"""Assesses a security manifest against the CRM: every way each entity's records lead to a contact.

    python scripts/assess.py --manifest workspace/<app>/security-manifest.json \\
        [--definition workspace/<app>/app-definition.json] [--out workspace/<app>/security-assessment.md]

For each entity the manifest grants, it lists every contact and account lookup the CRM
has (crm.py contact-paths) and marks the one the manifest uses, then reports:
  problems    a link that isn't a lookup to contact, "own" with no link, an entity or
              endpoint the app uses that the manifest doesn't cover (exit 1)
  to confirm  a link that can also point at an account, another lookup to contact on the
              same entity, read "all", every column returned, an endpoint that can write
              any field or a lookup to contact or account
Read-only, metadata only (it uses crm.py): no record is read and nothing is counted.
"""

import argparse
import json
import sys
import types
from pathlib import Path

import crm
import crmcheck
import kit

NO_ENTITY = ("rss-feed", "webview", "plugin")


class Metadata(crmcheck.Metadata):
    def __init__(self, dv: crm.Dataverse):
        super().__init__(dv)
        self.path_cache = {}

    def paths(self, name: str) -> list:
        if name not in self.path_cache:
            self.path_cache[name] = crm.contact_paths(self.dv, types.SimpleNamespace(name=name))["paths"]
        return self.path_cache[name]


def used_by(definition: dict):
    """The entities and endpoint ids an app definition uses, each with where."""
    ents, eps = {}, {}
    for s in definition.get("screens", []):
        if s.get("entity") and s.get("type") not in NO_ENTITY:
            ents.setdefault(s["entity"], f"screen `{s['id']}`")
        ids = (s.get("createEndpointIds") or []) + (s.get("updateEndpointIds") or []) + (s.get("actionEndpointIds") or [])
        ids += [(f.get("lookupConfig") or {}).get("endpointId") for f in s.get("fields", [])]
        ids += [(st.get("action") or {}).get("endpointId") for st in (s.get("journey") or {}).get("stages", [])]
        for eid in filter(None, ids):
            eps.setdefault(eid, f"screen `{s['id']}`")
    for w in definition.get("workflows", []):
        if w.get("entity"):
            ents.setdefault(w["entity"], f"multi-step form `{w['id']}`")
        if w.get("submitEndpointId"):
            eps.setdefault(w["submitEndpointId"], f"multi-step form `{w['id']}`")
    return ents, eps


def assess(md: Metadata, manifest: dict, definition: dict | None = None):
    """(problems, to confirm, report sections) for a manifest."""
    problems, confirm, sections = [], [], []
    entities = manifest.get("entities", {})

    for ent, pol in entities.items():
        lines = []
        if md.entity(ent) is None:
            problems.append(f"`{ent}`: the CRM has no such entity")
            sections.append((ent, pol, ["- The CRM has no such entity."]))
            continue
        cf, read = pol.get("customerField"), pol.get("read")
        paths = md.paths(ent)
        direct = [p for p in paths if p["kind"] == "direct"]

        if cf:
            f = md.field(ent, cf)
            targets = (f or {}).get("targets") or []
            if f is None:
                problems.append(f"`{ent}.{cf}`: the manifest links records to the contact by `{cf}`, but `{ent}` has no such field")
            elif "contact" not in targets:
                choices = ", ".join(f"`{p['customerField']}`" for p in direct) or "none"
                problems.append(f"`{ent}.{cf}`: the manifest links records to the contact by `{cf}`, but it's a lookup to {', '.join(targets) or 'nothing'}, "
                                f"not to contact. Its lookups to contact: {choices}")
            elif len(targets) > 1:
                confirm.append(f"`{ent}.{cf}` can point at {' or '.join(targets)}. Records whose `{cf}` is "
                               f"{' or '.join(t for t in targets if t != 'contact')} won't show for any contact. Is that intended?")
            others = [p["customerField"] for p in direct if p["customerField"] != cf]
            if others and f is not None and "contact" in targets:
                confirm.append(f"`{ent}` also has {', '.join(f'`{o}`' for o in others)} as lookup(s) to contact. "
                               f"Confirm `{cf}` is the one that means the record is the contact's own.")
        elif read == "own":
            problems.append(f"`{ent}`: read is \"own\" but there's no customerField to say whose records they are")
        if read == "all":
            names = ", ".join(f"`{p['customerField']}`" for p in direct)
            hint = f" It has a lookup to contact ({names}), so its records may belong to someone." if direct else ""
            confirm.append(f"`{ent}`: read \"all\", so every signed-in contact sees every record.{hint} Is it really public?")
        if read in ("own", "all") and pol.get("allowedFields") in (None, "", "*"):
            confirm.append(f"`{ent}`: no allowedFields, so every column goes to the app. List only the fields it shows.")

        lines.append(f"- Read: **{read}**" + (f" through `{cf}`" if cf else "") + f"; create: **{'yes' if pol.get('create') else 'no'}**; update: **{pol.get('update', 'none')}**")
        if pol.get("allowedFields") not in (None, "", "*"):
            lines.append(f"- Fields returned: {pol['allowedFields'].replace(',', ', ')}")
        lines.append("- Every path in the CRM from a record to a contact:" if paths else "- The CRM has no path from these records to a contact.")
        for p in paths:
            used = cf and p.get("customerField") == cf and p["kind"] == "direct"
            note = [x for x in (p.get("polymorphic") and "can point at other tables", p.get("note")) if x]
            lines.append(f"  - {'**uses** ' if used else ''}{p['kind']}: `{p['path']}`" + (f" ({'; '.join(note)})" if note else ""))
        sections.append((ent, pol, lines))

    ep_lines = []
    for ep in manifest.get("endpoints", []):
        eid, kind, ent = ep.get("id"), ep.get("type"), ep.get("entity")
        writes = ep.get("writableFields")
        target = f"`{ep.get('action')}`" if kind == "d365_action" else f"`{ep.get('uri')}`" if kind == "logic_app" else f"`{ent}`"
        ep_lines.append(f"- `{eid}` ({kind}, {target}): " + (("passes any input to it; its own code decides" if kind != "d365_direct" else "writes any field") if writes is None else f"writes {', '.join(writes)}" if writes else "writes no fields"))
        if kind == "d365_direct":
            if ent and ent not in entities:
                problems.append(f"endpoint `{eid}` writes to `{ent}`, which has no entity policy in the manifest")
            if writes is None:
                confirm.append(f"endpoint `{eid}` has no writableFields, so the contact can set any field of `{ent}`. List the fields its form sends.")
            pol_cf = (entities.get(ent) or {}).get("customerField")
            if ep.get("customerField") and pol_cf and ep["customerField"] != pol_cf:
                confirm.append(f"endpoint `{eid}` sets `{ep['customerField']}` to the contact, but `{ent}` is read through `{pol_cf}`. "
                               "Records it creates may not show for the contact who made them.")
        for name in writes or []:
            f = md.field(ent, name) if ent and md.entity(ent) else None
            linked = [t for t in (f or {}).get("targets") or [] if t in ("contact", "account")]
            if linked and name != ep.get("customerField"):
                confirm.append(f"endpoint `{eid}` lets the contact set `{ent}.{name}`, a lookup to {' or '.join(linked)}. "
                               "They could tie a record to someone else. Is it needed?")
        if kind == "logic_app":
            confirm.append(f"endpoint `{eid}` calls an outside URL ({ep.get('uri')}). Confirm it acts only for the signed-in contact.")

    if definition:
        ents, eps = used_by(definition)
        for ent, where in ents.items():
            if ent not in entities:
                problems.append(f"`{ent}`: {where} uses it, but the manifest has no policy for it, so the runtime API refuses it")
        ids = {e.get("id") for e in manifest.get("endpoints", [])}
        for eid, where in eps.items():
            if eid not in ids:
                problems.append(f"endpoint `{eid}`: {where} calls it, but the manifest doesn't allow it")
    return problems, confirm, sections, ep_lines


def report(problems, confirm, sections, ep_lines) -> str:
    out = ["# Security assessment", "",
           "The security manifest checked against the CRM's lookups to contact and account. Metadata only: no records were read.", "",
           f"**{len(problems)} problem(s), {len(confirm)} to confirm.**", ""]
    if problems:
        out += ["## Problems", "", "Fix these before saving the manifest.", ""] + [f"- {p}" for p in problems] + [""]
    if confirm:
        out += ["## To confirm with the developer", ""] + [f"- {c}" for c in confirm] + [""]
    out += ["## Entities", ""]
    for ent, _pol, lines in sections:
        out += [f"### {ent}", ""] + lines + [""]
    if ep_lines:
        out += ["## Endpoints", ""] + ep_lines + [""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Assess a security manifest against the CRM's contact lookups (read-only).")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--definition", help="the app definition, to check the manifest covers everything the app uses")
    ap.add_argument("--out", help="write the assessment here as markdown (default: print it)")
    ap.add_argument("--org", help="Dataverse URL (default: HAIKO_CRM_URL)")
    args = ap.parse_args(argv)
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8")) if p else None
    d = load(args.definition)
    dv = crm.Dataverse(kit.setting("HAIKO_CRM_URL", args.org), kit.setting("HAIKO_TENANT_ID", required=False))
    problems, confirm, sections, ep_lines = assess(Metadata(dv), load(args.manifest), (d or {}).get("definition", d))
    text = report(problems, confirm, sections, ep_lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        for p in problems:
            print(f"problem: {p}")
        for c in confirm:
            print(f"to confirm: {c}")
        print(f"\n{len(problems)} problem(s), {len(confirm)} to confirm. Wrote {args.out}")
    else:
        print(text)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
