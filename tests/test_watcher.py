import ast
import copy
import io
import json
import pathlib
import re
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric import rsa

import notify
import watcher as w


def report(state="OUT_OF_HOST_CAPACITY", count=None):
    data = w.capacity_body("test-root")
    data["timeCreated"] = "2026-08-31T04:05:00.171Z"
    data["shapeAvailabilities"][0].update(availabilityStatus=state, availableCount=count)
    return data


class Response(io.BytesIO):
    status = 200

    def __init__(self, data, headers=None):
        super().__init__(json.dumps(data).encode())
        self.headers = headers or {}


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def client(self, result=None, keys=None):
        credential = w.Credential("test-root", "test-user", "test-fingerprint", self.key)
        opener = Mock()
        opener.open.side_effect = [Response(keys if keys is not None else [{"fingerprint": "test-fingerprint"}]),
                                   Response(report() if result is None else result)]
        return w.CapacityClient(credential, opener), opener

    def test_wait_and_repeated_wait_no_issue(self):
        issues = Mock()
        for _ in range(3):
            client, opener = self.client()
            result, code = w.run(client)
            self.assertEqual(code, 0)
            self.assertEqual(result["state"], "OUT_OF_HOST_CAPACITY")
            self.assertIsNone(result["available_count"])
            self.assertEqual(notify.notify(result, issues), "NO_NOTIFICATION")
            self.assertEqual(opener.open.call_count, 2)
        issues.request.assert_not_called()

    def test_available_once_and_deduplicated(self):
        client, _ = self.client(report("AVAILABLE", 1))
        result, code = w.run(client)
        self.assertEqual(code, 0)
        issues = Mock()
        issues.request.side_effect = [[], {}, [{"title": notify.TITLE, "body": notify.MARKER,
                                               "user": {"login": "github-actions[bot]"}}]]
        self.assertEqual(notify.notify(result, issues), "NOTIFICATION_CREATED")
        self.assertEqual(notify.notify(result, issues), "EXISTING_OPEN_NOTIFICATION")
        self.assertEqual(sum(c.args[0] == "POST" for c in issues.request.call_args_list), 1)

    def test_available_nullable_count(self):
        result = w.parse_capacity(report("AVAILABLE", None), {})
        self.assertIsNone(result["available_count"])

    def test_count_and_status_contradictions(self):
        for state, count in [("AVAILABLE", 0), ("OUT_OF_HOST_CAPACITY", 1),
                             ("OTHER", None), ("AVAILABLE", True), ("AVAILABLE", -1),
                             ("AVAILABLE", "1")]:
            with self.subTest(state=state, count=count), self.assertRaises(w.Fault):
                w.parse_capacity(report(state, count), {})

    def test_schema_fail_closed(self):
        cases = [None, {}, [], {"availabilityDomain": w.AD}]
        for key in ("timeCreated", "shapeAvailabilities", "availabilityDomain"):
            data = report()
            del data[key]
            cases.append(data)
        data = report()
        data["shapeAvailabilities"][0]["instanceShapeConfig"]["memoryInGBs"] = 24
        cases.append(data)
        data = report()
        data["timeCreated"] = "2026-08-31T00:00:00"
        cases.append(data)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(w.Fault):
                w.parse_capacity(data, {})

    def test_compartment_mismatch(self):
        data = report()
        data["compartmentId"] = "other"
        result, code = w.run(self.client(data)[0])
        self.assertEqual((code, result["state"]), (1, "UNEXPECTED_RESPONSE"))

    def test_extra_missing_wrong_keys_stop_before_capacity(self):
        for keys in ([], [{"fingerprint": "wrong"}], [{"fingerprint": "test-fingerprint"}] * 2,
                     [{"fingerprint": "test-fingerprint", "lifecycleState": "DELETED"}], {}):
            client, opener = self.client(keys=keys)
            result, code = w.run(client)
            self.assertEqual((code, result["state"]), (1, "OCI_WATCHER_CREDENTIAL_INTEGRITY_ALERT"))
            self.assertEqual(opener.open.call_count, 1)
            self.assertFalse(client.capacity_called)

    def test_http_errors_sanitized_no_retry(self):
        for code in (401, 403, 404, 429, 500):
            client, opener = self.client()
            opener.open.side_effect = [Response([{"fingerprint": "test-fingerprint"}]),
                                      urllib.error.HTTPError("secret-url", code, "secret-body", {}, None)]
            result, status = w.run(client)
            self.assertEqual(status, 1)
            self.assertEqual(result["state"], "AUTH_REQUIRED" if code in (401, 403) else "QUERY_FAILED")
            self.assertNotIn("secret", json.dumps(result))
            self.assertTrue(client.capacity_called)
            with self.assertRaises(w.Fault):
                client._request("iaas", "POST", w.CAPACITY_PATH, w.capacity_body("test-root"))
            self.assertEqual(opener.open.call_count, 2)

    def test_methods_paths_bodies_rejected_before_network(self):
        client, opener = self.client()
        client.key_checked = True
        forbidden = ["/20160918/instances", "/20160918/computeCapacityReservations", "/20160918/volumes",
                     "/20160918/vcns", "/20160918/users", "/20160918/groups", "/20160918/policies",
                     "/20160918/users/test-user/apiKeys"]
        for service in ("iaas", "identity", "other"):
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                for path in forbidden:
                    with self.assertRaises(w.Fault):
                        client._request(service, method, path, {})
        for body in ({}, w.capacity_body("other")):
            with self.assertRaises(w.Fault):
                client._request("iaas", "POST", w.CAPACITY_PATH, body)
        opener.open.assert_not_called()

    def test_no_capacity_before_integrity_or_twice(self):
        client, opener = self.client()
        with self.assertRaises(w.Fault):
            client._request("iaas", "POST", w.CAPACITY_PATH, w.capacity_body("test-root"))
        client.query()
        with self.assertRaises(w.Fault):
            client.query()
        self.assertEqual(opener.open.call_count, 2)

    def test_runtime_has_no_iam_mutation_code(self):
        source = pathlib.Path(w.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        methods = [x for x in literals if x in ("GET", "POST", "PUT", "PATCH", "DELETE")]
        self.assertEqual(set(methods), {"GET", "POST"})
        for name in ("upload_api_key", "delete_api_key", "UploadApiKey", "DeleteApiKey", "LaunchInstance",
                     "create_volume", "create_vcn", "IdentityClient", "ComputeClient", "subprocess", "eval("):
            self.assertNotIn(name, source)
        self.assertEqual({x for x in literals if x.startswith("/20160918/")},
                         {w.CAPACITY_PATH, "/20160918/users/"})

    def test_redirect_and_pagination_rejected(self):
        self.assertIsNone(w.NoRedirect().redirect_request(None, None, 302, None, None, "https://example.com"))
        client, opener = self.client()
        opener.open.side_effect = [Response([], {"opc-next-page": "next"})]
        result, status = w.run(client)
        self.assertEqual(status, 1)
        self.assertEqual(result["reason"], "RESPONSE_BOUND_OR_STATUS")
        self.assertEqual(opener.open.call_count, 1)

    def test_issue_list_failure_no_create(self):
        issues = Mock()
        issues.request.side_effect = ValueError("no access")
        with self.assertRaises(ValueError):
            notify.notify({"state": "AVAILABLE"}, issues)
        self.assertEqual(issues.request.call_count, 1)

    def test_integrity_alert_one_issue(self):
        issues = Mock()
        issues.request.side_effect = [[], {}]
        notify.notify({"state": "OCI_WATCHER_CREDENTIAL_INTEGRITY_ALERT",
                       "checked_at": "2026-08-31T01:00:00+00:00"}, issues)
        self.assertEqual(issues.request.call_args.args[2]["title"], notify.ALERT)

    def test_request_is_exact(self):
        client, opener = self.client()
        client.query()
        request = opener.open.call_args_list[-1].args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.full_url, "https://iaas.ap-osaka-1.oraclecloud.com" + w.CAPACITY_PATH)
        self.assertEqual(json.loads(request.data), w.capacity_body("test-root"))
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 20)
        self.assertEqual(copy.deepcopy(json.loads(request.data))["shapeAvailabilities"][0]
                         ["instanceShapeConfig"], {"ocpus": 2, "memoryInGBs": 4})

    def test_job_output_does_not_contain_secret_region_value(self):
        result = w.parse_capacity(report("AVAILABLE", 1), {})
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / "output"
            with patch.dict(w.os.environ, {"GITHUB_OUTPUT": str(target)}), \
                    patch.object(w.Credential, "environment", return_value=None), \
                    patch.object(w, "run", return_value=(result, 0)), patch("builtins.print"):
                self.assertEqual(w.main(), 0)
            contents = target.read_text()
            self.assertNotIn(w.REGION, contents)
            self.assertIn("state=AVAILABLE\n", contents)
            decoded = json.loads(contents.split("result=", 1)[1])
            self.assertEqual(decoded["state"], "AVAILABLE")

    def test_workflow_security_contract(self):
        root = pathlib.Path(w.__file__).parent
        production = (root / ".github/workflows/capacity-watch.yml").read_text()
        verification = (root / ".github/workflows/verify.yml").read_text()
        for guard in ("github.ref == 'refs/heads/main'", "github.ref_protected",
                      "github.event.repository.default_branch == 'main'",
                      "!github.event.repository.private", "environment: oci-watch"):
            self.assertIn(guard, production)
        self.assertNotIn("secrets.", verification)
        self.assertNotIn("pull_request_target", production + verification)
        self.assertEqual(production.count("issues: write"), 1)
        capacity, notification = production.split("  notify:", 1)
        self.assertNotIn("issues: write", capacity)
        self.assertNotIn("secrets.OCI_", notification)
        self.assertEqual(set(re.findall(r"runs-on: (.+)", production + verification)), {"ubuntu-24.04"})
        for action in re.findall(r"uses: (.+)", production + verification):
            self.assertRegex(action, r"^actions/(checkout|setup-python)@[a-f0-9]{40}$")
        for forbidden in ("upload-artifact", "actions/cache", "self-hosted", "write-all", "secrets: inherit"):
            self.assertNotIn(forbidden, production + verification)
        for command in re.findall(r"^\s+- run: (.+)$", production + verification, re.MULTILINE):
            self.assertNotIn(": ", command, "Use block scalars for commands containing YAML mapping syntax")


if __name__ == "__main__":
    unittest.main()
