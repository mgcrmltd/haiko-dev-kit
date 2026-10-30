"""manifest.py grants only what the app uses, and asks rather than guesses."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import manifest  # noqa: E402


def app(**extra):
    return {
        "screens": [
            {"type": "form", "id": "ask", "entity": "incident", "createEndpointIds": ["submit"], "updateEndpointIds": [],
             "fields": [{"name": "title", "crmField": True}, {"name": "ec_category", "crmField": True}, {"name": "ui_toggle", "crmField": False},
                        {"name": "ec_internalnote", "crmField": True, "showOnCreate": False, "showOnView": False}]},
            {"type": "list", "id": "mine", "entity": "incident", "customerField": "customerid", "titleField": "title", "detailScreenId": "one",
             "filter": "<filter><condition attribute='ec_category' operator='not-null' /></filter>"},
            {"type": "record", "id": "one", "entity": "incident", "titleField": "title",
             "fields": [{"name": "ec_reply", "crmField": True}, {"name": "ec_doc", "type": "file", "crmField": True}],
             "journey": {"stages": [
                 {"id": "a", "activeWhen": "statuscode == 1", "completeWhen": "hasValue(ec_closedon)", "message": "{ec_advisorid.name} has it",
                  "showFields": ["ec_reply", "ec_doc", "title"], "readOnlyFields": ["title"]},
                 {"id": "b", "activeWhen": "isTrue(ec_flag)", "completeWhen": "isTrue(ec_flag)", "action": {"type": "confirm", "endpointId": "confirm"}}]}},
        ],
        "workflows": [],
        "endpoints": [{"id": "submit", "type": "d365_direct", "uri": "incident"}, {"id": "confirm", "type": "d365_action", "uri": "ec_Confirm"},
                      {"id": "unused", "type": "d365_direct", "uri": "incident"}],
        **extra,
    }


class Propose(unittest.TestCase):
    def run_it(self, d=None, links=None, shared=(), existing=None):
        return manifest.propose(d or app(), dict(links or {}), set(shared), existing)

    def test_least_privilege(self):
        m, reasons, problems = self.run_it()
        self.assertEqual(problems, [])
        inc = m["entities"]["incident"]
        self.assertEqual((inc["customerField"], inc["read"], inc["create"], inc["update"]), ("customerid", "own", True, "own"))
        allowed = inc["allowedFields"].split(",")
        for f in ("title", "ec_category", "ec_reply", "ec_closedon", "ec_advisorid", "ec_flag", "statuscode"):
            self.assertIn(f, allowed)
        self.assertNotIn("ui_toggle", allowed, "screen-only fields aren't CRM columns")
        self.assertNotIn("ec_internalnote", allowed, "a field the app never shows isn't granted")
        eps = {e["id"]: e for e in m["endpoints"]}
        self.assertNotIn("unused", eps, "an endpoint the app doesn't call isn't granted")
        # creates with the form's CRM fields; journey edits save through it too (no form declares an update endpoint)
        self.assertEqual(eps["submit"]["writableFields"], ["ec_category", "ec_reply", "title"])
        self.assertEqual(eps["confirm"]["entity"], "incident")
        self.assertEqual(eps["confirm"]["action"], "ec_Confirm")

    def test_journey_edits_exclude_read_only_and_files(self):
        m, _, _ = self.run_it()
        writable = {e["id"]: e for e in m["endpoints"]}["submit"]["writableFields"]
        self.assertIn("ec_reply", writable)
        self.assertNotIn("ec_doc", writable, "files go by upload, never in a save")
        self.assertNotIn("ui_toggle", writable)

    def test_no_link_is_a_question_not_a_guess(self):
        d = app()
        d["screens"][1].pop("customerField")
        m, _, problems = self.run_it(d)
        self.assertNotIn("incident", m["entities"])
        self.assertTrue(any("--link incident=" in p for p in problems))
        m, _, problems = self.run_it(d, links={"incident": "ec_studentid"})
        self.assertEqual(m["entities"]["incident"]["customerField"], "ec_studentid")
        self.assertEqual(problems, [])

    def test_shared_content_is_read_all_and_nothing_else(self):
        d = app()
        d["screens"].append({"type": "list", "id": "news", "entity": "ec_news", "titleField": "ec_title", "detailScreenId": "x"})
        m, _, problems = self.run_it(d, shared={"ec_news"})
        self.assertEqual(m["entities"]["ec_news"], {"customerField": None, "read": "all", "create": False, "update": "none", "allowedFields": "ec_title"})
        self.assertEqual(problems, [])

    def test_existing_action_details_are_kept_and_dropped_endpoints_explained(self):
        existing = {"entities": {}, "endpoints": [{"id": "confirm", "type": "d365_action", "action": "ec_ConfirmV2", "fieldMappings": {"a": "A"}},
                                                  {"id": "old_thing", "type": "d365_direct", "entity": "contact"}]}
        m, reasons, _ = self.run_it(existing=existing)
        confirm = {e["id"]: e for e in m["endpoints"]}["confirm"]
        self.assertEqual((confirm["action"], confirm["fieldMappings"]), ("ec_ConfirmV2", {"a": "A"}))
        self.assertIn("left out", reasons["endpoint:old_thing"][0])


if __name__ == "__main__":
    unittest.main()
