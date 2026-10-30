"""crmcheck finds the CRM names an app gets wrong. Offline: the metadata is faked."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crmcheck  # noqa: E402

ENTITIES = {
    "incident": {"fields": [
        {"name": "title"}, {"name": "createdon"},
        {"name": "customerid", "targets": ["account", "contact"]},
        {"name": "ec_advisorid", "targets": ["systemuser"]},
        {"name": "ec_category", "options": [{"value": 1, "label": "Anxiety"}, {"value": 2, "label": "Money"}]},
        {"name": "statuscode", "options": [{"value": 1, "label": "In progress"}, {"value": 450000003, "label": "Choose"}]},
    ]},
}


class FakeMetadata(crmcheck.Metadata):
    def __init__(self):
        self.cache = dict(ENTITIES)

    def entity(self, name):
        return self.cache.get(name)


def definition(**screen):
    return {"screens": [{"id": "s", "entity": "incident", "fields": [], **screen}], "workflows": []}


class CrmCheck(unittest.TestCase):
    def problems(self, d=None, m=None):
        return crmcheck.check(FakeMetadata(), d, m)

    def test_a_correct_app_has_no_problems(self):
        d = definition(fields=[{"name": "ec_category", "options": [{"value": "1", "label": "Anxiety"}]}, {"name": "slot", "crmField": False}],
                       titleField="title", journey={"stages": [{"id": "a", "activeWhen": "statuscode == 450000003 AND isEmpty(ec_advisorid)",
                                                                "completeWhen": 'hasValue(ec_advisorid.name) OR contains(title, "x == 9")', "showFields": ["slot"]}]})
        m = {"entities": {"incident": {"customerField": "customerid", "read": "own", "allowedFields": "title,ec_category"}}, "endpoints": []}
        self.assertEqual(self.problems(d, m), [])

    def test_wrong_names_are_found(self):
        d = definition(fields=[{"name": "ec_catgory"}, {"name": "ec_category", "options": [{"value": "7", "label": "Housing"}]}],
                       journey={"stages": [{"id": "a", "activeWhen": "statuscode == 450000099", "completeWhen": "hasValue(ec_closedon)"}]})
        d["screens"].append({"id": "t", "entity": "ec_nosuchentity", "fields": []})
        found = "\n".join(self.problems(d))
        self.assertIn("has no field 'ec_catgory'", found)
        self.assertIn("option 7 ('Housing') isn't a value of incident.ec_category", found)
        self.assertIn("incident.statuscode has no option value 450000099", found)
        self.assertIn("has no field 'ec_closedon'", found)
        self.assertIn("entity 'ec_nosuchentity' doesn't exist", found)

    def test_customer_fields_must_be_lookups_to_contact(self):
        m = {"entities": {"incident": {"customerField": "ec_advisorid", "read": "own"}}, "endpoints": [
            {"id": "e", "type": "d365_direct", "entity": "incident", "customerField": "title", "writableFields": ["ec_nope"]}]}
        found = "\n".join(self.problems(None, m))
        self.assertIn("'ec_advisorid' isn't a lookup to contact", found)
        self.assertIn("customerField: 'title' isn't a lookup to contact", found)
        self.assertIn("has no field 'ec_nope'", found)

    def test_own_without_customer_field(self):
        found = self.problems(None, {"entities": {"incident": {"customerField": None, "read": "own"}}, "endpoints": []})
        self.assertTrue(any("no customerField" in p for p in found))


if __name__ == "__main__":
    unittest.main()
