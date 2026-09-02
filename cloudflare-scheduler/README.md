# Cloudflare Durable Alarm clock

This directory replaces only the unreliable GitHub scheduled-event clock. The chain is:

`Cloudflare Free SQLite Durable Object Alarm -> workflow_dispatch -> existing GitHub workflow -> OCI capacity report`

Cloudflare holds one fine-grained GitHub credential with access only to this repository and
`Actions: write`. It never receives OCI credentials. The production Worker has no route and its
fetch handler always returns 404. A secret-authenticated commissioning handler exists only long
enough to initialize and inspect the first real alarm; production is redeployed immediately after
that check with `workers_dev=false`, and the commissioning secret is deleted.

The singleton SQLite Durable Object claims each nominal hourly `:17 UTC` slot with a primary-key
insert before external I/O. Duplicate delivery cannot dispatch twice. A delayed alarm claims only
the current slot and schedules the next future `:17`; it never catches up missed hours. GitHub or
network failure is recorded as `DISPATCH_FAILED_*` and is not thrown for an immediate Alarm retry.

## Zero-billing boundary

Deployment is permitted only to an owner-verified Workers Free account. SQLite Durable Objects are
available on Workers Free; Free-limit exhaustion fails requests rather than upgrading the account.
Do not enable Workers Paid, Queues, Workflows, R2, paid fallback, or any OCI resource. The expected
cadence is roughly 24 Alarm invocations and 24 dispatch requests per day, far below documented Free
limits. This is a capacity watcher, not an SLA.

## Local checks

```text
npm ci
npm run check
npx wrangler deploy --dry-run --config wrangler.jsonc
npx wrangler deploy --dry-run --config wrangler.commission.jsonc
```

## Commissioning order

1. Verify the selected Cloudflare account is Workers Free.
2. Create a GitHub fine-grained token limited to this repository, `Actions: write` only (GitHub's
   implicit Metadata read is acceptable). Never paste it into a file or shell history.
3. Deploy the temporary commissioning entry point and enter both secrets without persisting their
   values to a file, shell history, report, or repository.
4. Call the exact authenticated initialize endpoint once. It schedules the first alarm for one
   minute later. Inspect the authenticated status endpoint and GitHub Actions run.
5. Confirm one dispatch, one OCI query, current expected `OUT_OF_HOST_CAPACITY`, and no Issue.
6. Deploy `wrangler.jsonc` (no public route), delete `COMMISSIONING_SECRET`, and verify fetch is 404.
7. Only then remove GitHub's `schedule` event in a reviewed change. Keep `workflow_dispatch`.
8. Record first-24-hour timings from the bounded Durable history, GitHub `created_at`, and existing
   OCI server timestamp. Stop if routine latency is still measured in hours.

Never deploy with a broad GitHub OAuth token. Never pass repository/workflow/ref through a request;
all three are fixed in source. See the repository `SECURITY.md` and `COMMISSIONING.md`.

Commissioning completed on 2026-09-02. The production Worker has no public route; only
`GITHUB_DISPATCH_TOKEN` remains as a Worker Secret. The former GitHub cron has been removed.
