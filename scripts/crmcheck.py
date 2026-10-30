"""Checks every CRM name an app uses against the CRM itself, on your machine.

    python scripts/crmcheck.py --definition workspace/<app>/app-definition.json [--manifest workspace/<app>/security-manifest.json]

Studio can't see your CRM, so it checks an app's shape; this checks its names:
entities, fields, option values and the fields journey predicates use, plus the
manifest's customer fields (they must be lookups to contact) and allowed or
writable fields. Read-only, metadata only (it uses crm.py). Exit 1 on any problem.
"""

import argparse
import json
import re
import sys
import types
from pathlib import Path

import crm
import kit

FUNCTIONS = {"isEmpty", "hasValue", "isTrue", "isFalse", "contains", "isPast", "isFuture", "AND", "OR", "NOT", "true", "false", "null"}
SYSTEM = {"createdon", "modifiedon", "statecode", "statuscode", "ownerid"}


class Metadata:
    def __init__(self, dv: crm.Dataverse):
        self.dv, self.cache = dv, {}

    def entity(self, name: str):
        if name not in self.cache:
            try:
                self.cache[name] = crm.entity(self.dv, types.SimpleNamespace(name=name))
            except SystemExit:
                self.cache[name] = None
        return self.cache[name]

    def field(self, entity: str, name: str):
        e = self.entity(entity)
        return next((f for f in e["fields"] if f["name"] == name), None) if e else None


def predicate_fields(expr: str):
    """(field, compared value or None) for each field a predicate uses."""
    expr = re.sub(r'"[^"]*"', '""', expr or "")
    for m in re.finditer(r"\b([A-Za-z_][\w]*)(?:\.\w+)?\b(?:\s*(==|!=|>=|<=|>|<)\s*(-?\d+))?", expr):
        if m.group(1) not in FUNCTIONS:
            yield m.group(1), (int(m.group(3)) if m.group(3) and m.group(2) in ("==", "!=") else None)


def check(md: Metadata, definition: dict | None, manifest: dict | None) -> list[str]:
    problems = []

    def entity_ok(where, entity):
        if entity and md.entity(entity) is None:
            problems.append(f"{where}: entity '{entity}' doesn't exist in the CRM")
            return False
        return bool(entity)

    def field_ok(where, entity, name, options=None, value=None):
        if name in SYSTEM and not options and value is None:
            return
        f = md.field(entity, name)
        if f is None:
            problems.append(f"{where}: '{entity}' has no field '{name}'")
            return
        crm_values = {o["value"] for o in f.get("options", [])}
        for o in options or []:
            v = o.get("value")
            if crm_values and v is not None and int(v) not in crm_values:
                problems.append(f"{where}: option {v} ('{o.get('label')}') isn't a value of {entity}.{name}; the CRM has {sorted(crm_values)}")
        if value is not None and crm_values and value not in crm_values:
            problems.append(f"{where}: {entity}.{name} has no option value {value}; the CRM has {sorted(crm_values)}")

    for s in (definition or {}).get("screens", []):
        ent = s.get("entity")
        if not entity_ok(f"screens[{s.get('id')}]", ent):
            continue
        for f in s.get("fields", []):
            if f.get("crmField", True) and f.get("name"):
                field_ok(f"screens[{s['id']}].fields[{f['name']}]", ent, f["name"], f.get("options"))
        for key in ("titleField", "subtitleField", "dateField", "iconField", "customerField"):
            if s.get(key):
                field_ok(f"screens[{s['id']}].{key}", ent, s[key])
        journey = s.get("journey") or {}
        for st in journey.get("stages", []):
            for key in ("activeWhen", "completeWhen"):
                for name, value in predicate_fields(st.get(key, "")):
                    field_ok(f"screens[{s['id']}].journey.stages[{st.get('id')}].{key}", ent, name, value=value)
            for key in ("dateField",):
                if st.get(key):
                    field_ok(f"screens[{s['id']}].journey.stages[{st.get('id')}].{key}", ent, st[key])
            screen_only = {f["name"] for f in s.get("fields", []) if f.get("crmField") is False}
            for name in st.get("showFields", []):
                if name not in screen_only:  # a screen-only field (crmField false) isn't a CRM column
                    field_ok(f"screens[{s['id']}].journey.stages[{st.get('id')}].showFields", ent, name)
    for w in (definition or {}).get("workflows", []):
        entity_ok(f"workflows[{w.get('id')}]", w.get("entity"))

    for ent, policy in (manifest or {}).get("entities", {}).items():
        if not entity_ok(f"securityManifest.entities.{ent}", ent):
            continue
        cf = policy.get("customerField")
        if cf:
            f = md.field(ent, cf)
            if f is None:
                problems.append(f"securityManifest.entities.{ent}.customerField: '{ent}' has no field '{cf}'")
            elif "contact" not in (f.get("targets") or []):
                problems.append(f"securityManifest.entities.{ent}.customerField: '{cf}' isn't a lookup to contact (it points at {f.get('targets')})")
        elif policy.get("read") == "own":
            problems.append(f"securityManifest.entities.{ent}: read is 'own' but there's no customerField to say whose records they are")
        allowed = policy.get("allowedFields")
        if allowed and allowed != "*":
            for name in [x.strip() for x in allowed.split(",") if x.strip()]:
                field_ok(f"securityManifest.entities.{ent}.allowedFields", ent, name)
    for ep in (manifest or {}).get("endpoints", []):
        ent = ep.get("entity")
        if ep.get("type") == "d365_direct" and entity_ok(f"securityManifest.endpoints[{ep.get('id')}]", ent):
            for name in ep.get("writableFields") or []:
                field_ok(f"securityManifest.endpoints[{ep['id']}].writableFields", ent, name)
            if ep.get("customerField"):
                f = md.field(ent, ep["customerField"])
                if f is None or "contact" not in (f.get("targets") or []):
                    problems.append(f"securityManifest.endpoints[{ep['id']}].customerField: '{ep['customerField']}' isn't a lookup to contact on {ent}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check an app's CRM names against the CRM (read-only).")
    ap.add_argument("--definition")
    ap.add_argument("--manifest")
    ap.add_argument("--org", help="Dataverse URL (default: HAIKO_CRM_URL)")
    args = ap.parse_args(argv)
    if not (args.definition or args.manifest):
        kit.fail("Give --definition and/or --manifest.")
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8")) if p else None
    dv = crm.Dataverse(kit.setting("HAIKO_CRM_URL", args.org), kit.setting("HAIKO_TENANT_ID", required=False))
    problems = check(Metadata(dv), load(args.definition), load(args.manifest))
    for p in problems:
        print(p)
    print("CRM names: all found." if not problems else f"\n{len(problems)} name problem(s).")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
