"""Haiko Studio API v1 for the Dev Kit. Drafts only: no key can publish.

    python scripts/studio.py apps
    python scripts/studio.py pull <appId> --into workspace/<app>       app-definition.json + security-manifest.json
    python scripts/studio.py validate [--app <appId>] [--definition f] [--manifest f]
    python scripts/studio.py create --definition f [--manifest f]
    python scripts/studio.py save <appId> [--definition f] [--manifest f]
    python scripts/studio.py preview <appId> [--wait]

Settings come from .env: HAIKO_STUDIO_URL, HAIKO_STUDIO_ORG, HAIKO_STUDIO_API_KEY.
`save` and `create` validate first and refuse to send anything Studio would reject.
API description: <HAIKO_STUDIO_URL>/api/v1/openapi.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

import kit


class Studio:
    def __init__(self):
        env = kit.load_env()
        self.base = (env.get("HAIKO_STUDIO_URL") or "https://mgcrm-haiko-portal.azurewebsites.net").rstrip("/")
        self.org = kit.setting("HAIKO_STUDIO_ORG")
        self._key = kit.setting("HAIKO_STUDIO_API_KEY")

    def call(self, method: str, path: str, body=None, ok=(200, 201)):
        status, data = kit.http_json(method, f"{self.base}/api/v1/orgs/{self.org}{path}", {"Authorization": "Bearer " + self._key}, body)
        if status not in ok:
            kit.fail(f"Studio said {status} for {method} {path}: {(data or {}).get('error', data)}")
        return data


def load(path: str | None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def validate(studio: Studio, definition=None, manifest=None, app=None) -> dict:
    body = {k: v for k, v in (("definition", definition), ("securityManifest", manifest), ("appId", app)) if v is not None}
    return studio.call("POST", "/validate", body)


def report(result: dict) -> bool:
    if result["valid"]:
        print("valid: Studio found no problems")
    else:
        print(f"{len(result['errors'])} problem(s):")
        for e in result["errors"]:
            print(f"  {e['path']}: {e['message']}")
    return result["valid"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Haiko Studio API v1 (drafts only).")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("apps")
    p = sub.add_parser("pull"); p.add_argument("app"); p.add_argument("--into", required=True)
    p = sub.add_parser("validate"); p.add_argument("--app"); p.add_argument("--definition"); p.add_argument("--manifest")
    p = sub.add_parser("create"); p.add_argument("--definition", required=True); p.add_argument("--manifest")
    p = sub.add_parser("save"); p.add_argument("app"); p.add_argument("--definition"); p.add_argument("--manifest")
    p = sub.add_parser("preview"); p.add_argument("app"); p.add_argument("--wait", action="store_true", help="wait (up to 10 minutes) until it's ready or failed")
    args = ap.parse_args(argv)
    studio = Studio()

    if args.command == "apps":
        kit.emit(studio.call("GET", "/apps")["apps"], None)

    elif args.command == "pull":
        app = studio.call("GET", f"/apps/{args.app}")
        into = Path(args.into)
        into.mkdir(parents=True, exist_ok=True)
        (into / "app-definition.json").write_text(json.dumps(app["definition"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if app.get("securityManifest") is not None:
            (into / "security-manifest.json").write_text(json.dumps(app["securityManifest"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (into / "studio-app.json").write_text(json.dumps({k: app[k] for k in ("id", "name", "version", "updatedAt", "appConfigLabel", "manifestState", "manifestPublished")}, indent=2) + "\n", encoding="utf-8")
        print(f"pulled {app['name']} v{app['version']} into {into} (manifest: {app['manifestState']})")

    elif args.command == "validate":
        if not (args.app or args.definition or args.manifest):
            kit.fail("Give --app, --definition and/or --manifest.")
        sys.exit(0 if report(validate(studio, load(args.definition), load(args.manifest), args.app)) else 1)

    elif args.command in ("create", "save"):
        definition, manifest = load(args.definition), load(args.manifest)
        if args.command == "save" and definition is None and manifest is None:
            kit.fail("Nothing to save: give --definition and/or --manifest.")
        if not report(validate(studio, definition, manifest, getattr(args, "app", None))):
            kit.fail("Not saved. Fix the problems above, then try again.")
        if args.command == "create":
            out = studio.call("POST", "/apps", {"definition": definition, **({"securityManifest": manifest} if manifest else {})})
            app_id = out["app"]["id"]
            print(f"created {out['app']['name']} as {app_id}")
            if out.get("manifestNotice"):
                print(f"note: {out['manifestNotice']}")
        else:
            app_id = args.app
            if definition is not None:
                out = studio.call("PUT", f"/apps/{app_id}", {"definition": definition})
                print(f"saved definition: v{out.get('version')}")
            if manifest is not None:
                out = studio.call("PUT", f"/apps/{app_id}/manifest", manifest)
                print(f"saved security manifest as a draft: {out.get('manifestState')}")
                if out.get("manifestState") == "unpublished":
                    print("note: a person must review and publish it in Haiko Studio (the app's Security section). Until then the runtime API enforces the last published one.")
        print(f"Studio rebuilds its Preview now: python scripts/studio.py preview {app_id} --wait")

    elif args.command == "preview":
        deadline = time.time() + 600
        while True:
            p = studio.call("GET", f"/apps/{args.app}/preview")
            state = p.get("state") or ("disabled" if p.get("enabled") is False else "unknown")
            if not args.wait or state in ("ready", "failed", "none", "disabled") or time.time() > deadline:
                kit.emit(p, None)
                sys.exit(1 if state == "failed" else 0)
            print(f"preview: {state}...", file=sys.stderr)
            time.sleep(15)


if __name__ == "__main__":
    main()
