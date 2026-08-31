"""Deduplicated GitHub notifications; receives no OCI credentials."""

import json
import os
import re
import sys
import urllib.request

REPOSITORY = "tsuchiyatakahirolab/OCI-A1-Capacity-Watch"
TITLE = "OCI A1 capacity available — owner action required"
ALERT = "OCI watcher credential integrity — owner review required"
MARKER = "<!-- oci-a1-capacity-watch:v1 -->"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Issues:
    def __init__(self):
        if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
            raise ValueError("UNEXPECTED_REPOSITORY")
        self.token = os.environ["GH_TOKEN"]
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, suffix, data=None):
        if not ((method == "GET" and re.fullmatch(r"/issues\?state=open&per_page=100&page=[1-9][0-9]?", suffix))
                or (method == "POST" and suffix == "/issues" and isinstance(data, dict)
                    and data.get("title") in (TITLE, ALERT))):
            raise ValueError("ISSUE_OPERATION_NOT_ALLOWLISTED")
        req = urllib.request.Request("https://api.github.com/repos/" + REPOSITORY + suffix,
                                     data=None if data is None else json.dumps(data).encode(), method=method,
                                     headers={"Authorization": "Bearer " + self.token,
                                              "Accept": "application/vnd.github+json",
                                              "X-GitHub-Api-Version": "2022-11-28"})
        with self.opener.open(req, timeout=20) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000 or response.status not in (200, 201):
                raise ValueError("ISSUE_RESPONSE_BOUND")
            return json.loads(raw)


def notify(result, issues):
    state = result.get("state")
    if state not in ("AVAILABLE", "OCI_WATCHER_CREDENTIAL_INTEGRITY_ALERT"):
        return "NO_NOTIFICATION"
    title = TITLE if state == "AVAILABLE" else ALERT
    for page in range(1, 11):
        rows = issues.request("GET", f"/issues?state=open&per_page=100&page={page}")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("ISSUE_SCHEMA_CHANGED")
        if any(row.get("title") == title and "pull_request" not in row
               and MARKER in (row.get("body") or "")
               and row.get("user", {}).get("login") == "github-actions[bot]" for row in rows):
            return "EXISTING_OPEN_NOTIFICATION"
        if len(rows) < 100:
            break
    else:
        raise ValueError("ISSUE_PAGINATION_BOUND")
    # Construct from bounded fields only; never publish arbitrary provider/error strings.
    stamp = result.get("server_timestamp", result.get("checked_at", ""))
    if not isinstance(stamp, str) or not re.fullmatch(r"[0-9T:.+Z-]{10,40}", stamp):
        raise ValueError("INVALID_TIMESTAMP")
    meaning = ("CAPACITY_AVAILABLE_REQUIRES_ZERO_BILLING_REVALIDATION" if state == "AVAILABLE"
               else "OCI_WATCHER_CREDENTIAL_INTEGRITY_ALERT")
    body = (f"{MARKER}\n{meaning}\n\nTimestamp: {stamp}\nRegion: ap-osaka-1\n"
            "AD: fBdI:AP-OSAKA-1-AD-1\nShape: VM.Standard.A1.Flex\nOCPU: 2\nRAM: 4 GB\n"
            f"Capacity status: {'AVAILABLE' if state == 'AVAILABLE' else 'NOT_QUERIED'}\n\n"
            "No resource has been provisioned. Owner review and a separate zero-billing revalidation "
            "are required; this issue is not authorization to create resources.")
    issues.request("POST", "/issues", {"title": title, "body": body})
    return "NOTIFICATION_CREATED"


def main():
    try:
        print(notify(json.loads(os.environ["WATCH_RESULT"]), Issues()))
        return 0
    except Exception:  # noqa: BLE001 - do not log authenticated HTTP exception details.
        print("NOTIFICATION_FAILED_NO_RETRY")
        return 1


if __name__ == "__main__":
    sys.exit(main())
