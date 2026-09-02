# OCI A1 Capacity Watch

A small, public, zero-billing GitHub Actions watcher. It reports capacity;
it **does not provision anything**. No MGRB/GFW data or collector runtime lives here.

## Fixed request

Region `ap-osaka-1`, availability domain `fBdI:AP-OSAKA-1-AD-1`,
shape `VM.Standard.A1.Flex`, **2 OCPU / 4 GB RAM**, root compartment supplied as a secret.
The only infrastructure-service call is `POST /20160918/computeCapacityReports`.
One bounded request per execution, no automatic retry, 20-second network timeout.
Before it, one read of the dedicated user's API-key metadata checks exactly one expected key.

`OUT_OF_HOST_CAPACITY` is ordinary successful waiting, not an error. `availableCount: null`
remains null, not zero. Logs contain a compact sanitized status, server time and response hash;
no raw OCI response or artifact upload is needed. Run history is the WAIT history.

`AVAILABLE` creates one open GitHub Issue, deduplicated against an existing bot-created
notification. It means **CAPACITY_AVAILABLE_REQUIRES_ZERO_BILLING_REVALIDATION**, not
authorization to create a VM. Owner review must separately revalidate non-PAYG status,
Always Free allowance, other usage, storage, networking and exactly-zero charges.
Authentication, transport and schema errors fail closed. An unexpected API-key inventory
stops capacity queries and produces `OCI_WATCHER_CREDENTIAL_INTEGRITY_ALERT`.

## Execution and zero billing

Only standard **public-repository GitHub-hosted `ubuntu-24.04`** runners are used.
No private metered runner, larger runner, paid service, artifact/cache upload, Codespace,
OCI VM, reservation, storage, network or subscription operation is used.
Dependencies are wheel-hash-pinned for CPython 3.12 on Linux x86_64.
First-party Actions are commit-pinned. No third-party Actions are needed.

Production runs only on the protected default `main` branch via `workflow_dispatch`, either from
the bounded Cloudflare clock or by explicit owner action.
The `oci-watch` environment accepts only `main`. PR verification is offline and has no OCI
secrets. Default token permission is `contents: read`; only the notification job receives
`issues: write`, and that job receives no OCI credentials.

The workflow concurrency group allows at most one active run and cancels an overlapping
older execution. A canceled execution is never automatically retried; if its request already
reached OCI, that reporting-only observation cannot be recalled. Every execution still has
its own hard one-query bound. No catch-up or retry loop exists.

The primary clock is a Workers Free SQLite Durable Object Alarm at nominal minute `:17 UTC`.
It invokes this workflow through `workflow_dispatch`. The former GitHub `schedule` trigger was
removed only after one real Alarm produced exactly one successful capacity report. The OCI request
code and permissions are unchanged. Durable SQLite state keeps the first 72 dispatch records so
the initial 24-hour timeliness window remains auditable without artifact uploads.

## Owner operations

1. Inspect **Actions → OCI A1 capacity watch** and confirm recent successful WAIT runs.
2. A failed run needs inspection; never automatically replace the credential or retry it.
3. On an availability Issue, separately revalidate zero billing before any owner-authorized VM work.
4. On credential-integrity alert, stop the workflow and have the owner inspect/revoke unexpected
   keys using their administrative context. The watcher never manages keys itself.
5. Inspect the Cloudflare Alarm state and GitHub `workflow_dispatch` history when monitoring
   timeliness; there is no GitHub cron fallback that can create duplicate queries.
6. When changing code, use a PR with the required `tests` check; never put OCI secrets in PR jobs.
7. The old local capacity watcher is a manual fallback after online commissioning. Its code and
   SQLite history are retained. The independent local GFW collector remains authoritative.

Manual execution: `gh workflow run capacity-watch.yml --ref main --repo tsuchiyatakahirolab/OCI-A1-Capacity-Watch`

Offline validation: `python -m unittest discover -s tests -v`,
`python -m compileall -q watcher.py notify.py security_scan.py tests`,
`python security_scan.py`, `ruff check .`, `git diff --check`.
The public-source scanner examines tracked files, not secrets/environment/private workspaces.

## References

- [OCI core policy permission mappings](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm)
- [OCI own API-key upload capability](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/user/api-key/upload.html)
- [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

See [SECURITY.md](SECURITY.md) for the accepted residual capability and threat model.
