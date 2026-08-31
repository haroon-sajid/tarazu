"use client";

/**
 * One source-document page with every extracted value drawn at its real
 * provenance coordinates — over the actual page image when the backend
 * serves it (`GET /v1/documents/{id}/pages/{page}`), and over a schematic
 * outline at true A4 aspect ratio when it cannot (fixture mode, or a page the
 * backend could not render). The highlights are bbox-shaped in normalised
 * 0..1 page space either way, so they stay valid on both renders.
 *
 * Nothing here computes anything: every rectangle comes from the provenance
 * the extraction produced, and the active highlight is presentation state.
 */

import * as React from "react";
import { getDocumentPageUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BoundingBox } from "@/lib/types";

export interface PageHighlight {
  id: string;
  bbox?: BoundingBox | number[] | null;
  snippet?: string | null;
  label: string;
}

function Highlights({
  highlights,
  activeId,
  onSelect,
}: {
  highlights: PageHighlight[];
  activeId: string | null;
  onSelect?: (id: string) => void;
}) {
  return (
    <>
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
    </>
  );
}

/** The outline-only render: ruled lines at A4 proportions. */
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
      {Array.from({ length: 18 }).map((_, index) => (
        <div
          key={index}
          className="absolute left-[8%] right-[8%] h-px bg-slate-100"
          style={{ top: `${8 + index * 5}%` }}
        />
      ))}
      <Highlights highlights={highlights} activeId={activeId} onSelect={onSelect} />
    </div>
  );
}

/**
 * The real page when the backend serves it, the schematic when it cannot.
 * Reports which it managed through `onRendered`, so a caption can say so.
 */
export function DocumentPage({
  documentId,
  page,
  highlights,
  activeId,
  onSelect,
  onRendered,
}: {
  documentId: string;
  page: number;
  highlights: PageHighlight[];
  activeId: string | null;
  onSelect?: (id: string) => void;
  onRendered?: (mode: "image" | "schematic") => void;
}) {
  // undefined: loading; null: the backend has no image for this page.
  const [src, setSrc] = React.useState<string | null | undefined>(undefined);

  React.useEffect(() => {
    let cancelled = false;
    setSrc(undefined);
    getDocumentPageUrl(documentId, page)
      .then((url) => {
        if (cancelled) return;
        setSrc(url);
        onRendered?.(url ? "image" : "schematic");
      })
      .catch(() => {
        if (cancelled) return;
        setSrc(null);
        onRendered?.("schematic");
      });
    return () => {
      cancelled = true;
    };
    // onRendered is a reporting callback; re-fetching on its identity would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, page]);

  if (src === undefined) {
    return (
      <div
        className="w-full animate-pulse rounded-md border border-slate-200 bg-slate-100"
        style={{ aspectRatio: "1 / 1.414" }}
        aria-busy
        aria-label="Loading the page"
      />
    );
  }
  if (src === null) {
    return <SchematicPage highlights={highlights} activeId={activeId} onSelect={onSelect} />;
  }
  return (
    <div className="relative w-full overflow-hidden rounded-md border border-slate-300 bg-white shadow-inner">
      {/* The image sets the box; the highlights are percentages of it. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={`${documentId}, page ${page}`}
        className="block h-auto w-full select-none"
        draggable={false}
      />
      <Highlights highlights={highlights} activeId={activeId} onSelect={onSelect} />
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
