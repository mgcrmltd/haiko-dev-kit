"""Read-only CRM metadata for the Haiko Dev Kit.

    python scripts/crm.py whoami
    python scripts/crm.py solutions
    python scripts/crm.py entities [--custom] [--solution <uniquename>]
    python scripts/crm.py entity <logicalname>          fields, option values, lookups, text lengths
    python scripts/crm.py contact-paths <logicalname>   every way a record leads to a contact
    python scripts/crm.py processes [--entity <name>]   BPF stages, cloud flows, classic workflows
    python scripts/crm.py plugin-steps [--entity <name>]
    python scripts/crm.py counts <logicalname> [...]    how many records (counts only)

Add --out <file> to save the JSON instead of printing it. The CRM URL comes from
HAIKO_CRM_URL in .env, or --org.

Two promises, both enforced by tests (scripts/tests/test_crm.py):
  * It never writes: every request is a GET.
  * It never reads record contents: every request goes to a metadata or
    process-definition endpoint on ALLOWED, and records are only ever counted.
"""

import argparse
import json
import sys
import urllib.parse

import kit

API = "/api/data/v9.2/"

# The only things this script may ask Dataverse for. Metadata, solution and
# process definitions, and counts. No table of business records is on it.
ALLOWED = {
    "WhoAmI",
    "RetrieveTotalRecordCount",
    "EntityDefinitions",
    "GlobalOptionSetDefinitions",
    "solutions",
    "solutioncomponents",
    "workflows",
    "sdkmessageprocessingsteps",
}

# Entities whose lookups say nothing about which contact a record belongs to.
NOT_A_PATH = {"systemuser", "team", "businessunit", "organization", "transactioncurrency", "owner",
              "queue", "sla", "slakpiinstance", "processstage", "msdyn_flow_approval", "subject",
              "knowledgearticle", "email", "activitypointer", "socialprofile", "territory", "pricelevel"}


class Dataverse:
    def __init__(self, org: str, tenant: str | None):
        self.org = org.rstrip("/")
        self._token = kit.az_token(self.org, tenant)

    def get(self, path: str) -> dict:
        """GET one Dataverse path. Refuses anything not on ALLOWED."""
        target = path.split("?", 1)[0].split("(", 1)[0].split("/", 1)[0]
        if target not in ALLOWED:
            raise PermissionError(f"crm.py only reads metadata; '{target}' isn't on its allow-list")
        status, body = kit.http_json("GET", self.org + API + path.replace(" ", "%20"), {
            "Authorization": "Bearer " + self._token, "OData-MaxVersion": "4.0", "OData-Version": "4.0",
            "Prefer": 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'})
        if status >= 400 or status == 0:  # 0: no response at all
            message = (body or {}).get("error", {})
            message = message.get("message") if isinstance(message, dict) else message
            kit.fail(f"Dataverse said {status} for {target}: {message}")
        return body

    def all(self, path: str) -> list:
        """Every row of a collection, following paging."""
        out, body = [], self.get(path)
        while True:
            out += body.get("value", [])
            nxt = body.get("@odata.nextLink")
            if not nxt:
                return out
            body = self.get(nxt.split(API, 1)[1])


def q(s: str) -> str:
    return urllib.parse.quote(s, safe="'(),=")


def label(meta) -> str | None:
    return ((meta or {}).get("UserLocalizedLabel") or {}).get("Label")


# --------------------------------------------------------------------------
# Solutions and entities
# --------------------------------------------------------------------------

def solutions(dv: Dataverse, _args):
    rows = dv.all("solutions?$select=uniquename,friendlyname,ismanaged,version,installedon"
                  "&$expand=publisherid($select=friendlyname,customizationprefix)"
                  "&$filter=" + q("isvisible eq true") + "&$orderby=installedon desc")
    return [{"uniqueName": r["uniquename"], "name": r["friendlyname"], "managed": r["ismanaged"], "version": r["version"],
             "publisher": (r.get("publisherid") or {}).get("friendlyname"),
             "prefix": (r.get("publisherid") or {}).get("customizationprefix")} for r in rows]


def entities(dv: Dataverse, args):
    filt = "IsIntersect eq false" + (" and IsCustomEntity eq true" if args.custom else "")
    rows = dv.all("EntityDefinitions?$select=LogicalName,DisplayName,IsCustomEntity,IsActivity,OwnershipType,MetadataId"
                  "&$filter=" + q(filt))
    if args.solution:
        sol = dv.all("solutions?$select=solutionid&$filter=" + q(f"uniquename eq '{args.solution}'"))
        if not sol:
            kit.fail(f"No solution called {args.solution}. List them with: python scripts/crm.py solutions")
        ids = {c["objectid"] for c in dv.all("solutioncomponents?$select=objectid&$filter="
                                             + q(f"componenttype eq 1 and _solutionid_value eq {sol[0]['solutionid']}"))}
        rows = [r for r in rows if r["MetadataId"] in ids]
    return sorted(({"logicalName": r["LogicalName"], "displayName": label(r.get("DisplayName")), "custom": r["IsCustomEntity"],
                    "activity": r["IsActivity"], "ownership": r.get("OwnershipType")} for r in rows),
                  key=lambda r: r["logicalName"])


def options(meta) -> list:
    os_ = (meta or {}).get("Options") or []
    return [{"value": o["Value"], "label": label(o.get("Label"))} for o in os_]


def entity(dv: Dataverse, args):
    name = args.name
    base = f"EntityDefinitions(LogicalName='{name}')"
    e = dv.get(base + "?$select=LogicalName,DisplayName,DisplayCollectionName,PrimaryIdAttribute,PrimaryNameAttribute,"
                      "EntitySetName,IsCustomEntity,OwnershipType")
    attrs = dv.all(base + "/Attributes?$select=LogicalName,DisplayName,AttributeType,AttributeTypeName,RequiredLevel,"
                          "IsCustomAttribute,IsValidForCreate,IsValidForUpdate,AttributeOf&$filter=" + q("AttributeOf eq null"))
    lookups = {a["LogicalName"]: a.get("Targets") for a in dv.all(base + "/Attributes/Microsoft.Dynamics.CRM.LookupAttributeMetadata?$select=LogicalName,Targets")}
    opts = {}
    for cast in ("PicklistAttributeMetadata", "MultiSelectPicklistAttributeMetadata", "StatusAttributeMetadata", "StateAttributeMetadata"):
        for a in dv.all(base + f"/Attributes/Microsoft.Dynamics.CRM.{cast}?$select=LogicalName&$expand=OptionSet($select=Options)"):
            opts[a["LogicalName"]] = options(a.get("OptionSet"))
    # The most characters a text column holds; an app's text field must not allow more.
    lengths = {}
    for cast in ("StringAttributeMetadata", "MemoAttributeMetadata"):
        for a in dv.all(base + f"/Attributes/Microsoft.Dynamics.CRM.{cast}?$select=LogicalName,MaxLength"):
            lengths[a["LogicalName"]] = a.get("MaxLength")
    fields = []
    for a in sorted(attrs, key=lambda a: a["LogicalName"]):
        f = {"name": a["LogicalName"], "label": label(a.get("DisplayName")),
             "type": (a.get("AttributeTypeName") or {}).get("Value", a.get("AttributeType")),
             "required": (a.get("RequiredLevel") or {}).get("Value") in ("ApplicationRequired", "SystemRequired"),
             "custom": a.get("IsCustomAttribute"), "create": a.get("IsValidForCreate"), "update": a.get("IsValidForUpdate")}
        if a["LogicalName"] in lookups:
            f["targets"] = lookups[a["LogicalName"]]
        if a["LogicalName"] in opts:
            f["options"] = opts[a["LogicalName"]]
        if lengths.get(a["LogicalName"]):
            f["maxLength"] = lengths[a["LogicalName"]]
        fields.append(f)
    return {"logicalName": e["LogicalName"], "displayName": label(e.get("DisplayName")),
            "pluralName": label(e.get("DisplayCollectionName")), "entitySetName": e["EntitySetName"],
            "primaryId": e["PrimaryIdAttribute"], "primaryName": e["PrimaryNameAttribute"],
            "custom": e["IsCustomEntity"], "ownership": e.get("OwnershipType"), "fields": fields}


# --------------------------------------------------------------------------
# Paths from a record to a contact
# --------------------------------------------------------------------------

def many_to_one(dv: Dataverse, name: str, cache: dict) -> list:
    if name not in cache:
        cache[name] = [(r["ReferencingAttribute"], r["ReferencedEntity"]) for r in
                       dv.all(f"EntityDefinitions(LogicalName='{name}')/ManyToOneRelationships"
                              "?$select=ReferencingAttribute,ReferencedEntity")]
    return cache[name]


def contact_paths(dv: Dataverse, args):
    """Every way a record of `name` can be tied to one contact, narrowest first.

    direct     the record's own lookup to contact (customerid, ec_studentid...)
    via        the record's lookup to another record that has a lookup to contact
    account    the record's lookup to account; every contact of that account (broad)
    reverse    a lookup on contact pointing at this record (the contact's own course, say)
    """
    name, cache, paths = args.name, {}, []
    rels = many_to_one(dv, name, cache)
    targets_of = {}
    for attr, target in rels:
        targets_of.setdefault(attr, set()).add(target)
    for attr, target in rels:
        if target == "contact":
            paths.append({"kind": "direct", "path": f"{name}.{attr} -> contact", "customerField": attr})
    for attr, target in rels:
        if target == "account":
            paths.append({"kind": "account", "path": f"{name}.{attr} -> account <- contact.parentcustomerid",
                          "customerField": attr, "note": "every contact of that account; broad"})
    for attr, target in rels:
        if target in NOT_A_PATH or target in ("contact", "account", name):
            continue
        for attr2, target2 in many_to_one(dv, target, cache):
            if target2 == "contact":
                paths.append({"kind": "via", "path": f"{name}.{attr} -> {target}.{attr2} -> contact",
                              "customerField": attr, "through": {"entity": target, "field": attr2}})
    for attr, target in many_to_one(dv, "contact", cache):
        if target == name:
            paths.append({"kind": "reverse", "path": f"contact.{attr} -> {name}", "contactField": attr})
    for p in paths:
        if len(targets_of.get(p.get("customerField"), ())) > 1:
            p["polymorphic"] = True  # the lookup can point at several tables (customerid, regardingobjectid)
    order = {"direct": 0, "via": 1, "reverse": 2, "account": 3}
    return {"entity": name, "paths": sorted(paths, key=lambda p: (order[p["kind"]], p.get("polymorphic", False)))}


# --------------------------------------------------------------------------
# Processes: business process flows, cloud flows, classic workflows
# --------------------------------------------------------------------------

def bpf_stages(clientdata: str) -> dict:
    """Stages in order, each with its entity and fields, from a BPF's definition."""
    stages, branches = {}, False

    def walk(node, entity=None):
        nonlocal branches
        cls = node.get("__class", "").split(":")[0]
        if cls == "EntityStep":
            entity = node.get("description")
        if cls == "ConditionStep":
            branches = True
        if cls == "StageStep":
            stages[node["stageId"]] = {"name": node.get("description"), "entity": entity, "next": node.get("nextStageId"), "fields": []}
            current = stages[node["stageId"]]
            for step in node.get("steps", {}).get("list", []):
                for ctl in step.get("steps", {}).get("list", []):
                    if ctl.get("dataFieldName"):
                        current["fields"].append({"name": ctl["dataFieldName"], "required": bool(step.get("isProcessRequired"))})
        for child in node.get("steps", {}).get("list", []):
            walk(child, entity)

    walk(json.loads(clientdata))
    targets = {s["next"] for s in stages.values()}
    first = [sid for sid in stages if sid not in targets] or list(stages)
    ordered, seen, sid = [], set(), first[0] if first else None
    while sid in stages and sid not in seen:
        seen.add(sid)
        ordered.append(stages[sid])
        sid = stages[sid]["next"]
    ordered += [s for k, s in stages.items() if k not in seen]
    return {"stages": [{k: v for k, v in s.items() if k != "next"} for s in ordered], "branches": branches}


DATAVERSE_MESSAGES = {1: "create", 2: "delete", 3: "update", 4: "create or update", 5: "create or delete",
                      6: "update or delete", 7: "create, update or delete"}


def flow_summary(clientdata: str) -> dict:
    """What triggers a cloud flow and what it changes, from its definition."""
    definition = json.loads(clientdata).get("properties", {}).get("definition", {})
    triggers, effects = [], []
    for tname, t in (definition.get("triggers") or {}).items():
        t_inputs = t.get("inputs") if isinstance(t.get("inputs"), dict) else {}
        p = t_inputs.get("parameters") if isinstance(t_inputs.get("parameters"), dict) else {}
        if "subscriptionRequest/entityname" in p:
            triggers.append({"kind": "dataverse", "entity": p.get("subscriptionRequest/entityname"),
                             "when": DATAVERSE_MESSAGES.get(p.get("subscriptionRequest/message"), p.get("subscriptionRequest/message")),
                             "fields": [f.strip() for f in (p.get("subscriptionRequest/filteringattributes") or "").split(",") if f.strip()],
                             "filter": p.get("subscriptionRequest/filterexpression")})
        else:
            triggers.append({"kind": t.get("kind") or t.get("type"), "name": tname,
                             "recurrence": (t.get("recurrence") or {}) or None})

    def walk(actions):
        for aname, a in (actions or {}).items():
            if not isinstance(a, dict):
                continue
            inputs = a.get("inputs") if isinstance(a.get("inputs"), dict) else {}
            op = ((inputs.get("host") or {}).get("operationId")) or a.get("type")
            p = inputs.get("parameters") if isinstance(inputs.get("parameters"), dict) else {}
            if op in ("CreateRecord", "UpdateRecord", "UpdateOnlyRecord", "DeleteRecord"):
                effects.append({"op": op, "entity": p.get("entityName"),
                                "fields": sorted(k.split("/", 1)[1] for k in p if k.startswith("item/"))})
            elif op in ("PerformBoundAction", "PerformUnboundAction"):
                effects.append({"op": op, "entity": p.get("entityName"), "action": p.get("actionName")})
            elif op and ("SendEmail" in op or "PostMessage" in op):
                effects.append({"op": op})
            walk(a.get("actions"))
            walk((a.get("else") or {}).get("actions"))
            for case in (a.get("cases") or {}).values():
                walk(case.get("actions"))
            walk((a.get("default") or {}).get("actions"))

    walk(definition.get("actions"))
    return {"triggers": triggers, "effects": effects}


CATEGORY = {0: "classic workflow", 3: "action", 4: "business process flow", 5: "cloud flow"}


def processes(dv: Dataverse, args):
    # Business process flows, cloud flows and classic workflows, managed or not;
    # custom actions only when unmanaged (Dynamics ships hundreds), unless --all.
    filt = "type eq 1 and (category eq 0 or category eq 4 or category eq 5 or (category eq 3"
    filt += ("))" if args.all else " and ismanaged eq false)) and statecode eq 1")
    if args.entity:
        filt += f" and primaryentity eq '{args.entity}'"
    rows = dv.all("workflows?$select=name,uniquename,category,primaryentity,statecode,mode,ismanaged,"
                  "triggeroncreate,triggerondelete,triggeronupdateattributelist,clientdata&$filter=" + q(filt))
    out = []
    for r in rows:
        p = {"name": r["name"], "kind": CATEGORY[r["category"]], "entity": r["primaryentity"],
             "active": r["statecode"] == 1, "managed": r["ismanaged"]}
        try:
            if r["category"] == 4 and r.get("clientdata"):
                p.update(bpf_stages(r["clientdata"]))
            elif r["category"] == 5 and r.get("clientdata"):
                p.update(flow_summary(r["clientdata"]))
            elif r["category"] == 0:
                p["triggers"] = {"create": r.get("triggeroncreate"), "delete": r.get("triggerondelete"),
                                 "updateOf": [f for f in (r.get("triggeronupdateattributelist") or "").split(",") if f]}
                p["realTime"] = r.get("mode") == 1
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            p["unreadable"] = f"couldn't read its definition: {e}"
        out.append(p)
    order = {"business process flow": 0, "cloud flow": 1, "classic workflow": 2, "action": 3}
    return sorted(out, key=lambda p: (not p["active"], order[p["kind"]], p["entity"] or "", p["name"]))


def plugin_steps(dv: Dataverse, args):
    rows = dv.all("sdkmessageprocessingsteps?$select=name,stage,mode,filteringattributes,ishidden"
                  "&$expand=sdkmessageid($select=name),sdkmessagefilterid($select=primaryobjecttypecode),plugintypeid($select=typename)"
                  "&$filter=" + q("statecode eq 0 and ishidden/Value eq false" + ("" if args.all else " and ismanaged eq false")))
    stage = {10: "pre-validation", 20: "pre-operation", 40: "post-operation"}
    out = [{"name": r["name"], "message": (r.get("sdkmessageid") or {}).get("name"),
            "entity": (r.get("sdkmessagefilterid") or {}).get("primaryobjecttypecode"),
            "stage": stage.get(r["stage"], r["stage"]), "async": r["mode"] == 1,
            "fields": [f for f in (r.get("filteringattributes") or "").split(",") if f],
            "plugin": (r.get("plugintypeid") or {}).get("typename")} for r in rows]
    return [s for s in out if not args.entity or s["entity"] == args.entity]


def counts(dv: Dataverse, args):
    names = "[" + ",".join(f"'{n}'" for n in args.names) + "]"
    body = dv.get("RetrieveTotalRecordCount(EntityNames=@n)?@n=" + q(names))
    c = body["EntityRecordCountCollection"]
    return {"counts": dict(zip(c["Keys"], c["Values"])),
            "note": "Dataverse's stored counts, refreshed about daily; enough to tell a live entity from an unused one."}


def whoami(dv: Dataverse, _args):
    me = dv.get("WhoAmI")
    return {"org": dv.org, "userId": me["UserId"], "organizationId": me["OrganizationId"]}


def main(argv=None):
    # --org, --tenant and --out work before or after the command.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--org", default=argparse.SUPPRESS, help="Dataverse URL (default: HAIKO_CRM_URL)")
    common.add_argument("--tenant", default=argparse.SUPPRESS, help="Entra tenant id (default: HAIKO_TENANT_ID, else az's current)")
    common.add_argument("--out", default=argparse.SUPPRESS, help="write the JSON to this file instead of printing it")
    ap = argparse.ArgumentParser(description="Read-only CRM metadata for the Haiko Dev Kit.", parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)

    def cmd(name, fn, help_):
        p = sub.add_parser(name, parents=[common], help=help_)
        p.set_defaults(fn=fn)
        return p

    cmd("whoami", whoami, "who you are signed in as")
    cmd("solutions", solutions, "solutions, with publisher prefixes")
    p = cmd("entities", entities, "tables; --custom, --solution <uniquename>")
    p.add_argument("--custom", action="store_true")
    p.add_argument("--solution")
    cmd("entity", entity, "one table's fields, option values and lookups").add_argument("name")
    cmd("contact-paths", contact_paths, "every way a record leads to a contact").add_argument("name")
    for name, fn, help_ in (("processes", processes, "BPF stages, cloud flows, classic workflows, custom actions"),
                            ("plugin-steps", plugin_steps, "plugin registrations")):
        p = cmd(name, fn, help_)
        p.add_argument("--entity")
        p.add_argument("--all", action="store_true", help="also inactive processes, and managed actions / plugin steps (Microsoft's own)")
    cmd("counts", counts, "how many records (counts only)").add_argument("names", nargs="+")
    args = ap.parse_args(argv)
    org = kit.setting("HAIKO_CRM_URL", getattr(args, "org", None))
    dv = Dataverse(org, kit.setting("HAIKO_TENANT_ID", getattr(args, "tenant", None), required=False))
    kit.emit(args.fn(dv, args), getattr(args, "out", None))


if __name__ == "__main__":
    main()
