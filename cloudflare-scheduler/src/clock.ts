import { DurableObject } from "cloudflare:workers";

import { iso, nextNominalSlotAfter, nominalSlotAt } from "./schedule";

const GITHUB_DISPATCH_URL =
  "https://api.github.com/repos/tsuchiyatakahirolab/OCI-A1-Capacity-Watch/actions/workflows/capacity-watch.yml/dispatches";
const GITHUB_API_VERSION = "2022-11-28";
const REQUEST_TIMEOUT_MS = 20_000;
const HISTORY_LIMIT = 72;

export function dispatchTokenValid(value: unknown): value is string {
  return typeof value === "string" && value.length >= 20;
}

export interface ClockEnv {
  GITHUB_DISPATCH_TOKEN: string;
}

interface ClockState extends Record<string, SqlStorageValue> {
  last_nominal_slot: number | null;
  last_dispatched_slot: number | null;
  next_alarm_ms: number | null;
  dispatch_count: number;
  last_dispatch_result: string | null;
}

export class CapacityWatchClock extends DurableObject<ClockEnv> {
  constructor(ctx: DurableObjectState, env: ClockEnv) {
    super(ctx, env);
    this.ctx.storage.sql.exec(`
      CREATE TABLE IF NOT EXISTS clock_state (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        last_nominal_slot INTEGER,
        last_dispatched_slot INTEGER,
        next_alarm_ms INTEGER,
        dispatch_count INTEGER NOT NULL DEFAULT 0,
        last_dispatch_result TEXT
      );
      INSERT OR IGNORE INTO clock_state (singleton, dispatch_count) VALUES (1, 0);
      CREATE TABLE IF NOT EXISTS dispatch_history (
        nominal_slot INTEGER PRIMARY KEY,
        alarm_fired_at INTEGER NOT NULL,
        dispatch_http_at INTEGER,
        dispatch_result TEXT NOT NULL,
        http_status INTEGER
      );
    `);
  }

  async alarm(): Promise<void> {
    await this.processAlarm(Date.now());
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/initialize") {
      return this.initialize();
    }
    if (request.method === "GET" && url.pathname === "/status") {
      return Response.json(this.status());
    }
    return new Response("Not found", { status: 404 });
  }

  private async initialize(): Promise<Response> {
    const existing = await this.ctx.storage.getAlarm();
    if (existing !== null) {
      return Response.json({ initialized: false, next_alarm_ms: existing });
    }
    const nextAlarmMs = Date.now() + 60_000;
    await this.ctx.storage.setAlarm(nextAlarmMs);
    this.ctx.storage.sql.exec(
      "UPDATE clock_state SET next_alarm_ms = ? WHERE singleton = 1",
      nextAlarmMs,
    );
    return Response.json({ initialized: true, next_alarm_ms: nextAlarmMs });
  }

  private status(): { state: ClockState; history: unknown[] } {
    const state = this.ctx.storage.sql
      .exec<ClockState>(
        `SELECT last_nominal_slot, last_dispatched_slot, next_alarm_ms,
                dispatch_count, last_dispatch_result
           FROM clock_state WHERE singleton = 1`,
      )
      .one();
    const history = Array.from(
      this.ctx.storage.sql.exec(
        `SELECT nominal_slot, alarm_fired_at, dispatch_http_at,
                dispatch_result, http_status
           FROM dispatch_history ORDER BY nominal_slot DESC LIMIT ?`,
        HISTORY_LIMIT,
      ),
    );
    return { state, history };
  }

  private async processAlarm(alarmFiredAt: number): Promise<void> {
    const nominalSlot = nominalSlotAt(alarmFiredAt);
    const nextAlarmMs = nextNominalSlotAfter(alarmFiredAt);

    // Arm the next future slot before external I/O. A delayed wake never replays
    // missed slots: it claims only the current nominal slot.
    await this.ctx.storage.setAlarm(nextAlarmMs);
    this.ctx.storage.sql.exec(
      "UPDATE clock_state SET last_nominal_slot = ?, next_alarm_ms = ? WHERE singleton = 1",
      nominalSlot,
      nextAlarmMs,
    );

    // The SQLite primary key is the durable, atomic per-slot claim. Once claimed,
    // a crash or duplicate alarm cannot produce a second dispatch for this slot.
    const claim = this.ctx.storage.sql.exec(
      `INSERT OR IGNORE INTO dispatch_history
         (nominal_slot, alarm_fired_at, dispatch_result)
       VALUES (?, ?, 'CLAIMED')`,
      nominalSlot,
      alarmFiredAt,
    );
    if (claim.rowsWritten !== 1) {
      return;
    }

    this.ctx.storage.sql.exec(
      `UPDATE clock_state
          SET last_dispatched_slot = ?, dispatch_count = dispatch_count + 1,
              last_dispatch_result = 'CLAIMED'
        WHERE singleton = 1`,
      nominalSlot,
    );

    if (!dispatchTokenValid(this.env.GITHUB_DISPATCH_TOKEN)) {
      const result = "DISPATCH_FAILED_CONFIGURATION";
      this.ctx.storage.sql.exec(
        "UPDATE dispatch_history SET dispatch_result = ? WHERE nominal_slot = ?",
        result,
        nominalSlot,
      );
      this.ctx.storage.sql.exec(
        "UPDATE clock_state SET last_dispatch_result = ? WHERE singleton = 1",
        result,
      );
      return;
    }

    const dispatchHttpAt = Date.now();
    let result = "DISPATCH_FAILED_NETWORK";
    let httpStatus: number | null = null;
    try {
      const response = await fetch(GITHUB_DISPATCH_URL, {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${this.env.GITHUB_DISPATCH_TOKEN}`,
          "Content-Type": "application/json",
          "User-Agent": "OCI-A1-Capacity-Watch-Clock/1.0",
          "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        body: JSON.stringify({
          ref: "main",
          inputs: {
            trigger: "cloudflare-durable-alarm",
            nominal_slot: iso(nominalSlot),
            alarm_fired_at: iso(alarmFiredAt),
            dispatch_http_at: iso(dispatchHttpAt),
          },
        }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      httpStatus = response.status;
      result = response.status === 204 ? "DISPATCH_ACCEPTED" : "DISPATCH_FAILED_HTTP";
      await response.body?.cancel();
    } catch {
      // Normal GitHub/network failures are durable state, not thrown alarm retries.
    }

    this.ctx.storage.sql.exec(
      `UPDATE dispatch_history
          SET dispatch_http_at = ?, dispatch_result = ?, http_status = ?
        WHERE nominal_slot = ?`,
      dispatchHttpAt,
      result,
      httpStatus,
      nominalSlot,
    );
    this.ctx.storage.sql.exec(
      "UPDATE clock_state SET last_dispatch_result = ? WHERE singleton = 1",
      result,
    );
  }
}
