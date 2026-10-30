"""Shared by the kit's scripts: settings from .env, the developer's own Azure CLI
sign-in, and JSON over HTTPS. Standard library only, so nothing to install."""

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent


def load_env() -> dict:
    """Settings from the environment, with .env (if any) filling the gaps."""
    values = {}
    env_file = KIT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k.startswith("HAIKO_")})
    return values


def setting(name: str, override: str | None = None, required: bool = True) -> str | None:
    value = override or load_env().get(name) or None
    if required and not value:
        fail(f"{name} isn't set. Add it to .env (see .env.example) or pass it on the command line.")
    return value


def fail(message: str, code: int = 1):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


def az_path() -> str:
    # On Windows the Azure CLI is az.cmd, which subprocess only finds by its full path.
    path = shutil.which("az") or shutil.which("az.cmd")
    if not path:
        fail("The Azure CLI (az) isn't installed or isn't on PATH. Run the setup skill, or: python scripts/doctor.py")
    return path


def az_token(resource: str, tenant: str | None = None) -> str:
    """An access token for `resource` from the developer's own `az login`. Never printed."""
    args = [az_path(), "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"]
    if tenant:
        args += ["--tenant", tenant]
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        hint = out.stderr.strip().splitlines()[-1] if out.stderr.strip() else ""
        login = f"az login --tenant {tenant} --allow-no-subscriptions" if tenant else "az login --allow-no-subscriptions"
        fail(f"Couldn't get a token for {resource}. Sign in with: {login}\n  ({hint})")
    return out.stdout.strip()


def http_json(method: str, url: str, headers: dict, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Accept": "application/json", **({"Content-Type": "application/json"} if data else {}), **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:500]}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        # No answer at all (offline, proxy, or a server restarting): a line, not a traceback.
        return 0, {"error": f"no response from {url.split('?')[0]}: {getattr(e, 'reason', e)}. Check your connection and try again in a minute."}


def emit(result, out: str | None):
    """Print JSON, or write it to `out` (creating folders) and say where."""
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {path}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
