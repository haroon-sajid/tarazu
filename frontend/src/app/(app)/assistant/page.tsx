"use client";

/**
 * Assistant — Ask Tarazu, about this case. The auditor asks in plain language
 * (English or Urdu); the backend understands the intent, runs the query in
 * deterministic code, words the result, and shows its sources. Answers carry
 * a confidence level, cite the document and page behind every claim, and
 * list the computed facts they were written from. Questions that cannot be
 * grounded are refused, not guessed at — reliability rule 7 rendered as UI.
 *
 * The composer takes more than typing: documents can be attached (paperclip)
 * and are acknowledged, never read — the assistant answers only from the
 * uploaded case; and questions can be spoken — the mic streams live
 * transcription into the input via the browser's own speech engine
 * (lib/speech.ts; English or Urdu, nothing leaves the browser until Send).
 *
 * Live mode calls `POST /v1/assistant/chat`; fixture mode composes from the
 * fixture items client-side (lib/assistant.ts). The screen renders both alike.
 */

import * as React from "react";
import Link from "next/link";
import {
  Calculator,
  FileText,
  Loader2,
  MessageSquare,
  Mic,
  Paperclip,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import {
  ApiError,
  askAssistant,
  FIXTURE_MODE,
  getDashboard,
  getReviewItems,
} from "@/lib/api";
import {
  attachmentKind,
  describeAttachments,
  type AssistantAttachment,
} from "@/lib/assistant";
import { isSpeechSupported, startRecognition, type Recognizer } from "@/lib/speech";
import type { AssistantAnswer, DashboardSummary, ReviewItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ConfidenceBadge } from "@/components/ui/badge";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  reply?: AssistantAnswer;
  attachments?: AssistantAttachment[];
}

const MAX_ATTACHMENTS = 5;

const ACCEPTED_FILES = ".pdf,.png,.jpg,.jpeg,.webp,.xlsx,.xls,.csv,.txt";

/** Voice recognition languages the composer offers, in toggle order. */
const VOICE_LANGS = [
  { code: "en-US", label: "EN" },
  { code: "ur-PK", label: "اردو" },
] as const;

function formatChipSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

const SUGGESTIONS = [
  "Match results",
  "Which invoices are in this case?",
  "What is in the bank statement?",
  "Which items are unmatched?",
  "What have we decided so far?",
  "What did the model read?",
  "What happened in this case?",
  "What is reconciliation?",
  "اردو میں خلاصہ دیں",
];

/** An answer built locally — for attachments-only turns and transport errors. */
function localAnswer(question: string, text: string, grounded: boolean): AssistantAnswer {
  return {
    question,
    language: "en",
    intent: grounded ? "help" : "unknown",
    text,
    answer_confidence: grounded ? "high" : "low",
    grounded,
    citations: [],
    facts: [],
    composed_by: "frontend",
  };
}

export default function AssistantPage() {
  const [items, setItems] = React.useState<ReviewItem[] | null>(null);
  const [dashboard, setDashboard] = React.useState<DashboardSummary | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [noCases, setNoCases] = React.useState(false);

  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [draft, setDraft] = React.useState("");
  const [thinking, setThinking] = React.useState(false);
  const [attachments, setAttachments] = React.useState<AssistantAttachment[]>([]);

  const [speechSupported, setSpeechSupported] = React.useState(false);
  const [recording, setRecording] = React.useState(false);
  const [voiceLangIndex, setVoiceLangIndex] = React.useState(0);
  const [speechError, setSpeechError] = React.useState<string | null>(null);
  const recognizerRef = React.useRef<Recognizer | null>(null);
  const draftBaseRef = React.useRef("");

  const nextId = React.useRef(1);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    setSpeechSupported(isSpeechSupported());
    return () => recognizerRef.current?.stop();
  }, []);

  const load = React.useCallback(() => {
    setLoadError(null);
    setItems(null);
    setNoCases(false);
    Promise.all([getReviewItems(), getDashboard().catch(() => null)])
      .then(([reviewResponse, summary]) => {
        setItems(reviewResponse.items);
        setDashboard(summary);
      })
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 404) {
          setNoCases(true);
          return;
        }
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load the case.",
        );
      });
  }, []);

  React.useEffect(load, [load]);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const stopRecording = () => recognizerRef.current?.stop();

  const toggleRecording = () => {
    if (recording) {
      stopRecording();
      return;
    }
    setSpeechError(null);
    // New speech continues the draft rather than replacing it.
    draftBaseRef.current = draft.trim() ? `${draft.trimEnd()} ` : "";
    const recognizer = startRecognition({
      lang: VOICE_LANGS[voiceLangIndex].code,
      onTranscript: (finalText, interimText) =>
        setDraft(draftBaseRef.current + finalText + interimText),
      onEnd: () => setRecording(false),
      onError: (error) =>
        setSpeechError(
          error === "not-allowed" || error === "service-not-allowed"
            ? "Microphone access was blocked. Allow it in the browser's site settings."
            : `Voice input stopped: ${error}.`,
        ),
    });
    if (recognizer) {
      recognizerRef.current = recognizer;
      setRecording(true);
    }
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    setAttachments((current) =>
      [
        ...current,
        ...Array.from(files).map((file) => ({
          name: file.name,
          size_bytes: file.size,
          kind: attachmentKind(file.name, file.type),
        })),
      ].slice(0, MAX_ATTACHMENTS),
    );
  };

  const ask = async (question: string) => {
    const trimmed = question.trim();
    const files = attachments;
    if ((!trimmed && files.length === 0) || thinking || !items) return;
    if (recording) stopRecording();
    setDraft("");
    setAttachments([]);
    setMessages((current) => [
      ...current,
      {
        id: nextId.current++,
        role: "user",
        text: trimmed,
        attachments: files.length > 0 ? files : undefined,
      },
    ]);
    setThinking(true);

    const acknowledgement = files.length > 0 ? describeAttachments(files) : null;
    let reply: AssistantAnswer;
    if (!trimmed && acknowledgement) {
      reply = localAnswer("", acknowledgement, true);
    } else {
      try {
        reply = await askAssistant(trimmed, { fixture: { items, dashboard } });
      } catch (caught) {
        reply = localAnswer(
          trimmed,
          caught instanceof ApiError
            ? `The assistant could not answer: ${caught.message}`
            : "The assistant could not answer. Try again.",
          false,
        );
      }
      if (acknowledgement) {
        reply = { ...reply, text: `${acknowledgement}\n\n---\n\n${reply.text}` };
      }
    }
    setMessages((current) => [
      ...current,
      { id: nextId.current++, role: "assistant", text: reply.text, reply },
    ]);
    setThinking(false);
  };

  if (loadError) return <ErrorState message={loadError} onRetry={load} />;
  if (noCases) {
    return (
      <EmptyState
        title="No case to talk about yet"
        message="The assistant answers only from uploaded documents. Upload a bank statement, invoices, and a ledger first."
      />
    );
  }

  return (
    <div className="flex h-full w-full flex-col gap-4 overflow-hidden">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-ink-900">Assistant</h1>
          <p className="mt-1 text-sm text-ink-600">
            Ask about this audit in plain language, English or Urdu.
            Answers are computed in code from the uploaded documents, the
            audit trail, and every case in the organization — with the source
            cited on every claim.
          </p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-wide ring-1",
            FIXTURE_MODE
              ? "bg-sky-50 text-sky-700 ring-sky-200"
              : "bg-emerald-50 text-emerald-700 ring-emerald-200",
          )}
          title={
            FIXTURE_MODE
              ? "Fixture mode: answers are composed in the browser from the fixture case."
              : "Every answer is computed by the backend from this case's persisted results and recorded in the audit trail."
          }
        >
          {FIXTURE_MODE ? "FIXTURE" : "GROUNDED"}
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {/* Transcript */}
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 md:p-5">
          {items === null ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-2/3" />
              <Skeleton className="ml-auto h-10 w-1/2" />
              <Skeleton className="h-16 w-2/3" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <span className="mb-3 rounded-full bg-brand-50 p-3 text-brand-700">
                <MessageSquare className="h-6 w-6" aria-hidden />
              </span>
              <p className="text-sm font-medium text-ink-900">
                Ask anything about this case
              </p>
              <p className="mt-1 max-w-md text-xs text-ink-400">
                The assistant explains flags, matches, totals, and the
                Benford analysis. It also reads the engagement's own record
                — documents, extractions, decisions, reports, and history —
                and keeps a plain-language glossary for first-time auditors,
                in English and Urdu.
              </p>
              <div className="mt-5 flex max-w-xl flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => ask(suggestion)}
                    className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs text-ink-600 transition-colors hover:border-brand-600 hover:text-brand-800"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((message) =>
                message.role === "user" ? (
                  <div key={message.id} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-linear-to-b from-brand-700 to-brand-800 px-4 py-2.5 shadow-sm sm:max-w-[75%]">
                      {message.text && (
                        <p className="text-sm text-white">{message.text}</p>
                      )}
                      {message.attachments && (
                        <div
                          className={cn(
                            "flex flex-wrap gap-1.5",
                            message.text && "mt-2",
                          )}
                        >
                          {message.attachments.map((attachment, index) => (
                            <span
                              key={index}
                              className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2 py-0.5 text-[10px] text-white ring-1 ring-white/30 backdrop-blur-sm"
                            >
                              <FileText className="h-3 w-3" aria-hidden />
                              <span className="truncate max-w-xs">{attachment.name}</span>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <AssistantBubble key={message.id} message={message} />
                ),
              )}
              {thinking && (
                <div className="flex justify-start">
                  <p className="flex items-center gap-2 rounded-2xl rounded-bl-sm border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-ink-400">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                    Reading the case…
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Composer */}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask(draft);
          }}
          className="shrink-0 border-t border-slate-200 bg-white/50 p-3 backdrop-blur-sm transition-all md:p-4"
        >
          {attachments.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {attachments.map((attachment, index) => (
                <span
                  key={index}
                  className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 py-1 pl-2.5 pr-1.5 text-xs text-ink-900 ring-1 ring-slate-200"
                >
                  <FileText className="h-3.5 w-3.5 shrink-0 text-ink-400" aria-hidden />
                  <span className="max-w-48 truncate">{attachment.name}</span>
                  <span className="text-[10px] text-ink-400">
                    {formatChipSize(attachment.size_bytes)}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setAttachments((current) =>
                        current.filter((_, candidate) => candidate !== index),
                      )
                    }
                    aria-label={`Remove ${attachment.name}`}
                    className="rounded-full p-0.5 text-ink-400 transition-colors hover:bg-slate-200 hover:text-ink-900"
                  >
                    <X className="h-3 w-3" aria-hidden />
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 sm:flex-nowrap">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={items === null || attachments.length >= MAX_ATTACHMENTS}
              title="Attach documents"
              aria-label="Attach documents"
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-300 text-ink-400 transition-colors",
                "hover:border-brand-600 hover:text-brand-800 disabled:cursor-not-allowed disabled:opacity-40",
              )}
            >
              <Paperclip className="h-4 w-4" aria-hidden />
            </button>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept={ACCEPTED_FILES}
              className="hidden"
              onChange={(event) => {
                addFiles(event.target.files);
                event.target.value = "";
              }}
            />

            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                recording
                  ? "Listening… speak your question"
                  : "Ask about flags, matches, totals, documents, decisions, history, a concept, or Benford…"
              }
              aria-label="Ask the assistant"
              disabled={items === null}
              className={cn(
                "h-10 min-w-0 flex-1 rounded-lg border bg-white px-3.5 text-sm text-ink-900",
                "placeholder:text-ink-400 transition-all focus:outline-none focus:ring-1",
                recording
                  ? "border-rose-400 focus:border-rose-400 focus:ring-rose-400"
                  : "border-slate-300 focus:border-brand-600 focus:ring-brand-600",
              )}
            />

            {speechSupported && (
              <>
                <button
                  type="button"
                  onClick={() =>
                    setVoiceLangIndex((current) => (current + 1) % VOICE_LANGS.length)
                  }
                  disabled={recording}
                  title="Voice input language"
                  aria-label={`Voice input language: ${VOICE_LANGS[voiceLangIndex].label}`}
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-300 text-xs font-semibold text-ink-600 transition-colors",
                    "hover:border-brand-600 hover:text-brand-800 disabled:cursor-not-allowed disabled:opacity-40",
                  )}
                >
                  {VOICE_LANGS[voiceLangIndex].label}
                </button>
                <button
                  type="button"
                  onClick={toggleRecording}
                  disabled={items === null}
                  title={recording ? "Stop listening" : "Speak your question"}
                  aria-label={recording ? "Stop listening" : "Speak your question"}
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border transition-colors",
                    recording
                      ? "animate-pulse border-rose-400 bg-rose-50 text-rose-600"
                      : "border-slate-300 text-ink-400 hover:border-brand-600 hover:text-brand-800",
                  )}
                >
                  <Mic className="h-4 w-4" aria-hidden />
                </button>
              </>
            )}

            <button
              type="submit"
              disabled={
                (!draft.trim() && attachments.length === 0) ||
                thinking ||
                items === null
              }
              aria-label="Send"
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-linear-to-b from-brand-700 to-brand-800 text-white transition-colors",
                "hover:from-brand-800 hover:to-brand-900 disabled:cursor-not-allowed disabled:opacity-40",
              )}
            >
              <Send className="h-4 w-4" aria-hidden />
            </button>
          </div>

          {speechError && (
            <p className="mt-2 text-xs text-rose-600">{speechError}</p>
          )}
        </form>
      </div>

      <p className="text-center text-[10px] text-ink-400">
        The assistant explains; it never decides. Every question and answer is
        recorded in the audit trail. Voice is transcribed by your browser and
        sent as text; approvals and rejections happen only on the review screen,
        by you.
      </p>
    </div>
  );
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  const reply = message.reply;
  const [showFacts, setShowFacts] = React.useState(false);
  const urdu = reply?.language === "ur";
  return (
    <div className="flex justify-start">
      <div
        className={cn(
          "max-w-[85%] rounded-2xl rounded-bl-sm border px-4 py-3 shadow-sm",
          reply?.grounded === false
            ? "border-amber-200 bg-amber-50"
            : "border-slate-200 bg-slate-50",
        )}
      >
        <div className="mb-1.5 flex flex-wrap items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-brand-700" aria-hidden />
          <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
            Assistant
          </span>
          {reply && <ConfidenceBadge confidence={reply.answer_confidence} />}
          {reply && reply.grounded === false && (
            <span className="text-[10px] font-medium text-amber-700">not answerable from the documents</span>
          )}
        </div>
        <p
          className={cn(
            "whitespace-pre-line text-sm leading-relaxed text-ink-900",
            urdu && "text-right",
          )}
          dir={urdu ? "rtl" : "ltr"}
          lang={urdu ? "ur" : "en"}
        >
          {message.text}
        </p>
        {reply && reply.citations.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-slate-200 pt-2">
            {reply.citations.map((citation, index) => {
              const label = `${citation.document_id}${
                citation.page != null
                  ? ` · p.${citation.page}`
                  : citation.row_number != null
                    ? ` · row ${citation.row_number}`
                    : ""
              }`;
              const chip = (
                <span
                  title={citation.text_snippet ?? undefined}
                  className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 font-mono text-[10px] text-ink-600 ring-1 ring-slate-200 transition-colors hover:text-brand-800"
                >
                  <FileText className="h-3 w-3 text-ink-400" aria-hidden />
                  {label}
                </span>
              );
              const href = citation.review_item_id
                ? `/review?item=${encodeURIComponent(citation.review_item_id)}`
                : `/documents?doc=${encodeURIComponent(citation.document_id)}${
                    citation.page != null ? `&page=${citation.page}` : ""
                  }`;
              return (
                <Link key={index} href={href}>
                  {chip}
                </Link>
              );
            })}
          </div>
        )}
        {reply && (reply.facts.length > 0 || reply.composed_by !== "frontend") && (
          <div className="mt-2 border-t border-slate-200 pt-2">
            <button
              type="button"
              onClick={() => setShowFacts((current) => !current)}
              className="flex items-center gap-1 text-[10px] font-medium text-ink-400 hover:text-brand-800"
            >
              <Calculator className="h-3 w-3" aria-hidden />
              {reply.facts.length > 0
                ? `${showFacts ? "Hide" : "Show"} the ${reply.facts.length} computed fact${reply.facts.length === 1 ? "" : "s"} behind this answer`
                : "How this was produced"}
            </button>
            {showFacts && (
              <dl className="mt-1.5 space-y-0.5">
                {reply.facts.map((fact, index) => (
                  <div key={index} className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 text-[11px]">
                    <dt className="truncate text-ink-400">{fact.label}</dt>
                    <dd className="text-ink-900 tabular-nums">{fact.value}</dd>
                  </div>
                ))}
                <div className="pt-1 text-[10px] text-ink-400">
                  Intent: {reply.intent} · computed in code · worded by {reply.composed_by}
                </div>
              </dl>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
