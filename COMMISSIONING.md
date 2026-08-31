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

## Activation controls

Schedule: minute 17 every hour, UTC, best effort. Runtime code is unchanged from the
successful manual dispatch. Overlapping older workflow executions are canceled, not retried.
The enabling change passes the protected branch's `tests`
check through a PR. Workflow permissions are `contents: read`, plus `issues: write` only
on the separate notification job. The `oci-watch` environment allows only the `main` branch.
No secrets are available to PR verification.

The online workflow only detects capacity. Availability is not authorization to provision;
separate owner zero-billing revalidation remains necessary. No paid runner/service, artifact
storage, OCI infrastructure or credit-consuming resource was commissioned.

GitHub can disable public schedules after 60 days of repository inactivity. Use the README
owner runbook; do not manufacture commits. The previous local capacity watcher remains a
manual fallback, while its automatic schedule is paused only after online activation is
verified. The separate local GFW collector remains unchanged and authoritative.
