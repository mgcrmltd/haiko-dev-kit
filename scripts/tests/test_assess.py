"""assess finds what a security manifest gets wrong or should confirm. Offline: the metadata is faked."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import assess  # noqa: E402

ENTITIES = {
    "incident": {"fields": [
        {"name": "title"}, {"name": "description"},
        {"name": "customerid", "targets": ["account", "contact"]},
        {"name": "primarycontactid", "targets": ["contact"]},
        {"name": "ec_advisorid", "targets": ["systemuser"]},
    ]},
    "ec_placement": {"fields": [{"name": "ec_name"}, {"name": "ec_studentid", "targets": ["contact"]}, {"name": "ec_employerid", "targets": ["account"]}]},
    "ec_news": {"fields": [{"name": "ec_title"}]},
}
PATHS = {
    "incident": [{"kind": "direct", "path": "incident.customerid -> contact", "customerField": "customerid", "polymorphic": True},
                 {"kind": "direct", "path": "incident.primarycontactid -> contact", "customerField": "primarycontactid"},
                 {"kind": "account", "path": "incident.customerid -> account <- contact.parentcustomerid", "customerField": "customerid",
                  "note": "every contact of that account; broad", "polymorphic": True}],
    "ec_placement": [{"kind": "direct", "path": "ec_placement.ec_studentid -> contact", "customerField": "ec_studentid"},
                     {"kind": "account", "path": "ec_placement.ec_employerid -> account <- contact.parentcustomerid", "customerField": "ec_employerid"}],
    "ec_news": [],
}


class FakeMetadata(assess.Metadata):
    def __init__(self):
        self.cache, self.path_cache = dict(ENTITIES), dict(PATHS)

    def entity(self, name):
        return self.cache.get(name)


def run(manifest, definition=None):
    return assess.assess(FakeMetadata(), manifest, definition)


class Assess(unittest.TestCase):
    def test_a_tight_manifest_has_no_problems_or_questions(self):
        m = {"entities": {"ec_placement": {"customerField": "ec_studentid", "read": "own", "create": True, "update": "none", "allowedFields": "ec_name"}},
             "endpoints": [{"id": "submit", "type": "d365_direct", "entity": "ec_placement", "customerField": "ec_studentid", "writableFields": ["ec_name"]}]}
        d = {"screens": [{"id": "s", "entity": "ec_placement", "createEndpointIds": ["submit"]}], "workflows": []}
        problems, confirm, sections, _ = run(m, d)
        self.assertEqual((problems, confirm), ([], []))
        text = "\n".join(sections[0][2])
        self.assertIn("**uses** direct: `ec_placement.ec_studentid -> contact`", text)
        self.assertIn("account: `ec_placement.ec_employerid -> account", text)  # every path is listed, not only the one used

    def test_wrong_links_are_problems(self):
        m = {"entities": {"incident": {"customerField": "ec_advisorid", "read": "own", "create": False, "update": "none", "allowedFields": "title"},
                          "ec_placement": {"customerField": "ec_nosuch", "read": "own", "create": False, "update": "none", "allowedFields": "ec_name"},
                          "ec_news": {"customerField": None, "read": "own", "create": False, "update": "none", "allowedFields": "ec_title"},
                          "ec_gone": {"customerField": None, "read": "all", "create": False, "update": "none"}},
             "endpoints": []}
        found = "\n".join(run(m)[0])
        self.assertIn("`incident.ec_advisorid`: the manifest links records to the contact by `ec_advisorid`, but it's a lookup to systemuser, not to contact. Its lookups to contact: `customerid`, `primarycontactid`", found)
        self.assertIn("`ec_placement` has no such field", found)
        self.assertIn("`ec_news`: read is \"own\" but there's no customerField", found)
        self.assertIn("`ec_gone`: the CRM has no such entity", found)

    def test_broad_or_ambiguous_grants_are_raised(self):
        m = {"entities": {"incident": {"customerField": "customerid", "read": "own", "create": True, "update": "own"},
                          "ec_placement": {"customerField": None, "read": "all", "create": False, "update": "none", "allowedFields": "*"}},
             "endpoints": [{"id": "open_case", "type": "d365_direct", "entity": "incident", "customerField": "primarycontactid"},
                           {"id": "move", "type": "d365_direct", "entity": "incident", "customerField": "customerid", "writableFields": ["title", "primarycontactid"]},
                           {"id": "flow", "type": "logic_app", "uri": "https://example.test/hook"}]}
        problems, confirm, _, _ = run(m)
        found = "\n".join(confirm)
        self.assertEqual(problems, [])
        self.assertIn("`incident.customerid` can point at account or contact", found)
        self.assertIn("`incident` also has `primarycontactid` as lookup(s) to contact", found)
        self.assertIn("`incident`: no allowedFields", found)
        self.assertIn("`ec_placement`: read \"all\"", found)
        self.assertIn("lookup to contact (`ec_studentid`)", found)
        self.assertIn("`ec_placement`: no allowedFields", found)  # "*" is every column too
        self.assertIn("endpoint `open_case` has no writableFields", found)
        self.assertIn("endpoint `open_case` sets `primarycontactid` to the contact, but `incident` is read through `customerid`", found)
        self.assertIn("endpoint `move` lets the contact set `incident.primarycontactid`, a lookup to contact", found)
        self.assertIn("endpoint `flow` calls an outside URL", found)

    def test_what_the_app_uses_must_be_covered(self):
        m = {"entities": {"ec_placement": {"customerField": "ec_studentid", "read": "own", "create": False, "update": "none", "allowedFields": "ec_name"}},
             "endpoints": [{"id": "write_case", "type": "d365_direct", "entity": "incident", "writableFields": ["title"]}]}
        d = {"screens": [{"id": "cases", "entity": "incident", "actionEndpointIds": ["close_case"]},
                         {"id": "map", "type": "plugin", "entity": "ec_placement"}],
             "workflows": [{"id": "apply", "entity": "ec_placement", "submitEndpointId": "submit_placement"}]}
        found = "\n".join(run(m, d)[0])
        self.assertIn("`incident`: screen `cases` uses it, but the manifest has no policy for it", found)
        self.assertIn("endpoint `close_case`: screen `cases` calls it", found)
        self.assertIn("endpoint `submit_placement`: multi-step form `apply` calls it", found)
        self.assertIn("endpoint `write_case` writes to `incident`, which has no entity policy", found)

    def test_the_report_puts_problems_first(self):
        m = {"entities": {"incident": {"customerField": "ec_advisorid", "read": "own", "create": False, "update": "none"}}, "endpoints": []}
        text = assess.report(*run(m))
        self.assertLess(text.index("## Problems"), text.index("## To confirm"))
        self.assertLess(text.index("## To confirm"), text.index("## Entities"))
        self.assertIn("**1 problem(s), 1 to confirm.**", text)


if __name__ == "__main__":
    unittest.main()
