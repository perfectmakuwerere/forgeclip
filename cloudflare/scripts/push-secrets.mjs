// Upload the app's settings to the Worker as secrets (they reach the container as env vars).
//   npm run secrets                 -> reads ./secrets.env
//   npm run secrets -- other.env    -> reads another file
// Format: KEY=value per line, # comments, same as backend/.env. The file is git-ignored; keep it that way.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const file = process.argv[2] || "secrets.env";
const secrets = {};
for (const raw of readFileSync(file, "utf8").split(/\r?\n/)) {
	const line = raw.trim();
	if (!line || line.startsWith("#") || !line.includes("=")) continue;
	const i = line.indexOf("=");
	const key = line.slice(0, i).trim();
	const value = line.slice(i + 1).split(" #")[0].trim().replace(/^(['"])(.*)\1$/, "$2");
	if (value) secrets[key] = value; // empty values are skipped, not uploaded as ""
}

const required = ["PUBLIC_URL", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY",
	"S3_BUCKET", "S3_ENDPOINT", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"];
const missing = required.filter((k) => !secrets[k]);
if (missing.length) {
	console.error(`Missing in ${file}: ${missing.join(", ")}`);
	process.exit(1);
}
if (secrets.CONTAINER_INSTANCE) {
	console.error("Set CONTAINER_INSTANCE in wrangler.jsonc (vars), not as a secret.");
	process.exit(1);
}

const dir = mkdtempSync(join(tmpdir(), "clipforge-"));
const json = join(dir, "secrets.json");
try {
	writeFileSync(json, JSON.stringify(secrets), { mode: 0o600 });
	console.log(`Uploading ${Object.keys(secrets).length} secrets: ${Object.keys(secrets).join(", ")}`);
	execFileSync("npx", ["wrangler", "secret", "bulk", json], { stdio: "inherit", shell: process.platform === "win32" });
} finally {
	rmSync(dir, { recursive: true, force: true });
}
