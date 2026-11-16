"""Check the media bucket (S3_* settings in backend/.env), set its CORS rule, and optionally move
existing local media into it.

    cd backend
    .venv\\Scripts\\python scripts\\bucket_setup.py              # check access + set CORS
    .venv\\Scripts\\python scripts\\bucket_setup.py --migrate    # also upload data/projects/* to the bucket
    .venv\\Scripts\\python scripts\\bucket_setup.py --migrate --delete-local   # ...and free the disk

Safe to re-run. The CORS rule lets browsers on PUBLIC_URL (and localhost) upload straight to the
bucket and play videos from it.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from pathlib import Path


def _preload_env_file() -> None:
    """--env-file FILE: read settings from FILE (e.g. cloudflare/secrets.env) before backend/.env."""
    if "--env-file" not in sys.argv:
        return
    f = Path(sys.argv[sys.argv.index("--env-file") + 1])
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.split(" #", 1)[0].strip().strip('"').strip("'")


_preload_env_file()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, objstore  # noqa: E402

SKIP = {".wav", ".ass", ".part", ".tmp", ".ytdl", ".imported"}


def check() -> None:
    if not objstore.enabled():
        sys.exit("S3_BUCKET is empty in backend/.env. Fill in the S3_* settings first.")
    probe = f"_setup_check_{uuid.uuid4().hex[:6]}"
    objstore.put_json(probe, "check.json", {"ok": True})
    assert objstore.get_json(probe, "check.json") == {"ok": True}
    objstore.delete(probe, "check.json")
    print(f"OK: read/write access to bucket '{config.S3_BUCKET}'")


def set_cors() -> None:
    origins = sorted({config.PUBLIC_URL, "http://127.0.0.1:8000", "http://localhost:8000"})
    rules = {"CORSRules": [{"AllowedOrigins": origins, "AllowedMethods": ["GET", "HEAD", "PUT"],
                            "AllowedHeaders": ["content-type"], "ExposeHeaders": ["ETag"],
                            "MaxAgeSeconds": 3600}]}
    try:
        objstore._client().put_bucket_cors(Bucket=config.S3_BUCKET, CORSConfiguration=rules)
        print(f"OK: CORS allows uploads from {', '.join(origins)}")
    except Exception as exc:  # noqa: BLE001
        print(f"Could not set CORS automatically ({exc}).\n"
              "Your API token probably only has object access. Add the rule by hand:\n"
              "  Cloudflare dashboard -> R2 -> your bucket -> Settings -> CORS Policy -> Add, paste:\n"
              f'  [{{"AllowedOrigins": {origins!r}, "AllowedMethods": ["GET","HEAD","PUT"], '
              '"AllowedHeaders": ["content-type"], "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3600}]'
              .replace("'", '"'))


def migrate(delete_local: bool) -> None:
    root = config.PROJECTS_DIR
    dirs = [d for d in root.iterdir() if d.is_dir() and d.name.isalnum()] if root.exists() else []
    total = 0
    for d in dirs:
        stored = objstore.list_rel(d.name)
        files = [f for f in d.rglob("*") if f.is_file() and f.suffix.lower() not in SKIP
                 and f.name != "project.json" and f.relative_to(d).as_posix() not in stored]
        for f in files:
            rel = f.relative_to(d).as_posix()
            print(f"  {d.name}/{rel}  ({f.stat().st_size / 1e6:.1f} MB)")
            objstore.upload(d.name, rel, f)
            total += 1
        if delete_local:
            shutil.rmtree(d, ignore_errors=True)
    print(f"OK: uploaded {total} file(s) from {len(dirs)} project folder(s)"
          + ("; local copies deleted" if delete_local else "; local copies kept (add --delete-local to free the disk)"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migrate", action="store_true", help="upload existing data/projects/* to the bucket")
    ap.add_argument("--env-file", help="read settings from this file first, e.g. ../cloudflare/secrets.env")
    ap.add_argument("--delete-local", action="store_true", help="with --migrate: delete local copies afterwards")
    a = ap.parse_args()
    check()
    set_cors()
    if a.migrate:
        migrate(a.delete_local)
