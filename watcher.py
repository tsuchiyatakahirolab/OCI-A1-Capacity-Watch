"""Bounded OCI capacity reporting; no infrastructure or credential mutation."""

import base64
import email.utils
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

REGION = "ap-osaka-1"
AD = "fBdI:AP-OSAKA-1-AD-1"
SHAPE = "VM.Standard.A1.Flex"
CAPACITY_PATH = "/20160918/computeCapacityReports"
HOSTS = {"identity": f"identity.{REGION}.oraclecloud.com",
         "iaas": f"iaas.{REGION}.oraclecloud.com"}
MAX_BYTES = 2_000_000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def capacity_body(tenancy):
    return {"compartmentId": tenancy, "availabilityDomain": AD,
            "shapeAvailabilities": [{"instanceShape": SHAPE,
                                     "instanceShapeConfig": {"ocpus": 2, "memoryInGBs": 4}}]}


class Fault(Exception):
    """Only fixed, non-sensitive error codes may cross the transport boundary."""

    def __init__(self, state, code):
        self.state, self.code = state, code
        super().__init__(code)


@dataclass(repr=False)
class Credential:
    tenancy: str
    user: str
    fingerprint: str
    private_key: object = field(repr=False)

    @classmethod
    def environment(cls):
        try:
            values = {k: os.environ["OCI_" + k] for k in (
                "TENANCY_OCID", "COMPARTMENT_OCID", "USER_OCID", "FINGERPRINT",
                "PRIVATE_KEY", "REGION")}
            if (values["REGION"] != REGION or values["COMPARTMENT_OCID"] != values["TENANCY_OCID"]
                    or not re.fullmatch(r"ocid1\.tenancy\.[A-Za-z0-9._-]+", values["TENANCY_OCID"])
                    or not re.fullmatch(r"ocid1\.user\.[A-Za-z0-9._-]+", values["USER_OCID"])
                    or not re.fullmatch(r"(?:[0-9a-f]{2}:){15}[0-9a-f]{2}", values["FINGERPRINT"])):
                raise ValueError
            key = serialization.load_pem_private_key(values["PRIVATE_KEY"].encode(), password=None)
            if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
                raise ValueError
            der = key.public_key().public_bytes(serialization.Encoding.DER,
                                                serialization.PublicFormat.SubjectPublicKeyInfo)
            actual = ":".join(f"{b:02x}" for b in hashlib.md5(der, usedforsecurity=False).digest())
            if actual != values["FINGERPRINT"]:
                raise ValueError
            return cls(values["TENANCY_OCID"], values["USER_OCID"], actual, key)
        except Exception:  # noqa: BLE001 - secret-bearing parser exceptions must never escape.
            raise Fault("AUTH_REQUIRED", "CREDENTIAL_CONFIG_INVALID") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CapacityClient:
    def __init__(self, credential, opener=None):
        self.credential = credential
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
        self.key_checked = False
        self.capacity_called = False
        self.metadata_called = False

    def _sign(self, method, path, host, payload):
        headers = {"host": host, "date": email.utils.format_datetime(
            datetime.now(timezone.utc), usegmt=True)}
        if payload is not None:
            headers.update({"x-content-sha256": base64.b64encode(hashlib.sha256(payload).digest()).decode(),
                            "content-type": "application/json", "content-length": str(len(payload))})
        names = "(request-target) " + " ".join(headers)
        signing = f"(request-target): {method.lower()} {path}\n" + "\n".join(
            f"{k}: {v}" for k, v in headers.items())
        signature = base64.b64encode(self.credential.private_key.sign(
            signing.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()
        key_id = "/".join((self.credential.tenancy, self.credential.user, self.credential.fingerprint))
        headers["authorization"] = (f'Signature version="1",keyId="{key_id}",algorithm="rsa-sha256",'
                                    f'headers="{names}",signature="{signature}"')
        return headers

    def _request(self, service, method, path, body=None):
        # Exact method/path/body allowlist BEFORE signing or network I/O.
        if (service == "identity" and method == "GET"
                and path == f"/20160918/users/{self.credential.user}/apiKeys"
                and body is None and not self.metadata_called):
            self.metadata_called = True
        elif (service == "iaas" and method == "POST" and path == CAPACITY_PATH
              and body == capacity_body(self.credential.tenancy)
              and self.key_checked and not self.capacity_called):
            self.capacity_called = True  # Consume before I/O, even on failure. Never retry.
        else:
            raise Fault("QUERY_FAILED", "REQUEST_NOT_ALLOWLISTED")
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        req = urllib.request.Request("https://" + HOSTS[service] + path, data=payload,
                                     headers=self._sign(method, path, HOSTS[service], payload), method=method)
        try:
            with self.opener.open(req, timeout=20) as response:
                raw = response.read(MAX_BYTES + 1)
                if response.status != 200 or len(raw) > MAX_BYTES or response.headers.get("opc-next-page"):
                    raise Fault("QUERY_FAILED", "RESPONSE_BOUND_OR_STATUS")
                return json.loads(raw), {"http_status": response.status, "response_sha256": digest(raw)}
        except Fault:
            raise
        except urllib.error.HTTPError as exc:
            raise Fault("AUTH_REQUIRED" if exc.code in (401, 403) else "QUERY_FAILED", "OCI_HTTP_ERROR") from None
        except (ValueError, UnicodeError):
            raise Fault("UNEXPECTED_RESPONSE", "INVALID_JSON") from None
        except Exception:  # noqa: BLE001 - transport exceptions can contain signed request data.
            raise Fault("QUERY_FAILED", "TRANSPORT_ERROR") from None

    def check_key(self):
        keys, _ = self._request("identity", "GET", f"/20160918/users/{self.credential.user}/apiKeys")
        if (not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], dict)
                or keys[0].get("fingerprint") != self.credential.fingerprint
                or keys[0].get("lifecycleState", "ACTIVE") != "ACTIVE"):
            raise Fault("OCI_WATCHER_CREDENTIAL_INTEGRITY_ALERT", "KEY_INVENTORY_CHANGED")
        self.key_checked = True

    def query(self):
        self.check_key()
        data, evidence = self._request("iaas", "POST", CAPACITY_PATH, capacity_body(self.credential.tenancy))
        if not isinstance(data, dict) or data.get("compartmentId") != self.credential.tenancy:
            raise Fault("UNEXPECTED_RESPONSE", "COMPARTMENT_MISMATCH")
        return parse_capacity(data, evidence)


def parse_capacity(data, evidence):
    try:
        if data["availabilityDomain"] != AD or len(data["shapeAvailabilities"]) != 1:
            raise ValueError
        item = data["shapeAvailabilities"][0]
        config = item["instanceShapeConfig"]
        if (item["instanceShape"] != SHAPE or config["ocpus"] != 2 or config["memoryInGBs"] != 4
                or item.get("faultDomain") is not None):
            raise ValueError
        state, count = item["availabilityStatus"], item["availableCount"]
        if state not in ("AVAILABLE", "OUT_OF_HOST_CAPACITY"):
            raise ValueError
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError
        if state == "AVAILABLE" and count == 0 or state == "OUT_OF_HOST_CAPACITY" and count not in (None, 0):
            raise ValueError
        stamp = datetime.fromisoformat(data["timeCreated"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError
        return {"state": state, "available_count": count, "server_timestamp": stamp.isoformat(),
                "region": REGION, "ad": AD, "shape": SHAPE, "ocpus": 2, "memory_gb": 4,
                "credential_integrity": "ONE_EXPECTED_KEY", **evidence}
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        raise Fault("UNEXPECTED_RESPONSE", "CAPACITY_SCHEMA_CHANGED") from None


def run(client):
    try:
        return client.query(), 0
    except Fault as exc:
        return {"state": exc.state, "reason": exc.code}, 1
    except Exception:  # noqa: BLE001 - outer redaction boundary; fail closed, never retry.
        return {"state": "QUERY_FAILED", "reason": "INTERNAL_ERROR"}, 1


def main():
    try:
        result, status = run(CapacityClient(Credential.environment()))
    except Fault as exc:
        result, status = {"state": exc.state, "reason": exc.code}, 1
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    safe = json.dumps(result, separators=(",", ":"), sort_keys=True)
    print(safe)
    if os.environ.get("GITHUB_OUTPUT"):
        # Region is public/fixed but OCI_REGION is stored as an Actions secret. Do not
        # put its value in cross-job outputs: GitHub would suppress the whole output.
        job_result = {key: value for key, value in result.items() if key != "region"}
        job_json = json.dumps(job_result, separators=(",", ":"), sort_keys=True)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"state={result['state']}\nresult={job_json}\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
