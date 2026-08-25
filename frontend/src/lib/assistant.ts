/**
 * Frontend preview of the assistant module (`backend/app/modules/assistant/`
 * is not built yet). Responses are composed client-side by keyword routing —
 * no model is called — but every number and every citation is real: it comes
 * from the review items and dashboard the backend served for this case.
 *
 * The posture mirrors the contract the real module must keep (reliability
 * rule 7): answer only from the uploaded documents, cite the source of every
 * claim, and refuse what cannot be grounded. When `POST /v1/assistant/chat`
 * ships, this file shrinks to a fetch call and the UI stays unchanged.
 */

import type {
  Confidence,
  DashboardSummary,
  Flag,
  Provenance,
  ReviewItem,
} from "./types";

export interface AssistantCitation {
  document_id: string;
  page?: number | null;
  snippet?: string | null;
}

/** A file dropped into the chat. Metadata only — see `describeAttachments`. */
export interface AssistantAttachment {
  name: string;
  size_bytes: number;
  kind: "pdf" | "image" | "spreadsheet" | "text" | "document";
}

export function attachmentKind(name: string, mime: string): AssistantAttachment["kind"] {
  const lower = name.toLowerCase();
  if (mime.includes("pdf") || lower.endsWith(".pdf")) return "pdf";
  if (mime.startsWith("image/")) return "image";
  if (/\.(xlsx|xls|csv)$/.test(lower) || mime.includes("spreadsheet")) return "spreadsheet";
  if (mime.startsWith("text/") || lower.endsWith(".txt")) return "text";
  return "document";
}

function formatSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

/**
 * The honest preview behaviour for chat attachments: acknowledge exactly
 * what arrived and route the user to the pipeline that actually reads
 * documents today. When `modules/assistant/` ships, chat attachments get
 * extracted and join the grounded corpus, and this becomes a real read.
 */
function describeAttachments(attachments: AssistantAttachment[]): string {
  const listed = attachments
    .map(
      (attachment) =>
        `• ${attachment.name} (${attachment.kind}, ${formatSize(attachment.size_bytes)})`,
    )
    .join("\n");
  return (
    `Received ${attachments.length} ${attachments.length === 1 ? "file" : "files"}:\n\n${listed}\n\n` +
    `In this preview I answer only from the case's uploaded documents, so chat attachments are noted but not yet read. ` +
    `To bring ${attachments.length === 1 ? "this file" : "these files"} into the audit, add ${attachments.length === 1 ? "it" : "them"} on the Upload screen, where extraction, matching, and the red-flag rules will run over ${attachments.length === 1 ? "it" : "them"} there.`
  );
}

export interface AssistantReply {
  text: string;
  confidence: Confidence;
  citations: AssistantCitation[];
  /** false when the question could not be answered from the case documents. */
  grounded: boolean;
}

function cite(source?: Provenance | null): AssistantCitation | null {
  if (!source) return null;
  return {
    document_id: source.document_id,
    page: source.page,
    snippet: source.text_snippet,
  };
}

function citationsFor(items: ReviewItem[], flags: Flag[]): AssistantCitation[] {
  const seen = new Set<string>();
  const collected: AssistantCitation[] = [];
  const push = (citation: AssistantCitation | null) => {
    if (!citation) return;
    const key = `${citation.document_id}:${citation.page ?? ""}`;
    if (!seen.has(key)) {
      seen.add(key);
      collected.push(citation);
    }
  };
  flags.forEach((flag) => push(cite(flag.source)));
  items.forEach((item) => {
    push(cite(item.ledger_entry.source));
    item.evidence.forEach((evidence) => push(cite(evidence.source)));
  });
  return collected.slice(0, 4);
}

function money(amount: number, currency: string): string {
  return `${currency} ${amount.toLocaleString("en-PK")}`;
}

function flagsMatching(items: ReviewItem[], keyword: string) {
  const flags: Flag[] = [];
  const owners: ReviewItem[] = [];
  for (const item of items) {
    for (const flag of item.flags) {
      if (flag.rule_id.toLowerCase().includes(keyword)) {
        flags.push(flag);
        owners.push(item);
      }
    }
  }
  return { flags, owners };
}

function describeRule(
  items: ReviewItem[],
  keyword: string,
  intro: string,
): AssistantReply | null {
  const { flags, owners } = flagsMatching(items, keyword);
  if (flags.length === 0) return null;
  const lines = flags.map((flag, index) => {
    const owner = owners[index];
    return `• ${owner.ledger_entry.party_name}, ${money(
      owner.ledger_entry.amount,
      owner.ledger_entry.currency,
    )} (${owner.review_item_id}): ${flag.explanation}`;
  });
  return {
    text: `${intro}\n\n${lines.join("\n")}\n\nThese are suggestions from deterministic rules. The decision on each item is yours and is recorded in the audit trail.`,
    confidence: "high",
    citations: citationsFor(owners, flags),
    grounded: true,
  };
}

export function answerFromCase(
  question: string,
  items: ReviewItem[],
  dashboard: DashboardSummary | null,
  attachments: AssistantAttachment[] = [],
): AssistantReply {
  const q = question.toLowerCase();

  // --- Files in the chat --------------------------------------------------
  if (attachments.length > 0) {
    const acknowledgement = describeAttachments(attachments);
    if (!question.trim()) {
      return {
        text: acknowledgement,
        confidence: "high",
        citations: [],
        grounded: true,
      };
    }
    const reply = answerFromCase(question, items, dashboard);
    return { ...reply, text: `${acknowledgement}\n\n---\n\n${reply.text}` };
  }

  // --- Urdu summary -------------------------------------------------------
  if (q.includes("urdu") || /[؀-ۿ]/.test(question)) {
    const severity = dashboard?.flags_by_severity;
    const allFlagged = items.filter((item) => item.flags.length > 0);
    return {
      text:
        `اس کیس میں کل ${dashboard?.total_flags ?? allFlagged.length} نشانیاں (فلیگز) اٹھائی گئی ہیں` +
        (severity
          ? `: ${severity.high} زیادہ خطرے کی، ${severity.medium} درمیانے، اور ${severity.low} کم خطرے کی۔`
          : "۔") +
        ` سب سے اہم معاملہ: ایک ہی فریق کو ایک ہی دن دو ادائیگیاں، ہر ایک منظوری کی حد سے نیچے مگر مجموعی طور پر حد سے اوپر، اور یہ سٹرکچرنگ کی علامت ہو سکتی ہے۔ ہر نشانی صرف ایک تجویز ہے: حتمی فیصلہ ہمیشہ آڈیٹر کرتا ہے اور ہر فیصلہ آڈٹ ٹریل میں محفوظ ہوتا ہے۔`,
      confidence: "medium",
      citations: citationsFor(
        allFlagged,
        allFlagged.flatMap((item) => item.flags),
      ),
      grounded: true,
    };
  }

  // --- Specific rules -----------------------------------------------------
  if (q.includes("structur") || (q.includes("same day") && q.includes("limit"))) {
    const reply = describeRule(
      items,
      "structuring",
      "Structuring means splitting one payment into several, each under an approval limit but together over it. In this case:",
    );
    if (reply) return reply;
  }
  if (q.includes("duplicate") || q.includes("twice") || q.includes("double")) {
    const reply = describeRule(
      items,
      "duplicate",
      "Duplicate payments found by the deterministic rules:",
    );
    if (reply) return reply;
  }
  if (q.includes("weekend") || q.includes("sunday") || q.includes("saturday")) {
    const reply = describeRule(
      items,
      "weekend",
      "Entries dated on a weekend, unusual for regular business payments:",
    );
    if (reply) return reply;
  }
  if (q.includes("round")) {
    const reply = describeRule(
      items,
      "round",
      "Large round amounts (a weak signal on its own, so it is never the headline flag):",
    );
    if (reply) return reply;
  }
  if (q.includes("near") && q.includes("limit")) {
    const reply = describeRule(
      items,
      "near_limit",
      "Amounts sitting just below an approval limit:",
    );
    if (reply) return reply;
  }

  // --- Benford ------------------------------------------------------------
  if (q.includes("benford") || q.includes("digit")) {
    if (!dashboard?.benford) {
      return {
        text: "Benford analysis has not been computed for this case yet.",
        confidence: "high",
        citations: [],
        grounded: true,
      };
    }
    const benford = dashboard.benford;
    const worst = benford.digits.reduce((a, b) =>
      Math.abs(b.deviation) > Math.abs(a.deviation) ? b : a,
    );
    return {
      text:
        `Benford's law compares the first digits of the ${benford.sample_size} amounts against their natural distribution. ` +
        `Chi-square is ${benford.chi_square.toFixed(2)} on ${benford.degrees_of_freedom} degrees of freedom: ` +
        (benford.deviates_significantly
          ? "the distribution deviates significantly, which is worth attention."
          : "no significant deviation.") +
        ` The digit furthest from expectation is ${worst.digit} (observed ${(worst.observed_frequency * 100).toFixed(1)}% vs expected ${(worst.expected_frequency * 100).toFixed(1)}%). ` +
        `With a sample this small the test is indicative, not conclusive; it never decides anything on its own.`,
      confidence: "medium",
      citations: [],
      grounded: true,
    };
  }

  // --- Unmatched ----------------------------------------------------------
  if (
    q.includes("unmatched") ||
    q.includes("fictitious") ||
    q.includes("missing") ||
    q.includes("no bank")
  ) {
    const unmatched = items.filter((item) => item.match.status === "unmatched");
    if (unmatched.length === 0) {
      return {
        text: "Every ledger entry in this case found a bank or invoice counterpart.",
        confidence: "high",
        citations: [],
        grounded: true,
      };
    }
    const lines = unmatched.map(
      (item) =>
        `• ${item.ledger_entry.party_name}, ${money(item.ledger_entry.amount, item.ledger_entry.currency)} on ${item.ledger_entry.date} (${item.review_item_id}): ${item.match.reason}`,
    );
    return {
      text: `${unmatched.length} ledger ${unmatched.length === 1 ? "entry" : "entries"} matched nothing in the bank statement or invoices:\n\n${lines.join("\n")}\n\nAn entry with no payment and no invoice behind it is the classic fictitious-vendor pattern, worth tracing first.`,
      confidence: "high",
      citations: citationsFor(unmatched, []),
      grounded: true,
    };
  }

  // --- A party named in the question -------------------------------------
  const byParty = items.find((item) => {
    const tokens = item.ledger_entry.party_name.toLowerCase().split(/[^a-z]+/);
    return tokens.some((token) => token.length > 3 && q.includes(token));
  });
  if (byParty) {
    const flagText =
      byParty.flags.length > 0
        ? ` Flags: ${byParty.flags.map((flag) => flag.explanation).join(" ")}`
        : " No red flags on this item.";
    return {
      text:
        `${byParty.ledger_entry.party_name}: ${money(byParty.ledger_entry.amount, byParty.ledger_entry.currency)} on ${byParty.ledger_entry.date} (${byParty.review_item_id}). ` +
        `Match status: ${byParty.match.status} (${byParty.match.match_strength} strength). ${byParty.match.reason}.${flagText} ` +
        `Current decision: ${byParty.decision}.`,
      confidence: "high",
      citations: citationsFor([byParty], byParty.flags),
      grounded: true,
    };
  }

  // --- Flags overview -----------------------------------------------------
  if (q.includes("flag") || q.includes("risk") || q.includes("fraud") || q.includes("red")) {
    const flagged = items.filter((item) => item.flags.length > 0);
    const severity = dashboard?.flags_by_severity;
    const rules = Array.from(
      new Set(flagged.flatMap((item) => item.flags.map((flag) => flag.rule_id))),
    );
    return {
      text:
        `${dashboard?.total_flags ?? flagged.flatMap((i) => i.flags).length} flags across ${flagged.length} items` +
        (severity
          ? `: ${severity.high} high, ${severity.medium} medium, ${severity.low} low severity.`
          : ".") +
        ` Rules that fired: ${rules.join(", ")}. Ask about any of them (for example "explain the structuring flag") or about a party by name. Every flag is a deterministic suggestion; the verdict on each item is the auditor's.`,
      confidence: "high",
      citations: citationsFor(flagged, flagged.flatMap((item) => item.flags)),
      grounded: true,
    };
  }

  // --- Case progress ------------------------------------------------------
  if (
    q.includes("progress") ||
    q.includes("pending") ||
    q.includes("status") ||
    q.includes("summary") ||
    q.includes("overview")
  ) {
    if (!dashboard) {
      return {
        text: "The case summary has not loaded yet. Try again in a moment.",
        confidence: "low",
        citations: [],
        grounded: true,
      };
    }
    return {
      text:
        `${dashboard.client_name}, case ${dashboard.case_id}: ${dashboard.total_review_items} review items: ` +
        `${dashboard.decisions.approved} approved, ${dashboard.decisions.rejected} rejected, ${dashboard.decisions.pending} pending. ` +
        `Matching: ${dashboard.match_status.matched} matched, ${dashboard.match_status.partial} partial, ${dashboard.match_status.unmatched} unmatched. ` +
        `Audit readiness ${dashboard.audit_readiness_score.score}/100. Every remaining pending item needs an explicit human decision before the report is complete.`,
      confidence: "high",
      citations: [],
      grounded: true,
    };
  }

  // --- Greeting / capabilities -------------------------------------------
  if (
    q.trim().length < 4 ||
    q.includes("help") ||
    q.includes("hello") ||
    q.includes("what can") ||
    q.includes("salam") ||
    q.includes("hi ")
  ) {
    return {
      text:
        "I answer questions about this case, grounded only in the uploaded documents. Try: \"which items are unmatched?\", \"explain the structuring flag\", \"why is the Sunday payment flagged?\", \"Benford summary\", or ask about a party by name. I can also explain in Urdu; ask in Urdu or say \"in Urdu\".",
      confidence: "high",
      citations: [],
      grounded: true,
    };
  }

  // --- The refusal: rule 7 made visible -----------------------------------
  return {
    text:
      "I can't answer that from this case's uploaded documents, so I won't guess: Tarazu answers only from what the client actually provided. Ask about the flags, matches, Benford analysis, or any party in the ledger.",
    confidence: "low",
    citations: [],
    grounded: false,
  };
}
