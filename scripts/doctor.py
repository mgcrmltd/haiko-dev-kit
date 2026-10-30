"""Checks this machine is ready for the Haiko Dev Kit, one line per check.

    python scripts/doctor.py               # Windows (or: py scripts/doctor.py)
    python3 scripts/doctor.py              # macOS
    python scripts/doctor.py --offline     # tools only; skip the CRM and Studio checks
    python scripts/doctor.py --json        # for the agent

Exit code 0 when everything required passes. The setup skill
(.claude/skills/haiko-setup/SKILL.md) says how to fix each failure.
"""

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys

import kit

WINDOWS = platform.system() == "Windows"
results = []


def check(name: str, ok: bool | None, detail: str, fix: str = "", required: bool = True):
    """ok None means skipped."""
    results.append({"check": name, "status": "skip" if ok is None else "pass" if ok else ("fail" if required else "warn"),
                    "detail": detail, "fix": fix if ok is False else ""})


def run(*args) -> tuple[int, str]:
    exe = shutil.which(args[0]) or (shutil.which(args[0] + ".cmd") if WINDOWS else None)
    if not exe:
        return 127, ""
    try:
        out = subprocess.run([exe, *args[1:]], capture_output=True, text=True, timeout=60)
        return out.returncode, (out.stdout or out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def version(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    return tuple(int(x) for x in m.groups() if x) if m else ()


def tools():
    v = sys.version_info
    check("Python 3.11+", v >= (3, 11), f"{v.major}.{v.minor}.{v.micro} at {sys.executable}",
          "Install Python 3.12: winget install Python.Python.3.12 (Windows) / brew install python@3.12 (macOS)")
    if WINDOWS and "WindowsApps" in sys.executable:
        check("Python is a real install", False, "this is the Microsoft Store stub",
              "Settings > Apps > Advanced app settings > App execution aliases: turn off python.exe and python3.exe, then reopen the terminal")

    code, out = run("git", "--version")
    check("Git", code == 0, out or "not found", "winget install Git.Git (Windows) / xcode-select --install (macOS)")

    code, out = run("az", "version", "-o", "json")
    az_v = json.loads(out).get("azure-cli", "") if code == 0 and out.startswith("{") else ""
    check("Azure CLI", code == 0, f"azure-cli {az_v}" if az_v else "not found",
          "winget install Microsoft.AzureCLI (Windows) / brew install azure-cli (macOS), then open a new terminal")

    code, out = run("node", "--version")
    check("Node.js 20+ (plugins only)", code == 0 and version(out) >= (20,), out or "not found",
          "winget install OpenJS.NodeJS.LTS (Windows) / brew install node@20 (macOS). Only needed to build plugins.", required=False)

    code, out = run("pac", "help")
    check("Power Platform CLI (optional)", code == 0 or None, "found" if code == 0 else "not installed; not needed", required=False)


def signed_in():
    code, out = run("az", "account", "show", "-o", "json")
    if code != 0:
        check("Signed in to Azure CLI", False, "not signed in",
              "az login --tenant <your tenant> --allow-no-subscriptions  (use the account you sign in to Dynamics with)")
        return False
    acct = json.loads(out)
    check("Signed in to Azure CLI", True, f"{acct.get('user', {}).get('name')} in tenant {acct.get('tenantId')}")
    return True


def crm():
    env = kit.load_env()
    org = env.get("HAIKO_CRM_URL")
    if not org:
        check("CRM URL", False, "HAIKO_CRM_URL isn't set", "Copy .env.example to .env and set HAIKO_CRM_URL to your org, e.g. https://yourorg.crm11.dynamics.com")
        return
    url_ok = bool(re.match(r"^https://[\w-]+\.crm\d*\.dynamics\.com/?$", org))
    check("CRM URL", url_ok, org, "It should look like https://yourorg.crm11.dynamics.com (no path)")
    if not url_ok:
        return
    args = [kit.az_path(), "account", "get-access-token", "--resource", org.rstrip("/"), "--query", "accessToken", "-o", "tsv"]
    if env.get("HAIKO_TENANT_ID"):
        args += ["--tenant", env["HAIKO_TENANT_ID"]]
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        msg = (out.stderr.strip().splitlines() or [""])[-1]
        hint = ("Conditional Access may block the Azure CLI for Dynamics; ask your admin, or sign in with pac auth create and tell the agent"
                if "AADSTS53" in msg else "az login --tenant <your tenant> --allow-no-subscriptions")
        check("CRM token", False, msg[:200], hint)
        return
    status, body = kit.http_json("GET", org.rstrip("/") + "/api/data/v9.2/WhoAmI", {"Authorization": "Bearer " + out.stdout.strip()})
    check("CRM reachable (read-only)", status == 200, f"WhoAmI {status}" + (f", user {body.get('UserId')}" if status == 200 else f": {body}"),
          "Check the URL, and that your account has a security role in this environment")


def studio():
    env = kit.load_env()
    base, org, key = env.get("HAIKO_STUDIO_URL", "https://mgcrm-haiko-portal.azurewebsites.net"), env.get("HAIKO_STUDIO_ORG"), env.get("HAIKO_STUDIO_API_KEY")
    if not (org and key):
        check("Studio key", False, "HAIKO_STUDIO_ORG or HAIKO_STUDIO_API_KEY isn't set",
              "In Haiko Studio: Settings > API keys > create a 'Read and save drafts' key. Put it and your org id in .env")
        return
    status, body = kit.http_json("GET", f"{base.rstrip('/')}/api/v1/orgs/{org}/apps", {"Authorization": "Bearer " + key})
    detail = f"{len(body.get('apps', []))} app(s) in {org}" if status == 200 else f"{status}: {(body or {}).get('error')}"
    fix = {401: "The key is wrong, revoked or from before scopes: create a new one in Studio",
           403: "The key belongs to a different organisation: check HAIKO_STUDIO_ORG"}.get(status, "Check HAIKO_STUDIO_URL")
    check("Studio key", status == 200, detail, fix)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="check tools only")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    args = ap.parse_args()
    tools()
    if not args.offline and (shutil.which("az") or shutil.which("az.cmd")) and signed_in():
        crm()
    if not args.offline:
        studio()
    failed = [r for r in results if r["status"] == "fail"]
    if args.json:
        print(json.dumps({"ok": not failed, "platform": platform.system(), "results": results}, indent=2))
    else:
        mark = {"pass": "ok  ", "fail": "FAIL", "warn": "warn", "skip": "--  "}
        for r in results:
            print(f"[{mark[r['status']]}] {r['check']}: {r['detail']}")
            if r["fix"]:
                print(f"       fix: {r['fix']}")
        print("\nReady." if not failed else f"\n{len(failed)} check(s) to fix.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
