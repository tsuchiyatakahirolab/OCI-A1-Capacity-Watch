import { env } from "cloudflare:workers";
import { runDurableObjectAlarm } from "cloudflare:test";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import worker from "../src/index";
import { network } from "./network";

async function initialize(): Promise<DurableObjectStub> {
  const id = env.CAPACITY_CLOCK.newUniqueId();
  const stub = env.CAPACITY_CLOCK.get(id);
  const response = await stub.fetch("https://clock.internal/initialize", { method: "POST" });
  expect(response.status).toBe(200);
  return stub;
}

describe("capacity clock", () => {
  it("has no public control surface", async () => {
    const response = worker.fetch();
    expect(response.status).toBe(404);
  });

  it("dispatches once and atomically suppresses a duplicate alarm", async () => {
    let outbound = 0;
    let capturedBody: unknown;
    let capturedAuthorization: string | null = null;
    network.use(
      http.post(
        "https://api.github.com/repos/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/workflows/capacity-watch.yml/dispatches",
        async ({ request }) => {
          outbound += 1;
          capturedAuthorization = request.headers.get("Authorization");
          capturedBody = await request.json();
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );
    const stub = await initialize();

    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect(outbound).toBe(1);
    expect(capturedAuthorization).toBe("Bearer test-only-dispatch-secret");

    const body = capturedBody as { ref: string; inputs: { nominal_slot: string } };
    expect(body.ref).toBe("main");
    expect(new Date(body.inputs.nominal_slot).getUTCMinutes()).toBe(17);
    expect(Date.parse(body.inputs.nominal_slot)).toBeLessThanOrEqual(Date.now());
    expect(Object.keys(body).sort()).toEqual(["inputs", "ref"]);

    const status = await stub.fetch("https://clock.internal/status");
    const data = (await status.json()) as {
      state: { dispatch_count: number; last_dispatch_result: string };
      history: unknown[];
    };
    expect(data.state.dispatch_count).toBe(1);
    expect(data.state.last_dispatch_result).toBe("DISPATCH_ACCEPTED");
    expect(data.history).toHaveLength(1);
  });

  it("records a rejected dispatch without throwing or retrying", async () => {
    const before = Date.now();
    let outbound = 0;
    network.use(
      http.post(
        "https://api.github.com/repos/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/workflows/capacity-watch.yml/dispatches",
        () => {
          outbound += 1;
          return new HttpResponse(null, { status: 403 });
        },
      ),
    );
    const stub = await initialize();

    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect(outbound).toBe(1);
    const status = await stub.fetch("https://clock.internal/status");
    const data = (await status.json()) as {
      state: { last_dispatch_result: string; next_alarm_ms: number };
    };
    expect(data.state.last_dispatch_result).toBe("DISPATCH_FAILED_HTTP");
    expect(data.state.next_alarm_ms).toBeGreaterThan(before);
    expect(data.state.next_alarm_ms).toBeLessThanOrEqual(before + 60 * 60 * 1000);
  });

  it("records a network failure and consumes the slot without retry", async () => {
    let outbound = 0;
    network.use(
      http.post(
        "https://api.github.com/repos/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/workflows/capacity-watch.yml/dispatches",
        () => {
          outbound += 1;
          return HttpResponse.error();
        },
      ),
    );
    const stub = await initialize();

    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect(await runDurableObjectAlarm(stub)).toBe(true);
    expect(outbound).toBe(1);
    const status = await stub.fetch("https://clock.internal/status");
    const data = (await status.json()) as {
      state: { dispatch_count: number; last_dispatch_result: string };
    };
    expect(data.state.dispatch_count).toBe(1);
    expect(data.state.last_dispatch_result).toBe("DISPATCH_FAILED_NETWORK");
  });
});
