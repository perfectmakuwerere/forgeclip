/**
 * ClipForge on Cloudflare Workers + Containers.
 *
 * - Static frontend: served by Workers Static Assets (wrangler.jsonc "assets"); never wakes the container.
 * - /api/* and /media/*: forwarded to ONE container running the Python app (../Dockerfile). The app
 *   keeps job progress in memory, so every request goes to the same Durable Object, "main".
 * - Sleep: the container stops IDLE_MS after the last request. While the app reports background jobs
 *   (GET /api/health -> busy > 0) an alarm keeps it awake, so closing the tab doesn't kill a render.
 * - Media never passes through here: uploads and playback use signed R2 links (S3_* secrets).
 * - Config: every string var/secret of this Worker is passed to the container as an env var.
 *   Changing a secret or deploying a new image restarts the container the next time it is idle.
 */
import { DurableObject } from "cloudflare:workers";

const PORT = 8000;
const IDLE_MS = 10 * 60 * 1000; // keep running this long after the last request
const KEEPALIVE_MS = 4 * 60 * 1000; // while a job runs, check in this often
const READY_TIMEOUT_MS = 120 * 1000; // cold start: boot + Python imports
const DEFAULT_INSTANCE = "standard-2";

// Worker-only settings that the container doesn't need.
const WORKER_ONLY = new Set(["CONTAINER_INSTANCE"]);

type InstanceType = "lite" | "basic" | "standard-1" | "standard-2" | "standard-3" | "standard-4";

function containerEnv(env: Env): Record<string, string> {
	const out: Record<string, string> = {};
	for (const [k, v] of Object.entries(env)) {
		if (typeof v === "string" && !WORKER_ONLY.has(k)) out[k] = v;
	}
	out.CLIPFORGE_DATA_DIR = "/app/data"; // scratch space only; media lives in the R2 bucket
	return out;
}

/** Short hash of image + config, stored as a container label to spot stale containers. */
async function versionOf(image: string, env: Record<string, string>, instance: string): Promise<string> {
	const text = JSON.stringify([image, instance, Object.entries(env).sort()]);
	const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
	return [...new Uint8Array(digest)].slice(0, 12).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export class ClipForgeServer extends DurableObject<Env> {
	private starting: Promise<void> | undefined;
	private monitoring: Promise<void> | undefined;
	private versionChecked = false;

	constructor(ctx: DurableObjectState, env: Env) {
		super(ctx, env);
		const container = ctx.container;
		if (container?.running) {
			// A Durable Object restart (e.g. after a deploy) drops the timeout; set it again.
			void ctx.blockConcurrencyWhile(() => container.setInactivityTimeout(IDLE_MS));
			this.observeExit();
		}
	}

	async fetch(request: Request): Promise<Response> {
		try {
			this.starting ??= this.ensureRunning().finally(() => {
				this.starting = undefined;
			});
			await this.starting;
		} catch (err) {
			console.error("container start failed:", err);
			return Response.json(
				{ detail: "ClipForge is starting up. Please try again in a few seconds." },
				{ status: 503, headers: { "Retry-After": "5" } },
			);
		}
		await this.scheduleKeepalive();

		const url = new URL(request.url);
		const publicHost = url.host;
		url.protocol = "http:";
		url.host = "container";
		const headers = new Headers(request.headers);
		headers.delete("host");
		// The app runs uvicorn with --proxy-headers: this makes it see https (secure cookies) and the real IP.
		headers.set("x-forwarded-proto", "https");
		headers.set("x-forwarded-host", publicHost);
		const ip = request.headers.get("cf-connecting-ip");
		if (ip) headers.set("x-forwarded-for", ip);

		return this.ctx.container!.getTcpPort(PORT).fetch(
			new Request(url, {
				method: request.method,
				headers,
				body: request.body,
				// Media routes answer with a redirect to a signed R2 link: pass it to the browser instead of
				// following it here, so video bytes never flow through the Worker.
				redirect: "manual",
			}),
		);
	}

	/** Alarm: while the app has background jobs, keep the Durable Object (and so the container) active. */
	async alarm(): Promise<void> {
		if (!this.ctx.container?.running) return;
		if (await this.busy()) await this.ctx.storage.setAlarm(Date.now() + KEEPALIVE_MS);
		// Not busy: no new alarm. The container stops IDLE_MS after the last request.
	}

	private async scheduleKeepalive(): Promise<void> {
		if ((await this.ctx.storage.getAlarm()) === null) {
			await this.ctx.storage.setAlarm(Date.now() + KEEPALIVE_MS);
		}
	}

	private async ensureRunning(): Promise<void> {
		const container = this.ctx.container!;
		const env = containerEnv(this.env);
		const instance = (this.env.CONTAINER_INSTANCE || DEFAULT_INSTANCE) as InstanceType;
		const version = await versionOf(container.images.base, env, instance);

		// Once per Durable Object lifetime (i.e. after each deploy or secret change): replace a container
		// started from an older image/config, but never in the middle of a job.
		if (container.running && !this.versionChecked) {
			const info = await container.inspect();
			const current = info?.labels?.version;
			if (!current || current === version) {
				this.versionChecked = true;
			} else if (!(await this.busy())) {
				console.log(`restarting container: version ${current} -> ${version}`);
				await container.destroy("new version deployed");
				await this.monitoring?.catch(() => {});
			}
		}

		if (!container.running) {
			container.start({
				image: container.images.base,
				instance,
				enableInternet: true, // Supabase, R2, Groq, Stripe, yt-dlp downloads, social APIs
				env,
				labels: { version },
			});
			this.versionChecked = true;
		}
		this.observeExit();
		await container.setInactivityTimeout(IDLE_MS);
		await this.waitReady();
	}

	private async waitReady(): Promise<void> {
		const port = this.ctx.container!.getTcpPort(PORT);
		const deadline = Date.now() + READY_TIMEOUT_MS;
		while (Date.now() < deadline) {
			try {
				const res = await port.fetch("http://container/api/health", { signal: AbortSignal.timeout(2000) });
				await res.body?.cancel();
				if (res.ok) return;
			} catch {
				// not listening yet
			}
			await scheduler.wait(500);
		}
		throw new Error(`container did not answer on port ${PORT} within ${READY_TIMEOUT_MS / 1000}s`);
	}

	private async busy(): Promise<boolean> {
		try {
			const res = await this.ctx.container!.getTcpPort(PORT).fetch("http://container/api/health", {
				signal: AbortSignal.timeout(5000),
			});
			if (!res.ok) return false;
			const body = (await res.json()) as { busy?: number };
			return (body.busy ?? 0) > 0;
		} catch {
			return false;
		}
	}

	private observeExit(): void {
		if (this.monitoring) return;
		this.monitoring = this.ctx
			.container!.monitor()
			.then(() => console.log("container stopped"))
			.catch((err: unknown) => console.error("container exited with an error:", err))
			.finally(() => {
				this.monitoring = undefined;
			});
		this.ctx.waitUntil(this.monitoring);
	}
}

export default {
	async fetch(request, env): Promise<Response> {
		const { pathname } = new URL(request.url);
		if (pathname.startsWith("/api/") || pathname.startsWith("/media/")) {
			return env.CLIPFORGE.getByName("main").fetch(request);
		}
		return env.ASSETS.fetch(request);
	},
} satisfies ExportedHandler<Env>;
