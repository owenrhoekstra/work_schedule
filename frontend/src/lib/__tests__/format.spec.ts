import { describe, expect, it } from "vitest";
import { format12, formatDateMedium, formatDuration } from "@/lib/format";

describe("format12", () => {
  it("formats morning times with AM", () => {
    expect(format12("09:00")).toBe("9:00 AM");
    expect(format12("06:30")).toBe("6:30 AM");
    expect(format12("11:59")).toBe("11:59 AM");
  });

  it("formats afternoon times with PM", () => {
    expect(format12("13:00")).toBe("1:00 PM");
    expect(format12("17:30")).toBe("5:30 PM");
    expect(format12("23:59")).toBe("11:59 PM");
  });

  it("handles the 12 o'clock edges", () => {
    // 00:xx is 12:xx AM; 12:xx is 12:xx PM. Both are edge cases
    // where the naive `h % 12` produces 0.
    expect(format12("00:00")).toBe("12:00 AM");
    expect(format12("00:15")).toBe("12:15 AM");
    expect(format12("12:00")).toBe("12:00 PM");
    expect(format12("12:45")).toBe("12:45 PM");
  });

  it("has no leading zero on the hour", () => {
    expect(format12("09:00")).toBe("9:00 AM");
    expect(format12("08:05")).toBe("8:05 AM");
  });

  it("preserves minutes as-is (zero-padded)", () => {
    expect(format12("09:05")).toBe("9:05 AM");
    expect(format12("14:00")).toBe("2:00 PM");
  });
});

describe("formatDuration", () => {
  it("formats zero as 0h 00m", () => {
    expect(formatDuration(0)).toBe("0h 00m");
  });

  it("formats exact hours", () => {
    expect(formatDuration(60)).toBe("1h 00m");
    expect(formatDuration(480)).toBe("8h 00m");
    expect(formatDuration(2400)).toBe("40h 00m");
  });

  it("formats hours and minutes", () => {
    expect(formatDuration(30)).toBe("0h 30m");
    expect(formatDuration(90)).toBe("1h 30m");
    expect(formatDuration(495)).toBe("8h 15m");
    expect(formatDuration(2435)).toBe("40h 35m");
  });

  it("zero-pads single-digit minutes", () => {
    expect(formatDuration(5)).toBe("0h 05m");
    expect(formatDuration(65)).toBe("1h 05m");
  });

  it("handles negative durations (defensive)", () => {
    expect(formatDuration(-30)).toBe("-0h 30m");
    expect(formatDuration(-90)).toBe("-1h 30m");
  });

  it("handles durations above 24h", () => {
    expect(formatDuration(1500)).toBe("25h 00m");
    expect(formatDuration(3000)).toBe("50h 00m");
  });
});

describe("formatDateMedium", () => {
  it("formats standard dates", () => {
    expect(formatDateMedium("2026-11-16")).toBe("Nov 16, 2026");
    expect(formatDateMedium("2026-01-05")).toBe("Jan 5, 2026");
    expect(formatDateMedium("2026-12-31")).toBe("Dec 31, 2026");
  });

  it("does not drift to the previous day in negative-offset timezones", () => {
    // "2026-11-16" parsed with new Date("2026-11-16") would be UTC
    // midnight; in America/Toronto that's Nov 15 20:00, so
    // toLocaleDateString would report "Nov 15". The year/month/day
    // split in formatDateMedium constructs local midnight directly
    // and never drifts. This test pins that behavior.
    expect(formatDateMedium("2026-11-16")).toBe("Nov 16, 2026");
    expect(formatDateMedium("2026-01-01")).toBe("Jan 1, 2026");
  });

  it("handles leap-year February 29th", () => {
    expect(formatDateMedium("2028-02-29")).toBe("Feb 29, 2028");
  });

  it("does not zero-pad the day", () => {
    // "Jan 5" not "Jan 05" — Intl's short month/day format is
    // human-facing, not ISO-shaped.
    expect(formatDateMedium("2026-01-05")).toBe("Jan 5, 2026");
  });
});
