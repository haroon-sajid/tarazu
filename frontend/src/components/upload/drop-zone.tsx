"use client";

import * as React from "react";
import { CheckCircle2, FileUp, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/format";

export function DropZone({
  label,
  hint,
  accept,
  multiple = false,
  files,
  onFiles,
  disabled,
}: {
  label: string;
  hint: string;
  /** Lowercase extensions with the dot, e.g. [".pdf"]. */
  accept: string[];
  multiple?: boolean;
  files: File[];
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const [rejected, setRejected] = React.useState<string | null>(null);

  const acceptFile = (file: File) =>
    accept.some((extension) => file.name.toLowerCase().endsWith(extension));

  const takeFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const list = Array.from(incoming);
    const good = list.filter(acceptFile);
    const bad = list.filter((file) => !acceptFile(file));
    setRejected(
      bad.length
        ? `${bad.map((f) => f.name).join(", ")} — accepted: ${accept.join(", ")}`
        : null,
    );
    if (!good.length) return;
    onFiles(multiple ? [...files, ...good] : [good[0]]);
  };

  const removeFile = (index: number) =>
    onFiles(files.filter((_, i) => i !== index));

  const hasFiles = files.length > 0;

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label={`Upload ${label}`}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (!disabled && (event.key === "Enter" || event.key === " "))
            inputRef.current?.click();
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          if (!disabled) takeFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors",
          dragOver
            ? "border-brand-600 bg-brand-50"
            : hasFiles
              ? "border-emerald-300 bg-emerald-50/40"
              : "border-slate-300 bg-white hover:border-brand-600/60 hover:bg-slate-50",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        {hasFiles ? (
          <CheckCircle2 className="h-7 w-7 text-emerald-600" aria-hidden />
        ) : (
          <FileUp className="h-7 w-7 text-ink-400" aria-hidden />
        )}
        <div>
          <p className="text-sm font-semibold text-ink-900">{label}</p>
          <p className="mt-0.5 text-xs text-ink-400">{hint}</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept={accept.join(",")}
          multiple={multiple}
          onChange={(event) => {
            takeFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {rejected && (
        <p className="mt-1.5 text-xs text-rose-600">Not accepted: {rejected}</p>
      )}

      {hasFiles && (
        <ul className="mt-2 space-y-1">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${index}`}
              className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs"
            >
              <span className="truncate font-medium text-ink-900">{file.name}</span>
              <span className="ml-2 flex shrink-0 items-center gap-2 text-ink-400">
                {formatFileSize(file.size)}
                {!disabled && (
                  <button
                    onClick={() => removeFile(index)}
                    className="rounded p-0.5 hover:bg-slate-100 hover:text-rose-600"
                    aria-label={`Remove ${file.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
