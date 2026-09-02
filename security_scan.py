"""Scan tracked public source only; never display matched secret content."""

import pathlib
import re
import subprocess
import sys


def main():
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    ).decode().split("\0")
    patterns = [rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                rb"ocid1\.(?:tenancy|user|compartment)\.[a-z0-9._-]{30,}",
                rb"[A-Za-z]:[/\\]Users[/\\]", rb"gh[pousr]_[A-Za-z0-9]{30,}",
                rb"github_pat_[A-Za-z0-9_]{30,}"]
    cloudflare_forbidden = [
        rb"OCI_(?:TENANCY|COMPARTMENT|USER)_OCID",
        rb"OCI_(?:FINGERPRINT|PRIVATE_KEY|REGION)",
        rb"computeCapacityReports",
    ]
    failures = []
    for name in filter(None, paths):
        path = pathlib.Path(name)
        content = path.read_bytes()
        if (path.suffix.lower() in {".pem", ".key", ".sqlite", ".sqlite3", ".db", ".csv", ".zip", ".gpkg"}
                or any(part in {".local", "browser-profile", "node_modules", ".env"} for part in path.parts)
                or any(re.search(pattern, content) for pattern in patterns)
                or (path.parts[0] == "cloudflare-scheduler"
                    and any(re.search(pattern, content) for pattern in cloudflare_forbidden))):
            failures.append(name)
    print("PUBLIC_SOURCE_SCAN_PASS" if not failures else "PUBLIC_SOURCE_SCAN_FAILED: " + ", ".join(failures))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
