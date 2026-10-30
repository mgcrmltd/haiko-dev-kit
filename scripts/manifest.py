"""Proposes the least-privilege security manifest for an app, with a reason for each grant.

    python scripts/manifest.py --definition workspace/<app>/app-definition.json \\
        [--link incident=customerid ...] [--shared ec_news ...] [--existing workspace/<app>/security-manifest.json] \\
        --out workspace/<app>/security-manifest.json --explain workspace/<app>/security-review.md

It grants only what the app uses:
  entities   read "own" through the contact link; allowedFields = every field the app shows or tests;
             create only where a create endpoint is used; update "own" only where the app updates
  endpoints  only those the app calls; writableFields = exactly the fields the forms create with
             and the journeys let the contact edit
Contact links come from --link, then the app's list screens (customerField), then --existing.
An entity the app uses with no link and not --shared is a problem: it's reported, never guessed.
Offline: reads files only. Check the result with crmcheck.py and studio.py validate.
"""

import argparse
import json
import re
import sys
from pathlib import Path

FUNCTIONS = {"isEmpty", "hasValue", "isTrue", "isFalse", "contains", "isPast", "isFuture", "AND", "OR", "NOT", "true", "false", "null"}
SCREEN_KEYS = ("titleField", "subtitleField", "dateField", "iconField", "statusField", "segmentField", "featureField", "imageField", "bodyField", "featuredImageField")


def predicate_fields(expr: str):
    expr = re.sub(r'"[^"]*"', '""', expr or "")
    return {m.group(1) for m in re.finditer(r"\b([A-Za-z_]\w*)(?:\.\w+)?\b", expr) if m.group(1) not in FUNCTIONS}


def message_fields(text: str):
    return {m.group(1) for m in re.finditer(r"\{(\w+)(?:\.\w+)?\}", text or "")}


def propose(definition: dict, links: dict, shared: set, existing: dict | None):
    screens = definition.get("screens", [])
    endpoints = {e["id"]: e for e in definition.get("endpoints", [])}
    old_eps = {e["id"]: e for e in (existing or {}).get("endpoints", [])}
    old_ents = (existing or {}).get("entities", {})
    reasons, problems = {}, []

    def why(key, text):
        reasons.setdefault(key, []).append(text)

    # Who each entity belongs to.
    for s in screens:
        if s.get("type") == "list" and s.get("customerField") and s.get("entity") not in links:
            links[s["entity"]] = s["customerField"]
            why(s["entity"], f"linked to the contact by `{s['customerField']}` (list screen `{s['id']}`)")
    for ent, pol in old_ents.items():
        if ent not in links and pol.get("customerField"):
            links[ent] = pol["customerField"]
            why(ent, f"linked to the contact by `{pol['customerField']}` (from the existing manifest)")

    # What each entity's screens read.
    read = {}
    for s in screens:
        ent = s.get("entity")
        if not ent or s.get("type") in ("rss-feed", "webview", "plugin"):
            continue
        fields = read.setdefault(ent, set())
        fields |= {f["name"] for f in s.get("fields", []) if f.get("crmField", True) and f.get("name") and f.get("showOnView", True)}
        fields |= {s[k] for k in SCREEN_KEYS if s.get(k)}
        fields |= set(re.findall(r"attribute=['\"](\w+)['\"]", s.get("filter") or ""))  # a list's FetchXML filter
        crm_names = {f["name"] for f in s.get("fields", []) if f.get("crmField", True)}
        screen_only = {f["name"] for f in s.get("fields", []) if f.get("crmField") is False}
        for st in (s.get("journey") or {}).get("stages", []):
            fields |= predicate_fields(st.get("activeWhen")) | predicate_fields(st.get("completeWhen")) | predicate_fields(st.get("appliesWhen"))
            fields |= message_fields(st.get("message")) | {st[k] for k in ("dateField",) if st.get(k)}
            fields |= {n for n in st.get("showFields", []) if n not in screen_only}
        if crm_names or s.get("journey"):
            why(ent, f"screen `{s['id']}` shows or tests {len(fields)} field(s) so far")

    # Which endpoints the app calls, and how.
    used = {}  # endpoint id -> {"create": {fields}, "update": {fields}, "entity": ent, "options": bool}
    workflows = definition.get("workflows", [])
    def use(eid, mode, ent, fields=(), where=""):
        if eid not in endpoints:
            problems.append(f"{where} uses endpoint `{eid}`, which the definition doesn't have")
            return
        u = used.setdefault(eid, {"create": set(), "update": set(), "entity": None, "options": False, "where": set()})
        if mode == "options":
            u["options"] = True
        else:
            u[mode] |= set(fields)
        u["entity"] = u["entity"] or ent
        u["where"].add(where)

    for s in screens:
        ent = s.get("entity")
        # A direct create writes CRM columns only; screen-only fields (crmField false) never reach the CRM.
        create_fields = [f["name"] for f in s.get("fields", []) if f.get("showOnCreate", True) and f.get("name") and f.get("crmField", True)]
        for eid in s.get("createEndpointIds") or []:
            use(eid, "create", ent, create_fields, f"form `{s['id']}`")
        for f in s.get("fields", []):
            if (f.get("lookupConfig") or {}).get("endpointId"):
                use(f["lookupConfig"]["endpointId"], "options", ent, where=f"lookup `{s['id']}.{f['name']}`")
        for eid in s.get("actionEndpointIds") or []:
            use(eid, "update", ent, (), f"record `{s['id']}` action")
        stages = (s.get("journey") or {}).get("stages", [])
        for st in stages:
            act = st.get("action") or {}
            if act.get("endpointId") and act.get("type") in ("endpoint", "confirm"):
                use(act["endpointId"], "update", ent, (), f"journey `{s['id']}.{st.get('id')}` button")
        if s.get("type") == "record" and stages:
            # Journey edits save through the entity's update endpoint (the app's own rule): fields a
            # stage shows and doesn't mark read-only. File fields go by upload, never in the save.
            files = {f["name"] for f in s.get("fields", []) if f.get("type") in ("file", "camera", "signature")}
            editable = set()
            for st in stages:
                editable |= set(st.get("showFields", [])) - set(st.get("readOnlyFields") or []) - files
            target = next((e for e in endpoints if any(sc.get("type") == "form" and sc.get("entity") == ent and e in (sc.get("updateEndpointIds") or []) for sc in screens)), None) \
                or next((e["id"] for e in endpoints.values() if e.get("uri") == ent), None)
            if editable and target:
                use(target, "update", ent, editable, f"journey edits on `{s['id']}`")
            elif editable:
                problems.append(f"record `{s['id']}` lets the contact edit {sorted(editable)} but no endpoint can save them")
    for w in workflows:
        if w.get("submitEndpointId"):
            forms = {st.get("formScreenId") for st in w.get("steps", [])}
            fields = [f["name"] for s in screens if s["id"] in forms for f in s.get("fields", []) if f.get("showOnCreate", True) and f.get("crmField", True)]
            use(w["submitEndpointId"], "create", w.get("entity"), fields, f"workflow `{w['id']}`")

    # Entities.
    entities = {}
    all_ents = set(read) | {u["entity"] for eid, u in used.items() if u["entity"] and endpoints[eid].get("type") == "d365_direct"}
    for ent in sorted(all_ents):
        mine = [u for u in used.values() if u["entity"] == ent]
        creates = any(u["create"] for u in mine)
        # An update is a save of journey edits, or a record button / action (they run against a record).
        updates = any(u["update"] or any("button" in w or "action" in w for w in u["where"]) for u in mine)
        if ent in shared:
            pol = {"customerField": None, "read": "all", "create": False, "update": "none"}
            why(ent, "shared content: every signed-in contact may read it (you said so with --shared)")
        elif ent in links:
            pol = {"customerField": links[ent], "read": "own", "create": creates, "update": "own" if updates else "none"}
        else:
            problems.append(f"`{ent}`: the app uses it but nothing says which contact a record belongs to. Pass --link {ent}=<lookup to contact>, or --shared {ent} if every contact may see every record")
            continue
        fields = sorted((read.get(ent, set()) - {"createdon", "modifiedon", "statecode", "statuscode", "ownerid"} - ({links.get(ent)} if links.get(ent) else set()))
                        | ({"createdon"} & read.get(ent, set())) | ({"statuscode"} & read.get(ent, set())))
        if fields:
            pol["allowedFields"] = ",".join(fields)
            why(ent, f"may return only the {len(fields)} field(s) the app uses: {', '.join(fields)}")
        why(ent, "contacts may create these" if pol.get("create") else "contacts can't create these")
        why(ent, "contacts may update their own" if pol.get("update") == "own" else "contacts can't change these")
        entities[ent] = pol

    # Endpoints.
    out_eps = []
    for eid, u in used.items():
        e, old = endpoints[eid], old_eps.get(eid, {})
        ep = {"id": eid, "type": e.get("type", "d365_direct")}
        if ep["type"] == "d365_direct":
            ep["entity"] = e.get("uri") or u["entity"]
            if links.get(ep["entity"]):
                ep["customerField"] = links[ep["entity"]]
        elif ep["type"] == "d365_action":
            ep["action"] = old.get("action") or e.get("uri")
            if u["entity"]:
                ep["entity"] = u["entity"]
            for k in ("fieldMappings", "customerField"):
                if old.get(k):
                    ep[k] = old[k]
        else:
            ep["uri"] = e.get("uri")
        if e.get("submitMessage"):
            ep["submitMessage"] = e["submitMessage"]
        if not u["options"] or u["create"] or u["update"]:
            ep["writableFields"] = sorted(u["create"] | u["update"])
        out_eps.append(ep)
        why(f"endpoint:{eid}", f"used by {', '.join(sorted(u['where']))}" + (f"; may write only {', '.join(ep['writableFields'])}" if ep.get("writableFields") else "; writes no fields" if "writableFields" in ep else ""))
    for eid in sorted(set(old_eps) - set(used)):
        why(f"endpoint:{eid}", "left out: the app doesn't use it (it was in the existing manifest)")

    return {"entities": entities, "endpoints": sorted(out_eps, key=lambda e: e["id"])}, reasons, problems


def explain(manifest, reasons, problems) -> str:
    lines = ["# Security review", "", "What the app's draft manifest lets a signed-in contact do, and why. Review it, then publish it in Haiko Studio (the app's Security section).", ""]
    if problems:
        lines += ["## Needs an answer", ""] + [f"- {p}" for p in problems] + [""]
    lines += ["## Entities", ""]
    for ent, pol in manifest["entities"].items():
        lines += [f"### {ent}: read {pol['read']}, create {str(pol['create']).lower()}, update {pol['update']}", ""] + [f"- {r}" for r in reasons.get(ent, [])] + [""]
    lines += ["## Endpoints", ""]
    for key in [k for k in reasons if k.startswith("endpoint:")]:
        lines += [f"- `{key[9:]}`: " + "; ".join(reasons[key])]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Propose a least-privilege security manifest.")
    ap.add_argument("--definition", required=True)
    ap.add_argument("--link", action="append", default=[], help="entity=lookup to contact")
    ap.add_argument("--shared", action="append", default=[], help="entity every contact may read")
    ap.add_argument("--existing", help="the current manifest (action names and field mappings are kept from it)")
    ap.add_argument("--out", help="write the manifest here (default: print it)")
    ap.add_argument("--explain", help="write the review (reasons and questions) here as markdown")
    args = ap.parse_args(argv)
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    links = dict(x.split("=", 1) for x in args.link)
    d = load(args.definition)
    manifest, reasons, problems = propose(d.get("definition", d), links, set(args.shared), load(args.existing) if args.existing else None)
    text = json.dumps(manifest, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    review = explain(manifest, reasons, problems)
    if args.explain:
        Path(args.explain).write_text(review, encoding="utf-8")
        print(f"wrote {args.explain}")
    for p in problems:
        print(f"needs an answer: {p}", file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
