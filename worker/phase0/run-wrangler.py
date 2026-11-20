#!/usr/bin/env python3
"""Run wrangler with the registered custom.cloudflare credential.

Fetches a fresh surrogate from authd at runtime and passes it to wrangler
as CLOUDFLARE_API_TOKEN (in-process env only). No credential value is ever
printed, logged, or written to disk by this script.
Usage: run-wrangler.py <wrangler args...>
"""
import os, subprocess, sys
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import dynamic_credential_entry

def main():
    entry = dynamic_credential_entry("custom.cloudflare", "access_token")
    env = dict(os.environ)
    env["CLOUDFLARE_API_TOKEN"] = str(entry["surrogate"]).strip()
    r = subprocess.run(["wrangler"] + sys.argv[1:], env=env)
    return r.returncode

if __name__ == "__main__":
    raise SystemExit(main())
