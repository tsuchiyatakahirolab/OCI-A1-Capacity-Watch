# Security boundary

Policy-granted OCI resource authority is limited to **COMPUTE_CAPACITY_REPORT_CREATE**.

```
Allow group MGRBCapacityWatchers to manage compute-capacity-reports in tenancy
```

Dedicated user `MGRBCapacityWatcher` belongs only to `MGRBCapacityWatchers`.
Commissioning audits all compartment policies and complete group memberships;
any unexpected policy/grant blocks credential deployment.
No Administrator membership, IAM-management, instance-family, capacity-reservation,
volume, networking or billing grant is allowed.

## Explicitly accepted platform residual

**OCI_INHERENT_SELF_API_KEY_MANAGEMENT**: OCI inherently permits a user to manage its
own API signing credentials. This is an owner-accepted platform-level residual capability,
separate from policy-granted resource authority. The principal does NOT literally have
only one possible OCI permission.

If the dedicated key is stolen, an attacker may retain access to **the same limited user**
by managing that user's API keys. That does not grant authority to create/mutate Compute,
Storage, Networking, IAM policies/group memberships or Billing resources. It is not zero
residual risk. Detection on the next normal run is not instantaneous and can be evaded by
an attacker with sufficiently privileged control of the workflow itself.

The watcher application **does not exercise IAM credential mutation**. It has no upload,
delete, or general IAM client. Its transport is limited to one own-key metadata GET and
one exact capacity-report POST; method/path/body guards execute before signing or I/O.
No resource-creation requests are sent as negative authorization tests: denial evidence
comes from the complete effective-policy inspection and documented permission mappings.

## Credentials

Exactly one new public signing key is registered at commissioning. The private key and
tenant/user/fingerprint configuration belong only in the protected `oci-watch` GitHub Actions
environment secrets. A temporary restricted local key, if used for setup, must be removed
after secret handoff verification. No admin key is reused or exported. No console password,
auth token, customer secret key, SMTP, DB or OAuth credential is created; unnecessary user
credential capabilities are disabled. Existing identities and AutoQuant resources are untouched.

Each run checks the expected fingerprint and key count. Extra/missing/changed keys or
unexpected lifecycle state prevent the capacity query. Failure to read key metadata also
fails closed; no broader permission is automatically granted.

## Public workflow trust

The protected default branch and `oci-watch` environment branch restriction guard secrets.
PR checks have no secrets, and production events are only schedule/manual on protected main.
The owner controls privileged merges and repository settings; GitHub-hosted runner and
dependency supply-chain trust remain part of the model. Actions and package wheel hashes
are pinned. No artifacts/caches are uploaded. Secrets exist in memory only on ephemeral runners.

The public source scanner rejects private keys, sensitive OCID-shaped values, tokens, local
owner paths, raw data formats and browser/profile state. It is a regression gate, not a proof
that every conceivable secret encoding is detectable. Review every proposed change.

GitHub Issue notifications are public and contain only bounded capacity facts. A failed Issue
write is not retried inside a run. Later availability runs can attempt notification again after
checking for an existing open bot notification. Credential failures do not silently reset state.

The online watcher never audits subscription/storage/billing using broader grants and never
claims capacity availability alone proves an Always Free VM can be created.
