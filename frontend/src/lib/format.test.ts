import { describe, expect, it } from "vitest";
import {
  formatCompactNumber,
  formatDate,
  formatFileSize,
  formatMoney,
  formatMonth,
  formatPercent,
  formatTimestamp,
} from "./format";

/**
 * Display formatting is the one place the frontend touches a number, and it
 * must never change one: the same input renders the same text on every
 * machine, in UTC, with the separators an auditor expects.
 */
describe("formatMoney", () => {
  it("renders rupees with thousands separators and two decimals", () => {
    expect(formatMoney(284000)).toBe("PKR 284,000.00");
    expect(formatMoney(1500000.5)).toBe("PKR 1,500,000.50");
  });

  it("keeps a negative sign and honours another currency", () => {
    expect(formatMoney(-187500, "USD")).toBe("USD -187,500.00");
  });

  it("does not round away a value", () => {
    expect(formatMoney(0.005)).toBe("PKR 0.01");
    expect(formatMoney(0)).toBe("PKR 0.00");
  });
});

describe("formatDate and formatTimestamp", () => {
  it("renders an ISO date day-first with a short month, in UTC", () => {
    expect(formatDate("2026-06-02")).toBe("02 Jun 2026");
  });

  it("returns an unparseable date unchanged rather than 'Invalid Date'", () => {
    expect(formatDate("not a date")).toBe("not a date");
    expect(formatDate("")).toBe("");
  });

  it("renders a timestamp in UTC whatever the machine's zone", () => {
    expect(formatTimestamp("2026-06-19T09:41:07Z")).toBe("19 Jun 2026, 09:41 UTC");
    expect(formatTimestamp("2026-06-19T09:41:07+05:00")).toBe("19 Jun 2026, 04:41 UTC");
  });

  it("returns an unparseable timestamp unchanged", () => {
    expect(formatTimestamp("yesterday")).toBe("yesterday");
  });
});

describe("formatMonth", () => {
  it("renders a calendar month with a full or two-digit year", () => {
    expect(formatMonth("2026-01")).toBe("Jan 2026");
    expect(formatMonth("2026-01", "2-digit")).toBe("Jan 26");
  });

  it("returns a malformed month unchanged", () => {
    expect(formatMonth("not-a-month")).toBe("not-a-month");
    expect(formatMonth("")).toBe("");
  });
});

describe("compact numbers and percentages", () => {
  it("squeezes large numbers onto an axis", () => {
    expect(formatCompactNumber(35_500_000)).toBe("35.5M");
    expect(formatCompactNumber(412_500)).toBe("412.5K");
    expect(formatCompactNumber(12)).toBe("12");
  });

  it("renders a fraction as a percentage with the asked decimals", () => {
    expect(formatPercent(0.1234)).toBe("12.3%");
    expect(formatPercent(0.5, 0)).toBe("50%");
    expect(formatPercent(0)).toBe("0.0%");
  });
});

describe("formatFileSize", () => {
  it("picks the unit by size", () => {
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(1024)).toBe("1.0 KB");
    expect(formatFileSize(23_552)).toBe("23.0 KB");
    expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("handles zero", () => {
    expect(formatFileSize(0)).toBe("0 B");
  });
});
