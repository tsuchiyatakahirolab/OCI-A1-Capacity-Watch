import { CapacityWatchClock, type ClockEnv } from "./clock";

interface CommissionEnv extends ClockEnv {
  CAPACITY_CLOCK: DurableObjectNamespace;
  COMMISSIONING_SECRET: string;
}

export { CapacityWatchClock };

export function commissioningAuthorized(request: Request, expected: unknown): boolean {
  if (typeof expected !== "string" || expected.length < 32) {
    return false;
  }
  const supplied = request.headers.get("Authorization");
  return supplied !== null && supplied === `Bearer ${expected}`;
}

export default {
  async fetch(request: Request, env: CommissionEnv): Promise<Response> {
    if (!commissioningAuthorized(request, env.COMMISSIONING_SECRET)) {
      return new Response("Not found", { status: 404 });
    }
    const path = new URL(request.url).pathname;
    const id = env.CAPACITY_CLOCK.idFromName("singleton");
    const clock = env.CAPACITY_CLOCK.get(id);
    if (request.method === "POST" && path === "/__commission/initialize") {
      return clock.fetch("https://clock.internal/initialize", { method: "POST" });
    }
    if (request.method === "GET" && path === "/__commission/status") {
      return clock.fetch("https://clock.internal/status");
    }
    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<CommissionEnv>;
