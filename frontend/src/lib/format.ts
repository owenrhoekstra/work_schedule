// Display formatting for the schedule view. Server sends raw data —
// "HH:MM" 24h times, minutes as integers, dates as ISO — because
// display concerns (12h/24h, h/m formatting, locale) are client-side.
// Keep these pure; no reactivity, no imports beyond what's used.

/**
 * Convert 24h "HH:MM" to 12h with AM/PM. Hour has no leading zero.
 *   09:00 → "9:00 AM"
 *   13:30 → "1:30 PM"
 *   00:00 → "12:00 AM"
 *   12:00 → "12:00 PM"
 *
 * Input is guaranteed "HH:MM" by the server schema; no defensive
 * parsing. Minutes optional in the split so tests don't have to
 * always include them, but production always sends them.
 */
export function format12(time24: string): string {
  // Defaults satisfy noUncheckedIndexedAccess; runtime always has both
  // parts because the schema guarantees "HH:MM".

  if (time24 === "") {
    return ``
  }
  
  const [hStr = "00", mStr = "00"] = time24.split(":");
  const h = parseInt(hStr, 10);
  const suffix = h < 12 ? "AM" : "PM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${mStr} ${suffix}`;
}

/**
 * Convert integer minutes to "Hh MMm". Handles 0, values > 24h, and
 * negative (shouldn't occur in practice; guarded for completeness).
 *   0    → "0h 00m"
 *   480  → "8h 00m"
 *   495  → "8h 15m"
 *   -30  → "-0h 30m"
 */
export function formatDuration(minutes: number): string {
  const sign = minutes < 0 ? "-" : "";
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return `${sign}${h}h ${String(m).padStart(2, "0")}m`;
}

/**
 * Format an ISO date "YYYY-MM-DD" as "Nov 16, 2026".
 *
 * Constructs the Date from year/month/day parts at LOCAL midnight
 * (not from a string, which would parse "2026-11-16" as UTC and
 * shift the day for negative-offset timezones). The displayed day
 * always matches the ISO date.
 */
export function formatDateMedium(iso: string): string {
  // Tuple cast: the schema guarantees "YYYY-MM-DD", so the map always
  // produces exactly three numbers. Casting sidesteps the
  // number-or-undefined union without runtime fallbacks that would
  // silently accept a malformed date.
  const [y, m, d] = iso.split("-").map(Number) as [number, number, number];
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
