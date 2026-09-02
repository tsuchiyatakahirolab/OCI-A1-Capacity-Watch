export const SLOT_MINUTE_UTC = 17;
export const HOUR_MS = 60 * 60 * 1000;

export function nominalSlotAt(nowMs: number): number {
  const now = new Date(nowMs);
  const slot = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
    now.getUTCHours(),
    SLOT_MINUTE_UTC,
  );
  return slot <= nowMs ? slot : slot - HOUR_MS;
}

export function nextNominalSlotAfter(nowMs: number): number {
  return nominalSlotAt(nowMs) + HOUR_MS;
}

export function iso(ms: number): string {
  return new Date(ms).toISOString();
}
