const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

/** A step number from a URL segment: a plain integer from 1 to 1000, else null. */
export function parseStepNumber(value: unknown): number | null {
  if (typeof value !== "string" || !/^[0-9]{1,4}$/.test(value)) return null;
  const n = Number(value);
  return n >= 1 && n <= 1000 ? n : null;
}
