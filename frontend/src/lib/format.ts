/** Display formatting only. No arithmetic on audit data happens client-side. */

const pkrFormatter = new Intl.NumberFormat("en-PK", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** "PKR 284,000.00" — right-aligned money for the review table. */
export function formatMoney(amount: number, currency = "PKR"): string {
  return `${currency} ${pkrFormatter.format(amount)}`;
}

/** "02 Jun 2026" — compact and unambiguous for auditors. */
export function formatDate(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** "19 Jun 2026, 09:41 UTC" for audit-trail timestamps. */
export function formatTimestamp(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return isoTimestamp;
  return `${date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  })}, ${date.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  })} UTC`;
}

/** "Jan 2026" (or "Jan 26" for chart axes) for a `YYYY-MM` calendar month. */
export function formatMonth(
  month: string,
  yearStyle: "numeric" | "2-digit" = "numeric",
): string {
  const date = new Date(`${month}-01T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return month;
  return date.toLocaleDateString("en-GB", {
    month: "short",
    year: yearStyle,
    timeZone: "UTC",
  });
}

/** "35.5M" / "412.5k" — a number squeezed onto a chart axis. */
export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en-PK", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/** "PKR 35.5M" — money squeezed into a chart legend or tooltip. */
export function formatMoneyCompact(amount: number, currency = "PKR"): string {
  return `${currency} ${formatCompactNumber(amount)}`;
}

export function formatPercent(fraction: number, decimals = 1): string {
  return `${(fraction * 100).toFixed(decimals)}%`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
