"use client";

/**
 * A schematic rendering of one source-document page, with every extracted
 * value drawn at its real provenance coordinates. The backend does not serve
 * document files yet (`GET /v1/extractions/...` is "to be defined" in
 * docs/api-contracts.md), so the page is an outline at true A4 aspect ratio;
 * when a document URL exists this is where react-pdf slots in — the
 * highlights are already bbox-shaped and stay valid on a real render.
 *
 * Nothing here computes anything: every rectangle comes from the provenance
 * the extraction produced, and the active highlight is presentation state.
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import type { BoundingBox } from "@/lib/types";

export interface PageHighlight {
  id: string;
  bbox?: BoundingBox | number[] | null;
  snippet?: string | null;
  label: string;
}

export function SchematicPage({
  highlights,
  activeId,
  onSelect,
}: {
  highlights: PageHighlight[];
  activeId: string | null;
  onSelect?: (id: string) => void;
}) {
  return (
    <div
      className="relative w-full overflow-hidden rounded-md border border-slate-300 bg-white shadow-inner"
      style={{ aspectRatio: "1 / 1.414" }}
    >
      {/* Faint ruled lines to suggest the document body. */}
      {Array.from({ length: 18 }).map((_, index) => (
        <div
          key={index}
          className="absolute left-[8%] right-[8%] h-px bg-slate-100"
          style={{ top: `${8 + index * 5}%` }}
        />
      ))}
      {highlights.map((highlight) => {
        const active = highlight.id === activeId;
        if (highlight.bbox && highlight.bbox.length === 4) {
          const [x0, y0, x1, y1] = highlight.bbox;
          return (
            <button
              key={highlight.id}
              onClick={() => onSelect?.(highlight.id)}
              title={`${highlight.label}${highlight.snippet ? `: “${highlight.snippet}”` : ""}`}
              aria-label={`Highlight for ${highlight.label}`}
              className={cn(
                "absolute rounded-sm border-2 transition-colors",
                active
                  ? "z-10 border-amber-500 bg-amber-300/40"
                  : "border-brand-600/50 bg-brand-100/30 hover:border-brand-700 hover:bg-brand-100/50",
              )}
              style={{
                left: `${x0 * 100}%`,
                top: `${y0 * 100}%`,
                width: `${(x1 - x0) * 100}%`,
                height: `${(y1 - y0) * 100}%`,
              }}
            />
          );
        }
        // No usable box from the vision model — pin the snippet mid-page.
        return (
          <button
            key={highlight.id}
            onClick={() => onSelect?.(highlight.id)}
            className={cn(
              "absolute inset-x-[10%] top-[42%] rounded-sm px-2 py-1 text-center text-xs font-medium text-ink-900 transition-colors",
              active ? "z-10 bg-amber-300/50" : "bg-brand-100/40 hover:bg-brand-100/70",
            )}
          >
            {highlight.snippet ?? highlight.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The spreadsheet counterpart: the ledger is read directly by pandas, so its
 * provenance is a row number, not a page region. Rendered as a schematic
 * sheet with the referenced rows highlighted.
 */
export function SchematicSheet({
  rows,
  activeRow,
  onSelect,
}: {
  rows: { row: number; label: string }[];
  activeRow: number | null;
  onSelect?: (row: number) => void;
}) {
  const referenced = new Map(rows.map((entry) => [entry.row, entry.label]));
  const maxRow = Math.max(12, ...rows.map((entry) => entry.row));
  return (
    <div className="overflow-hidden rounded-md border border-slate-300 bg-white shadow-inner">
      <div className="grid grid-cols-[3rem_1fr] border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
        <span className="px-2 py-1.5 text-right">Row</span>
        <span className="px-3 py-1.5">Ledger entry</span>
      </div>
      {Array.from({ length: maxRow }, (_, index) => index + 1).map((row) => {
        const label = referenced.get(row);
        const active = row === activeRow;
        return (
          <button
            key={row}
            onClick={() => label && onSelect?.(row)}
            disabled={!label}
            className={cn(
              "grid w-full grid-cols-[3rem_1fr] border-b border-slate-100 text-left text-xs last:border-0",
              active
                ? "bg-amber-100"
                : label
                  ? "bg-brand-50/60 hover:bg-brand-50"
                  : "cursor-default",
            )}
          >
            <span className="px-2 py-1.5 text-right font-mono text-[10px] text-ink-400">
              {row}
            </span>
            <span className={cn("truncate px-3 py-1.5", label ? "text-ink-900" : "text-ink-400")}>
              {label ?? "·"}
            </span>
          </button>
        );
      })}
    </div>
  );
}
