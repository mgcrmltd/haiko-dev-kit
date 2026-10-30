"""crm.py keeps two promises: it never writes to the CRM, and it never reads
record contents. Run: python -m unittest discover -s scripts/tests  (python3 on macOS)"""

import json
import re
import sys
import types
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import crm  # noqa: E402
import kit  # noqa: E402

# The allow-list is the promise. Adding to it should be a decision, so it is pinned here.
EXPECTED_ALLOWED = {"WhoAmI", "RetrieveTotalRecordCount", "EntityDefinitions", "GlobalOptionSetDefinitions",
                    "solutions", "solutioncomponents", "workflows", "sdkmessageprocessingsteps"}

CANNED = {"value": [], "LogicalName": "incident", "EntitySetName": "incidents", "PrimaryIdAttribute": "incidentid",
          "PrimaryNameAttribute": "title", "IsCustomEntity": False, "UserId": "u", "OrganizationId": "o",
          "EntityRecordCountCollection": {"Keys": ["incident"], "Values": [3]}}


class FakeDataverse(crm.Dataverse):
    def __init__(self):  # no az, no network
        self.org = "https://example.crm11.dynamics.com"
        self._token = "test"


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body=None):
        self.calls.append((method, url, body))
        return 200, CANNED


class ReadOnly(unittest.TestCase):
    def setUp(self):
        self.recorder = Recorder()
        self._real = kit.http_json
        kit.http_json = self.recorder

    def tearDown(self):
        kit.http_json = self._real

    def run_command(self, fn, **args):
        defaults = {"custom": False, "solution": None, "entity": None, "all": False, "name": "incident", "names": ["incident"]}
        fn(FakeDataverse(), types.SimpleNamespace(**{**defaults, **args}))

    def every_command(self):
        for fn, args in ((crm.whoami, {}), (crm.solutions, {}), (crm.entities, {}), (crm.entities, {"custom": True}),
                         (crm.entity, {}), (crm.contact_paths, {}), (crm.processes, {}), (crm.processes, {"all": True}),
                         (crm.plugin_steps, {}), (crm.counts, {"names": ["incident", "contact"]})):
            self.run_command(fn, **args)
        return self.recorder.calls

    def test_the_allow_list_has_no_record_tables(self):
        self.assertEqual(crm.ALLOWED, EXPECTED_ALLOWED)

    def test_every_request_is_a_get_with_no_body(self):
        calls = self.every_command()
        self.assertGreater(len(calls), 10)
        for method, url, body in calls:
            self.assertEqual(method, "GET", url)
            self.assertIsNone(body, url)

    def test_every_request_goes_to_the_allow_list(self):
        for _method, url, _body in self.every_command():
            path = url.split(crm.API, 1)[1]
            target = re.split(r"[?(/]", path, maxsplit=1)[0]
            self.assertIn(target, EXPECTED_ALLOWED, url)

    def test_record_tables_are_refused(self):
        dv = FakeDataverse()
        for path in ("contacts", "incidents?$select=title", "accounts(00000000-0000-0000-0000-000000000000)", "ec_placements"):
            with self.assertRaises(PermissionError):
                dv.get(path)
        self.assertEqual(self.recorder.calls, [])

    def test_no_other_way_out(self):
        # The only HTTP in crm.py goes through Dataverse.get, which is GET-only.
        src = (SCRIPTS / "crm.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"kit\.http_json\(", src)), 1)
        self.assertRegex(src, r'kit\.http_json\("GET",')
        for forbidden in ("urllib.request", "http.client", "requests", "subprocess", '"POST"', '"PATCH"', '"PUT"', '"DELETE"'):
            self.assertNotIn(forbidden, src)


# Shapes taken from Empirical College's real definitions.
BPF = {"__class": "WorkflowStep:#x", "steps": {"list": [
    {"__class": "EntityStep:#x", "description": "incident", "steps": {"list": [
        {"__class": "StageStep:#x", "description": "Triage", "stageId": "a", "nextStageId": "b", "steps": {"list": [
            {"__class": "StepStep:#x", "isProcessRequired": True, "steps": {"list": [{"__class": "ControlStep:#x", "dataFieldName": "ec_category"}]}}]}}]}},
    {"__class": "EntityStep:#x", "description": "incident", "steps": {"list": [
        {"__class": "StageStep:#x", "description": "Close", "stageId": "c", "steps": {"list": [
            {"__class": "StepStep:#x", "steps": {"list": [{"__class": "ControlStep:#x", "dataFieldName": "ec_closedon"}]}}]}}]}},
    {"__class": "EntityStep:#x", "description": "incident", "steps": {"list": [
        {"__class": "StageStep:#x", "description": "Arrange", "stageId": "b", "nextStageId": "c", "steps": {"list": []}}]}},
]}}

FLOW = {"properties": {"definition": {
    "triggers": {"When a case is updated": {"type": "OpenApiConnectionWebhook", "inputs": {"parameters": {
        "subscriptionRequest/entityname": "incident", "subscriptionRequest/message": 3,
        "subscriptionRequest/filteringattributes": "statuscode, ec_closedon"}}}},
    "actions": {
        "Compose": {"type": "Compose", "inputs": "some text"},
        "Condition": {"type": "If", "actions": {
            "Update a row": {"type": "OpenApiConnection", "inputs": {"host": {"operationId": "UpdateRecord"},
                             "parameters": {"entityName": "incidents", "recordId": "@x", "item/ec_supportstartedon": "@now"}}}},
         "else": {"actions": {"Send": {"type": "OpenApiConnection", "inputs": {"host": {"operationId": "SendEmailV2"}}}}}},
    }}}}


class Parsers(unittest.TestCase):
    def test_bpf_stages_follow_next_stage_order(self):
        out = crm.bpf_stages(json.dumps(BPF))
        self.assertEqual([s["name"] for s in out["stages"]], ["Triage", "Arrange", "Close"])
        self.assertEqual(out["stages"][0]["fields"], [{"name": "ec_category", "required": True}])
        self.assertEqual(out["stages"][2]["entity"], "incident")
        self.assertFalse(out["branches"])

    def test_flow_trigger_and_effects(self):
        out = crm.flow_summary(json.dumps(FLOW))
        self.assertEqual(out["triggers"], [{"kind": "dataverse", "entity": "incident", "when": "update",
                                            "fields": ["statuscode", "ec_closedon"], "filter": None}])
        self.assertIn({"op": "UpdateRecord", "entity": "incidents", "fields": ["ec_supportstartedon"]}, out["effects"])
        self.assertIn({"op": "SendEmailV2"}, out["effects"])


if __name__ == "__main__":
    unittest.main()
