# Commissioning evidence — 2026-08-31

The dedicated identity and manual online execution passed before this change enabled
hourly scheduling. No instance, reservation, volume, network or billing mutation was sent.
The only created OCI objects were the explicitly owner-authorized IAM user, group,
membership, narrowly scoped policy and one public API key.

## Identity boundary

- User: `MGRBCapacityWatcher`; sole group: `MGRBCapacityWatchers`; group members: one.
- Policy: `Allow group MGRBCapacityWatchers to manage compute-capacity-reports in tenancy`.
- Policy-granted resource permission: `COMPUTE_CAPACITY_REPORT_CREATE` only.
- Accepted separate residual: `OCI_INHERENT_SELF_API_KEY_MANAGEMENT`, as explained in SECURITY.md.
- All compartment policies and memberships were inspected. Safe negative authorization
  evidence is the effective-policy model, not dangerous live create/delete probes.
- One API key registered; expected fingerprint verified by admin inspection and by the
  dedicated credential's own read-only metadata call. No credential mutation in runtime.
- Non-API credential capabilities disabled; no console password or other credentials created.
- Dedicated private key handed to the protected GitHub Actions environment secrets;
  restricted temporary local copy removed. The administrator key was never exported.

## Online execution

[Successful real manual run](https://github.com/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/runs/33358663472)
at commit `0dbe44175ca5429d0982316a7adc0fafa92eb176`:

- Standard public GitHub-hosted `ubuntu-24.04`; protected default branch `main`.
- 17 offline tests and the public-source scan passed before credentials were loaded.
- One own-key metadata GET, then **one** capacity-report POST; no retry.
- HTTP 200; `OUT_OF_HOST_CAPACITY`; `available_count: null` preserved.
- Server timestamp: `2026-08-31T04:54:16.790000+00:00` (13:54:16 JST).
- Response SHA-256: `cbdd94c8dff8700ed47ca18df423695d8fcd4495d757a9f5d17164daa5e44fe4`.
- Request: Osaka `ap-osaka-1`, `fBdI:AP-OSAKA-1-AD-1`, `VM.Standard.A1.Flex`, 2 OCPU, 4 GB.
- Notification job skipped; no Issue created; zero uploaded artifacts.
- Compute, reservation, volume, boot-volume, VCN, subnet, gateway, route-table, security-list
  and backup inventories matched the pre-commissioning snapshot. Existing AutoQuant/admin
  identity and resources were not modified.

[Offline CI verification](https://github.com/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/runs/33358613870)
also passed. Initial workflow YAML parsing failures happened before any runner/job or OCI
query; block-scalar syntax was corrected before the single real manual dispatch.

## Historical activation controls

The initial GitHub schedule used minute 17 every hour, UTC, on a best-effort basis. It was later
removed after the Durable Alarm cutover documented below. Runtime code remained unchanged from
the successful manual dispatch. Overlapping older workflow executions are canceled, not retried.
The enabling change passes the protected branch's `tests`
check through a PR. Workflow permissions are `contents: read`, plus `issues: write` only
on the separate notification job. The `oci-watch` environment allows only the `main` branch.
No secrets are available to PR verification.

The online workflow only detects capacity. Availability is not authorization to provision;
separate owner zero-billing revalidation remains necessary. No paid runner/service, artifact
storage, OCI infrastructure or credit-consuming resource was commissioned.

The previous local capacity watcher remains a manual fallback. Its automatic schedule is paused.
The separate local GFW collector remains unchanged and authoritative.

## Durable Alarm clock cutover — active 2026-09-02

The GitHub scheduled event was later measured at roughly 2.5–7.5-hour intervals. The replacement
clock is implemented under `cloudflare-scheduler/`. The cutover checks passed in this order:

1. selected Cloudflare account independently confirmed as Workers Free;
2. fine-grained GitHub credential limited to this repository and `Actions: write` only;
3. one real Alarm produces exactly one `workflow_dispatch` run and one OCI capacity report;
4. duplicate and delayed Alarm tests remain green and no catch-up burst occurs;
5. current result remains ordinary `OUT_OF_HOST_CAPACITY` with no Issue;
6. production Worker is redeployed without a route and the temporary commissioning secret deleted.

The first live Alarm claimed nominal slot `2026-09-02T09:17:00.000Z`, fired and sent the GitHub
request at `2026-09-02T09:49:25.602Z`, and received HTTP 204. Exactly one new
[`workflow_dispatch` run](https://github.com/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/runs/33616209925)
was created at `2026-09-02T09:49:26Z`; its capacity job started at `09:49:32Z`. The one OCI
capacity response had server timestamp `2026-09-02T09:49:38.411000+00:00` and completed with
HTTP 200, `OUT_OF_HOST_CAPACITY`, and `available_count: null`. The notification job was skipped,
open Issue count remained zero, and no OCI mutation occurred.

Alarm-to-workflow creation was about 0.4 seconds and Alarm-to-OCI server response about 12.8
seconds. The next future slot was set to `2026-09-02T10:17:00.000Z`; no missed-slot catch-up was
attempted. Durable SQLite history retains 72 slots, covering the required first 24-hour evidence
window. After the successful online check the production Worker was deployed with no route, the
commissioning secret was deleted, and a separate reviewed change removed GitHub `schedule:` while
retaining `workflow_dispatch`, concurrency, OCI semantics and existing notification behavior.
No OCI or billing resource was created during this cutover.

## 24-hour production audit and freeze — 2026-09-03

The first 24-hour commissioning window completed successfully. It contains the initial online
commissioning dispatch and 24 consecutive normal `:17 UTC` slots:

- 25 runs; 25 successful; zero failed, missing or duplicate nominal slots;
- normal Alarm delay from nominal slot: 20–472 ms;
- Alarm-to-OCI server response: 12.567–22.679 seconds;
- all 25 results: HTTP 200, `OUT_OF_HOST_CAPACITY`, `available_count: null`;
- zero open notification Issues and no OCI resource mutation;
- first run: https://github.com/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/runs/33616209925;
- final run inside the window: https://github.com/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/runs/33737974972.

The following `10:17 UTC` run also succeeded, confirming continued operation after the audit.
The owner accepted v2 as **PRODUCTION / FROZEN**. Do not change the scheduler, IAM, Cloudflare
Durable Object, GitHub workflow, OCI query semantics, or notification behavior unless A1 capacity
transitions to `AVAILABLE` or a real operational failure occurs. No further development or
monitoring-validation work is required while neither condition exists. This commissioning record
and the README owner runbook are permanent evidence and must be preserved.
