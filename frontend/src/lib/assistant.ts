/**
 * The fixture-mode assistant. With no backend configured, questions are
 * answered here by keyword routing over the fixture review items — no model
 * is called, and every number and citation comes from those items.
 *
 * In live mode the real module (`backend/app/modules/assistant/`) answers
 * through `POST /v1/assistant/chat`; `api.ts` routes there and this file is
 * not consulted. The two keep the same posture (reliability rule 7): answer
 * only from the uploaded documents, cite the source of every claim, refuse
 * what cannot be grounded. `toAssistantAnswer` adapts this file's reply to
 * the backend's `AssistantAnswer` shape so the screen renders both alike.
 *
 * The router mirrors the module's shape at reduced breadth: the glossary
 * (`CONCEPTS` — a faithful copy of the module's `concepts.py`) and the
 * engagement-record questions (documents, readings, decisions, reports,
 * history, every case in the organization) are answered here too, worded
 * like the module's composer templates. Like `types.ts` and `schemas.py`,
 * the two are changed together.
 */

import type {
  AssistantAnswer,
  AssistantIntent,
  AssistantLanguage,
  BankTransaction,
  Confidence,
  DashboardSummary,
  ExtractedField,
  Flag,
  Invoice,
  MatchStatus,
  MatchStrength,
  Provenance,
  ReviewDecision,
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
 * The honest behaviour for chat attachments: acknowledge exactly what arrived
 * and route the user to the pipeline that actually reads documents. The
 * assistant answers only from the case's uploaded documents, so a file dropped
 * into the chat is noted, never read — bringing it into the audit means
 * uploading it, where extraction, matching, and the rules run over it.
 */
export function describeAttachments(attachments: AssistantAttachment[]): string {
  const listed = attachments
    .map(
      (attachment) =>
        `• ${attachment.name} (${attachment.kind}, ${formatSize(attachment.size_bytes)})`,
    )
    .join("\n");
  return (
    `Received ${attachments.length} ${attachments.length === 1 ? "file" : "files"}:\n\n${listed}\n\n` +
    `I answer only from the case's uploaded documents, so chat attachments are noted but not read. ` +
    `To bring ${attachments.length === 1 ? "this file" : "these files"} into the audit, add ${attachments.length === 1 ? "it" : "them"} on the Upload screen, where extraction, matching, and the red-flag rules run over ${attachments.length === 1 ? "it" : "them"}.`
  );
}

export interface AssistantReply {
  text: string;
  confidence: Confidence;
  citations: AssistantCitation[];
  /** false when the question could not be answered from the case documents. */
  grounded: boolean;
  /** The intent the keyword router placed the question in, mirroring the
   * backend's `AssistantIntent`. Omitted where the reply is not one. */
  intent?: AssistantIntent;
}

/** Adapt a fixture-mode reply to the backend's `AssistantAnswer` shape. */
export function toAssistantAnswer(
  question: string,
  reply: AssistantReply,
  language?: AssistantLanguage,
): AssistantAnswer {
  const urdu = language === "ur" || /[؀-ۿ]/.test(question) || /urdu/i.test(question);
  const intent: AssistantIntent = reply.intent ?? (reply.grounded ? "summary" : "unknown");
  return {
    question,
    language: urdu ? "ur" : "en",
    intent,
    text: reply.text,
    answer_confidence: reply.confidence,
    grounded: reply.grounded,
    citations: reply.citations.map((citation) => ({
      document_id: citation.document_id,
      page: citation.page ?? null,
      row_number: null,
      text_snippet: citation.snippet ?? null,
      review_item_id: null,
    })),
    facts: [],
    composed_by: "fixture.keyword-router",
  };
}

function cite(source?: Provenance | null): AssistantCitation | null {
  if (!source) return null;
  return {
    document_id: source.document_id,
    page: source.page,
    snippet: source.text_snippet,
  };
}

function dedupeCitations(citations: AssistantCitation[], cap = 4): AssistantCitation[] {
  const seen = new Set<string>();
  const collected: AssistantCitation[] = [];
  for (const citation of citations) {
    const key = `${citation.document_id}:${citation.page ?? ""}`;
    if (!seen.has(key)) {
      seen.add(key);
      collected.push(citation);
    }
  }
  return collected.slice(0, cap);
}

function citationsFor(items: ReviewItem[], flags: Flag[]): AssistantCitation[] {
  const collected: AssistantCitation[] = [];
  const push = (citation: AssistantCitation | null) => {
    if (citation) collected.push(citation);
  };
  flags.forEach((flag) => push(cite(flag.source)));
  items.forEach((item) => {
    push(cite(item.ledger_entry.source));
    item.evidence.forEach((evidence) => push(cite(evidence.source)));
  });
  return dedupeCitations(collected);
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
  intent: AssistantIntent = "rule",
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
    intent,
  };
}

// ---------------------------------------------------------------------------
// The glossary — a faithful copy of the module's concepts.py, kept in sync.
// ---------------------------------------------------------------------------

const CONCEPTS: Record<string, { en: string; ur: string }> = {
  "reconciliation": {
    en: "Reconciliation is checking that two independent records of the same money agree. In Tarazu it is a three-way match: every payment in the client's ledger must be backed by a line in the bank statement (the money really left) and, where there should be one, an invoice (the payment was really owed). A row that agrees on amount and date is matched; a row with nothing behind it is the classic sign of a payment that never happened. Ask \"which items are unmatched?\" to see yours.",
    ur: "مطابقت (ریکنسلئیشن) کا مطلب ہے ایک ہی رقم کے دو آزاد ریکارڈوں کا آپس میں ملانا۔ ترازو میں یہ تین طرفہ میچ ہے: کلائنٹ کی لیجر کی ہر ادائیگی کے پیچھے بینک اسٹیٹمنٹ کی ایک قطار ہونی چاہیے (رقم واقعی گئی) اور جہاں انوائس ہونی چاہیے وہ بھی (ادائیگی واقعی واجب الادا تھی)۔ جو قطار رقم اور تاریخ دونوں پر مل جائے وہ مماثل ہے؛ جس کے پیچھے کچھ نہ ہو وہ فرضی ادائیگی کی کلاسک علامت ہے۔ اپنے کیس میں دیکھنے کے لیے پوچھیں: \"کون سے آئٹم غیر مماثل ہیں؟\"",
  },
  "benford": {
    en: "Benford's law is an observation about real-life numbers: in naturally occurring amounts, about 30% start with the digit 1 and only about 5% start with 9. Made-up numbers tend not to follow that shape, so when the first digits of a ledger's amounts stray far from it, that is worth a look. It is a screening test, never proof: small samples wobble, and honest books can deviate. Ask \"Benford summary\" to see this case's own result.",
    ur: "بینفورڈ کا قانون قدرتی اعداد کے بارے میں ایک مشاہدہ ہے: حقیقی رقوم میں تقریباً 30% کا آغاز ہندسہ 1 سے ہوتا ہے اور صرف 5% کا آغاز 9 سے۔ گھڑے ہوئے اعداد عموماً یہ ساخت نہیں رکھتے، اس لیے جب لیجر کی رقوم کے پہلے ہندسے اس سے بہت ہٹ جائیں تو دیکھنے کے قابل ہے۔ یہ ایک جانچ ہے، ثبوت کبھی نہیں۔ چھوٹا نمونہ ہل سکتا ہے اور ایماندار کتابیں بھی ہٹ سکتی ہیں۔ اپنے کیس کا نتیجہ دیکھنے کے لیے پوچھیں: \"بینفورڈ خلاصہ\"۔",
  },
  "red-flag": {
    en: "A red flag is a pattern that experience says deserves a closer look, not proof of wrongdoing. A round amount, a payment on a Sunday, two payments just under an approval limit: each can have an innocent explanation, and each is where an auditor looks first. In Tarazu every flag is raised by a fixed, published rule and is only a suggestion; the verdict is always the auditor's. Ask \"what flags were raised?\" for this case's list.",
    ur: "سرخ نشانی (ریڈ فلیگ) وہ نمونہ ہے جسے تجربہ کہتا ہے زیادہ غور سے دیکھو، غلط کام کا ثبوت نہیں۔ گول رقم، اتوار کی ادائیگی، منظوری کی حد سے تھوڑا نیچے دو ادائیگیاں: ہر ایک کی معقول وضاحت ہو سکتی ہے، اور ہر ایک وہ جگہ ہے جہاں آڈیٹر پہلے دیکھتا ہے۔ ترازو میں ہر نشانی ایک متعین، طے شدہ اصول سے اٹھتی ہے اور صرف تجویز ہے؛ فیصلہ ہمیشہ آڈیٹر کا ہے۔ اپنے کیس کی فہرست کے لیے پوچھیں: \"کون سی نشانیاں اٹھیں؟\"",
  },
  "approval-limit": {
    en: "An approval limit is the amount above which a payment needs a second signature, a control firms set so no one person can move large sums alone. The audit interest is in payments sized to sit just under it: one payment at 98% of the limit may be chance, a pattern of them suggests someone knows the limit and is steering under it. Tarazu's near-limit rule flags amounts within 2% below a limit.",
    ur: "منظوری کی حد وہ رقم ہے جس سے اوپر ادائیگی کو دوسرا دستخط درکار ہوتا ہے۔ یہ کنٹرول فرم اس لیے رکھتی ہے کہ کوئی اکیلا بڑی رقم نہ ہلا سکے۔ آڈٹ کی دلچسپی ان ادائیگیوں میں ہے جو عین اس حد سے نیچے رکھی گئی ہوں: حد کے 98% پر ایک ادائیگی اتفاق ہو سکتی ہے، مگر ان کا سلسلہ بتاتا ہے کہ کوئی حد جانتا ہے اور اس سے بچ رہا ہے۔ ترازو کا \"حد کے قریب\" اصول حد سے 2% نیچے کی رقوم نشان زد کرتا ہے۔",
  },
  "duplicate-payment": {
    en: "A duplicate payment is the same bill paid twice, usually by accident: an invoice entered twice, a re-send mistaken for a new bill. It costs the client real money and is easy to miss by eye, which is why it is checked mechanically. Tarazu flags the same amount to the same party within a few days, and one invoice settled by two ledger rows. Ask \"any duplicate payments?\" to see yours.",
    ur: "دوہری ادائیگی ایک ہی بل کی دو بار ادائیگی ہے، عموماً غلطی سے: انوائس دو بار درج ہو گئی، یا دوبارہ بھیجی گئی انوائس کو نیا بل سمجھ لیا گیا۔ اس سے کلائنٹ کی اصل رقم جاتی ہے اور نظر سے چھپنا آسان ہے، اسی لیے یہ مشینی طریقے سے جانچی جاتی ہے۔ ترازو ایک ہی فریق کو چند دنوں کے اندر ایک ہی رقم، اور ایک انوائس جو دو لیجر قطاروں سے کلی ہو، نشان زد کرتا ہے۔ اپنے کیس کے لیے پوچھیں: \"کوئی دوہری ادائیگی؟\"",
  },
  "matching": {
    en: "Matching is the comparison at the heart of reconciliation. Tarazu matches each ledger row against the bank statement and the invoices: matched means amount and date both agree; partial means the right counterpart exists but something differs (a date off by days, a small amount gap), which is worth a look but may be timing; unmatched means nothing behind the row at all, which is where fictitious payments hide. Ask \"which items are unmatched?\" to start with the sharpest question first.",
    ur: "میلان (میچنگ) وہ موازنہ ہے جو مطابقت کے مرکز میں ہے۔ ترازو لیجر کی ہر قطار کو بینک اسٹیٹمنٹ اور انوائسز سے ملاتا ہے: مماثل کا مطلب رقم اور تاریخ دونوں متفق ہیں؛ جزوی کا مطلب صحیح ہم منصب موجود ہے مگر کچھ فرق ہے (کچھ دن کی تاریخ، تھوڑا رقم کا فرق)، اسے دیکھیں مگر یہ ٹائمنگ بھی ہو سکتی ہے؛ غیر مماثل کا مطلب قطار کے پیچھے کچھ بھی نہیں، اور فرضی ادائیگیاں وہیں چھپتی ہیں۔ سب سے تیز سوال پہلے پوچھنے کے لیے کہیں: \"کون سے آئٹم غیر مماثل ہیں؟\"",
  },
  "audit-trail": {
    en: "An audit trail is the unbroken record of who did what, and when: the thing that lets a third party re-verify the work months later. Tarazu's trail is append-only: every upload, every flag, every decision, every question you ask here is written to it, and nothing (not you, not the system) can edit or delete an entry. That is enforced in the database itself, not by good behaviour. Ask \"what happened in this case?\" to read this engagement's own history.",
    ur: "آڈٹ ٹریل اس کام کا مسلسل ریکارڈ ہے کہ کس نے کیا کیا اور کب۔ یہی چیز تیسرے شخص کو مہینوں بعد کام دوبارہ جانچنے دیتی ہے۔ ترازو کا ٹریل صرف جمع ہونے والا ہے: ہر اپ لوڈ، ہر نشانی، ہر فیصلہ، آپ کا یہاں پوچھا گیا ہر سوال اس میں لکھا جاتا ہے، اور کچھ بھی (نہ آپ، نہ سسٹم) کوئی اندراج بدل یا مٹ نہیں سکتا۔ یہ بات ڈیٹابیس خود پر لاگو کرتی ہے، دیانت پر نہیں۔ اس کیس کی اپنی تاریخ پڑھنے کے لیے پوچھیں: \"اس کیس میں کیا ہوا؟\"",
  },
  "evidence": {
    en: "Evidence, in an audit, is the independent document behind a claim: the bank line proves the money moved; the invoice proves it was owed; the ledger alone proves nothing, because the client writes it. That is why Tarazu never takes a ledger row on trust: each one is matched against those independent sources, and rows short of evidence are surfaced rather than smoothed over. Ask \"which rows are missing evidence?\" for this case's gaps.",
    ur: "آڈٹ میں ثبوت کسی دعوے کے پیچھے کی آزاد دستاویز ہے: بینک کی قطار ثابت کرتی ہے کہ رقم گئی؛ انوائس ثابت کرتی ہے کہ ادائیگی واجب الادا تھی؛ لیجر اکیلے کچھ ثابت نہیں کرتا، کیونکہ وہ کلائنٹ خود لکھتا ہے۔ اسی لیے ترازو لیجر کی قطار پر بھروسہ نہیں کرتا: ہر قطار ان آزاد مآخذ سے ملائی جاتی ہے، اور جو قطاریں ثبوت سے خالی ہیں وہ چھپائی نہیں جاتیں۔ اپنے کیس کے خلا دیکھنے کے لیے پوچھیں: \"کون سی قطاریں ثبوت سے خالی ہیں؟\"",
  },
  "ledger": {
    en: "A ledger is the client's own book of payments, usually a spreadsheet, and it is the starting point of this audit, not the truth. The client writes it, so a dishonest client can write anything into it; the bank statement and the invoices are the independent voices it is checked against. In Tarazu the ledger is read by plain spreadsheet code, no AI involved, and every row keeps the sheet row it came from.",
    ur: "لیجر کلائنٹ کی اپنی ادائیگیوں کی کتاب ہے، عموماً ایک اسپریڈ شیٹ، اور یہ اس آڈٹ کا نقطہ آغاز ہے، سچ نہیں۔ یہ کلائنٹ خود لکھتا ہے، اس لیے بے ایمان کلائنٹ اس میں کچھ بھی لکھ سکتا ہے؛ بینک اسٹیٹمنٹ اور انوائسز وہ آزاد آوازیں ہیں جن سے اس کی جانچ ہوتی ہے۔ ترازو میں لیجر سادہ اسپریڈ شیٹ کوڈ سے پڑھا جاتا ہے، کوئی AI شامل نہیں، اور ہر قطار اپنی شیٹ قطار نمبر ساتھ رکھتی ہے۔",
  },
  "bank-statement": {
    en: "A bank statement is the bank's own record of the account, the closest thing to an independent witness an audit has. Money that left the account is on it, money that only exists on paper is not, which is why the statement is the anchor every ledger row is matched against. Tarazu reads it with a vision model, and every value it reads keeps the page and the snippet it came from, so you can check the machine against the paper.",
    ur: "بینک اسٹیٹمنٹ بینک کا اکاؤنٹ کا اپنا ریکارڈ ہے، آڈٹ کے پاس آزاد گواہ کا سب سے قریب روپ۔ جو رقم اکاؤنٹ سے گئی وہ اس پر ہے، جو رقم صرف کاغذ پر ہے وہ نہیں، اسی لیے یہ وہ لنگر ہے جس سے لیجر کی ہر قطار ملائی جاتی ہے۔ ترازو اسے وژن ماڈل سے پڑھتا ہے، اور جو قدر پڑھی جاتی ہے وہ اپنا صفحہ اور اقتباس ساتھ رکھتی ہے، تاکہ آپ مشین کا کاغذ سے مقابلہ کر سکیں۔",
  },
  "materiality": {
    en: "Materiality is the professional word for \"big enough to matter\". An audit does not check every paisa to the same depth; it focuses where an error would change a reader's opinion of the books. A missing receipt for a small tea bill and the same gap on a large payment are not the same finding. Tarazu helps you see the sizes (largest payments, totals by vendor) so you can point your attention where it matters.",
    ur: "اہمیت (میٹیریلٹی) کا پیشہ ورانہ مطلب ہے \"اتنا بڑا کہ فرق ڈالے\"۔ آڈٹ ہر پیسے کو ایک گہرائی سے نہیں جانچتا؛ وہ وہاں توجہ دیتا ہے جہاں غلطی کتابوں پر قاری کی رائے بدل دے۔ چھوٹے چائے کے بل کی گم رسید اور بڑی ادائیگی پر وہی خلا برابر نہیں۔ ترازو سائز دکھانے میں مدد دیتا ہے (سب سے بڑی ادائیگیاں، وینڈر کے حساب سے مجموعی) تاکہ آپ اپنی توجہ وہاں رکھیں جہاں وہ معنی رکھتی ہے۔",
  },
  "sampling": {
    en: "Sampling is checking some of the many and reasoning about the rest, which is what auditors do when a ledger has thousands of rows. The choice of which rows to look at is where an audit earns its keep: random samples, high-value rows, and rule-based picks each answer a different question. Tarazu's flags are rule-based picks: every row is screened by the same published rules, and you decide which flagged rows become findings.",
    ur: "نمونہ لینا (سیمپلنگ) بہت سے میں سے کچھ جانچ کر باقی کے بارے میں نتیجہ نکالنا ہے۔ یہی آڈیٹر کرتے ہیں جب لیجر میں ہزاروں قطاریں ہوں۔ یہ انتخاب کہ کون سی قطاریں دیکھنی ہیں وہی آڈٹ کی اصل مہارت ہے: رینڈم نمونے، بڑی رقم کی قطاریں، اور اصول پر مبنی چناؤ الگ الگ سوال کا جواب دیتے ہیں۔ ترازو کی نشانیاں اصول پر مبنی چناؤ ہیں: ہر قطار اسی شائع شدہ اصول سے جانچی جاتی ہے، اور آپ فیصلہ کرتے ہیں کہ کون سی نشان زد قطار باب بنے۔",
  },
  "human-in-the-loop": {
    en: "Human-in-the-loop means the machine may narrow the work, never close it. Tarazu's AI reads documents and its rules raise flags, but approving or rejecting an item is an act of professional judgement with your name on it, so it stays with you, and every decision you make is recorded as yours in the trail. The assistant you are talking to is under the same rule: it explains and computes, it never decides.",
    ur: "ہیومن اِن دی لوپ کا مطلب ہے: مشین کام تنگ کر سکتی ہے، مکمل نہیں کرتی۔ ترازو کا AI دستاویزیں پڑھتا ہے اور اس کے اصول نشانیاں اٹھاتے ہیں، مگر کسی آئٹم کی منظوری یا رد کا فیصلہ پیشہ ورانہ فیصلہ ہے جس پر آپ کا نام ہے، اس لیے وہ آپ کے پاس رہتا ہے، اور آپ کا ہر فیصلہ ٹریل میں آپ ہی کے نام سے درج ہوتا ہے۔ جس اسسٹنٹ سے آپ بات کر رہے ہیں وہی اصول مانتا ہے: وہ سمجھاتا اور حساب کرتا ہے، فیصلہ کبھی نہیں کرتا۔",
  },
  "provenance": {
    en: "Provenance is the answer to \"says who?\": where a value came from, exactly. Every number Tarazu shows carries its source: the document, the page, and the snippet for things a model read, or the spreadsheet row for things code read. It is what lets you check the machine's reading against the paper yourself, and it is why an answer from this assistant always cites where it stands.",
    ur: "ماخذ (پروویننس) اس سوال کا جواب ہے: \"کہتا کون ہے؟\" یعنی کوئی قدر کہاں سے آئی، بالکل۔ ترازو کا دکھایا ہر عدد اپنا ذریعہ ساتھ رکھتا ہے: دستاویز، صفحہ اور اقتباس اگر ماڈل نے پڑھا، یا اسپریڈ شیٹ کی قطار اگر کوڈ نے پڑھا۔ یہی چیز آپ کو مشین کی پڑھائی کاغذ سے خود جانچنے دیتی ہے، اور اسی لیے اس اسسٹنٹ کا ہر جواب بتاتا ہے کہ وہ کہاں کھڑا ہے۔",
  },
  "tolerance": {
    en: "A tolerance is the small difference two records may show and still count as agreeing: a bank posting a day after the ledger dates it, a rounding of rupees on a large amount. Zero tolerance would drown an audit in noise, so Tarazu's matching allows a date window and a small amount gap, marks those matches as partial, and tells you the exact difference so you can judge whether it is timing or something worth chasing.",
    ur: "رخصت (ٹالرنس) وہ چھوٹا فرق ہے جو دو ریکارڈ دکھا کر بھی متفق سمجھے جائیں: بینک ادائیگی ایک دن بعد درج کرے، یا بڑی رقم پر چند روپے کا فرق۔ صفر رخصت آڈٹ کو شور میں ڈبو دے گی، اسی لیے ترازو کے میچنگ میں تاریخ کی مہلت اور تھوڑا رقم کا فرق شامل ہے، ایسے میچ جزوی کہلاتے ہیں، اور آپ کو بالکل فرق بتایا جاتا ہے تاکہ آپ فیصلہ کر سکیں کہ یہ ٹائمنگ ہے یا پیچھا کرنے والی بات۔",
  },
};

const TOPIC_WORDS: Record<string, string[]> = {
  "reconciliation": ["reconcil*", "three-way match*", "three way match*", "تین طرفہ مطابقت", "مطابقت"],
  "benford": ["benford*", "بینفورڈ"],
  "red-flag": ["red flag*", "سرخ نشانی"],
  "approval-limit": ["approval limit*", "منظوری کی حد"],
  "duplicate-payment": ["duplicate payment*", "دوہری ادائیگی"],
  "matching": ["matched", "unmatched", "partial match*", "match strength*", "مماثل", "غیر مماثل", "جزوی"],
  "audit-trail": ["audit trail*", "آڈٹ ٹریل", "ٹریل"],
  "evidence": ["evidence", "supporting document*", "ثبوت"],
  "ledger": ["ledger", "لیجر"],
  "bank-statement": ["bank statement*", "بینک اسٹیٹمنٹ"],
  "materiality": ["materialit*", "material", "اہمیت"],
  "sampling": ["sampl*", "نمونہ"],
  "human-in-the-loop": ["human in the loop", "human-in-the-loop", "why do i have to approve", "approve everything myself", "انسانی فیصلہ"],
  "provenance": ["provenance", "source of a value", "ماخذ"],
  "tolerance": ["tolerance", "date window*", "رخصت"],
};

const DEDICATED_TOPICS = new Set(["benford", "red-flag", "duplicate-payment", "matching"]);

const CONCEPT_SUFFIX = {
  en: "That is from Tarazu's built-in glossary, written and reviewed in code, not generated. Ask about your own case next (for example \"which items are unmatched?\" or \"what happened in this case?\") to see the idea at work in your data.",
  ur: "یہ ترازو کی اپنی لغت سے ہے، کوڈ میں لکھی اور جانچی گئی، مشین سے تخلیق نہیں۔ اب اپنے کیس کے بارے میں پوچھیں (مثلاً \"کون سے آئٹم غیر مماثل ہیں؟\" یا \"اس کیس میں کیا ہوا؟\") تاکہ یہ تصور اپنے ہی اعداد میں دکھے۔",
};

// --- Keyword helpers (mirror planner.py) -----------------------------------

const _DEFINITIONAL = ["what is", "what are", "what does", "mean*", "define", "definition*", "difference between", "کیا ہے", "کیا ہیں", "کا مطلب", "تعریف"];
const _DEFINITIONAL_EXCEPT = ["what is the", "what is this", "what is my", "what is our", "what are the", "what are these", "what are my", "what are our"];
const _EXPLAIN = ["explain*", "teach me", "tell me about", "help me understand", "how does", "how do", "سمجھائیں", "سمجھاؤ", "سکھائیں"];
const _BEGINNER = ["i'm new", "i am new", "new to audit*", "first audit", "beginner*", "new to this", "where do i start", "شروع کہاں سے", "پہلی بار"];

const _HELP_EN = "Yes, ask away. I answer questions about this audit, grounded only in what was actually uploaded and decided. About the results: \"match results\", \"which items are unmatched?\", \"explain the structuring flag\", \"any duplicate payments?\", \"Benford summary\". About the data: \"which invoices are in this case?\", \"what is in the bank statement?\", \"list all ledger rows\", \"what was paid on 11 June?\", \"any payment of 49,500?\", \"top vendors\", \"what did we pay Karachi Packaging?\". About one thing, name it: \"RI-0005\", \"invoice INV-2026-0087\", \"row 16\". About the engagement's own record: \"what documents are in this case?\", \"what did the model read?\", \"how confident was the reading?\", \"what have we decided so far?\", \"which reports exist?\", \"what happened in this case?\", \"who is the client?\", \"show me all my cases\". And if you are new to auditing, ask \"what is reconciliation?\" or \"explain materiality\". I keep a plain-language glossary for exactly that. I can also answer in Urdu: ask in Urdu or say \"in Urdu\".";
const _HELP_UR = "جی، پوچھیں۔ میں اس آڈٹ کے سوالوں کے جواب صرف اپ لوڈ شدہ اور فیصلہ شدہ چیزوں کی بنیاد پر دیتا ہوں۔ نتائج کے بارے میں: \"میچ کے نتائج\"، \"کون سے آئٹم غیر مماثل ہیں؟\"، \"کل اخراجات\"، \"بینفورڈ خلاصہ\"۔ ڈیٹا کے بارے میں: \"اس کیس میں کون سی انوائسز ہیں؟\"، \"بینک اسٹیٹمنٹ میں کیا ہے؟\"، \"تمام قطاریں دکھائیں\"، \"11 جون کو کیا ادا ہوا؟\"۔ کسی ایک چیز کے بارے میں اس کا نمبر لکھیں: \"RI-0005\"، \"انوائس INV-2026-0087\"، \"قطار 16\"۔ ریکارڈ کے بارے میں: \"اس کیس میں کون سے دستاویزات ہیں؟\"، \"ماڈل نے کیا پڑھا؟\"، \"اب تک کیا فیصلے ہوئے؟\"، \"اس کیس میں کیا ہوا؟\"، \"کلائنٹ کون ہے؟\"، \"میرے تمام کیس دکھائیں\"۔ اگر آڈٹ کے لیے نئے ہیں تو پوچھیں \"مطابقت کیا ہے؟\" یا \"اہمیت کیا ہے؟\"۔ میرے پاس سادہ زبان کی لغت موجود ہے۔ اردو میں بھی جواب دے سکتا ہوں: اردو میں پوچھیں یا کہیں \"اردو میں\"۔";
const _REFUSAL_EN = "I can't answer that from this case's uploaded documents, so I won't guess: Tarazu answers only from what the client actually provided. Ask about the match results, one row or invoice by its identifier, the invoices, the bank statement lines, the flags, a party by name, a day or an amount, totals by vendor or month, the Benford analysis, the documents, the decisions, the reports, or the history.";
const _REFUSAL_UR = "میں اس سوال کا جواب اس کیس کی اپ لوڈ شدہ دستاویزات سے نہیں دے سکتا، اس لیے اندازہ نہیں لگاؤں گا: ترازو صرف اسی سے جواب دیتا ہے جو کلائنٹ نے واقعی فراہم کیا ہو۔ میچ کے نتائج، کسی قطار یا انوائس کے شناختی نمبر، انوائسز، بینک اسٹیٹمنٹ کی قطاروں، نشانیوں، کسی فریق کے نام، کسی تاریخ یا رقم، وینڈر یا مہینے کے حساب سے مجموعی رقم، بینفورڈ تجزیے، دستاویزات، فیصلوں، رپورٹوں یا تاریخچے کے بارے میں پوچھیں۔";
/** The question used the audit's own words but named no query: say so, and show what works (mirrors composer._REFUSAL_ON_TOPIC). */
const _REFUSAL_ON_TOPIC_EN = "That sounds like a question about this audit, but I couldn't tell which part of it you mean, so I won't guess. I can answer, from this case's own data: the match results (\"match results\", \"partial matches\", \"which items are unmatched?\"); one row, invoice, or bank line by its identifier (\"RI-0005\", \"invoice INV-2026-0087\", \"row 16\"); the invoices, the bank statement lines, or every ledger row; a party by name; a day or month (\"what was paid on 11 June?\"); a specific amount; the flags and each rule; totals, top vendors, largest payments; how confidently the documents were read; the documents, the decisions, the reports, the history; and the case itself.";
const _REFUSAL_ON_TOPIC_UR = "یہ سوال اس آڈٹ کے بارے میں لگتا ہے، مگر میں یہ طے نہیں کر سکا کہ آپ کا مطلب اس کا کون سا حصہ ہے، اس لیے اندازہ نہیں لگاؤں گا۔ میں اس کیس کے اپنے ڈیٹا سے بتا سکتا ہوں: میچ کے نتائج، کوئی ایک قطار، انوائس یا بینک لائن اس کے شناختی نمبر سے، انوائسز، بینک اسٹیٹمنٹ کی قطاریں، لیجر کی ہر قطار، کوئی فریق نام سے، کوئی دن یا مہینہ، کوئی مخصوص رقم، نشانیاں اور ہر اصول، مجموعی رقم، دستاویزات، فیصلے، رپورٹیں، تاریخچہ، اور کیس خود۔";
/** "Can I ask you something?" — yes. Mirrors planner._META. */
const _META = ["can i ask", "may i ask", "could i ask", "i have a question", "i want to ask", "i'd like to ask", "i would like to ask", "one question", "a question", "ask you something", "ask something", "ask about", "کیا میں پوچھ", "ایک سوال", "سوال پوچھ"];
/** Words that say the question is about this audit's data. Mirrors planner._DOMAIN. */
const _DOMAIN = ["ledger", "bank", "invoice*", "payment*", "paid", "pay", "item*", "row*", "entr*", "transaction*", "audit*", "case", "match*", "vendor*", "supplier*", "amount*", "rupee*", "pkr", "rs", "flag*", "document*", "statement*", "record*", "account*", "reconcil*", "review*", "decision*", "report*", "client", "money", "cheque*", "check*", "receipt*", "voucher*", "expense*", "cost*", "purchase*", "party", "parties", "figure*", "number*", "total*", "date*", "month*", "result*", "finding*", "evidence", "extract*", "لیجر", "بینک", "انوائس", "ادائیگی", "آئٹم", "قطار", "آڈٹ", "اس کیس", "کیس میں", "رقم", "دستاویز"];

function isUrdu(question: string): boolean {
  return /[؀-ۿ]/.test(question) || /\burdu\b/i.test(question);
}

function matchesAny(text: string, ...needles: string[]): boolean {
  for (const needle of needles) {
    const star = needle.endsWith("*");
    const core = star ? needle.slice(0, -1) : needle;
    if (/[a-z]/i.test(core)) {
      const esc = core.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (new RegExp(`(?<![a-z0-9])${esc}${star ? "" : "(?![a-z0-9])"}`, "i").test(text)) return true;
    } else if (text.includes(core)) {
      return true;
    }
  }
  return false;
}

function topicNamed(lowered: string): string | null {
  for (const [topic, words] of Object.entries(TOPIC_WORDS)) {
    if (matchesAny(lowered, ...words)) return topic;
  }
  return null;
}

function isDefinitional(lowered: string): boolean {
  if (matchesAny(lowered, ..._DEFINITIONAL_EXCEPT)) return false;
  return matchesAny(lowered, ..._DEFINITIONAL);
}

// --- Workspace handlers (mirror composer.py at reduced breadth) -------------

function answerConcept(topic: string, urdu: boolean): AssistantReply {
  const entry = CONCEPTS[topic];
  if (!entry) return { text: "", confidence: "low", citations: [], grounded: false };
  const lang = urdu ? "ur" : "en";
  return { text: `${entry[lang]}\n\n${CONCEPT_SUFFIX[lang]}`, confidence: "high", citations: [], grounded: true, intent: "concept" };
}

function answerCases(items: ReviewItem[], dashboard: DashboardSummary | null, urdu: boolean): AssistantReply {
  const client = dashboard?.client_name ?? "—";
  const caseId = dashboard?.case_id ?? "—";
  const pending = items.filter((i) => i.decision === "pending").length;
  const flagCount = items.reduce((s, i) => s + i.flags.length, 0);
  if (urdu) {
    return { text: `آپ کی تنظیم میں 1 کیس ہے:\n\n• ${client} (${caseId}) (فعلی کیس): ${items.length} آئٹم، ${pending} زیر التوا، ${flagCount} نشانیاں · ready_for_review، 2026-06-19 کو بنی\n\nفعلی کیس نشان زد ہے اور میرے باقی جوابات اسی کے بارے میں ہیں؛ ہیڈر سے کیس بدل کر کسی دوسرے میں جائیں۔`, confidence: "high", citations: [], grounded: true, intent: "cases" };
  }
  return { text: `Your organization holds 1 engagement:\n\n• ${client} (${caseId}) (active case): ${items.length} items, ${pending} pending, ${flagCount} flags · ready_for_review, created 2026-06-19\n\nThe active case is marked, and every other answer I give is about it. Switch cases from the header to work inside another engagement.`, confidence: "high", citations: [], grounded: true, intent: "cases" };
}

function answerDocuments(items: ReviewItem[], urdu: boolean): AssistantReply {
  const byDoc: Record<string, { count: number; type: string }> = {};
  for (const item of items) {
    const add = (id: string | undefined) => {
      if (!id) return;
      if (!byDoc[id]) {
        const type = id.includes("LED") ? "ledger" : id.includes("BNK") ? "bank_statement" : "invoice";
        byDoc[id] = { count: 0, type };
      }
      byDoc[id].count++;
    };
    add(item.ledger_entry.source?.document_id);
    for (const ev of item.evidence) add(ev.source?.document_id);
  }
  const count = Object.keys(byDoc).length;
  if (count === 0) {
    return { text: urdu ? "اس کیس میں ابھی کوئی دستاویز نہیں۔" : "This case holds no documents yet.", confidence: "high", citations: [], grounded: true, intent: "documents" };
  }
  const lines = Object.entries(byDoc).map(([id, d]) =>
    urdu ? `• ${id} (${d.type}): ${d.count} قدریں پڑھی گئیں` : `• ${id} (${d.type}): ${d.count} value(s) read by the extraction pipeline`,
  );
  const intro = urdu
    ? `اس کیس میں ${count} دستاویزات ہیں، جن میں سے ${count} نکاسی سلگھی ہے:\n\n`
    : `This case holds ${count} document(s), ${count} of them read by the extraction pipeline:\n\n`;
  const suffix = urdu
    ? "\n\nدستاویز اپ لوڈ کے وقت ایک بار پڑھی جاتی ہے۔ ماڈل کی پڑھی ہر قدر اپنا صفحہ اور اقتباس ساتھ رکھتی ہے۔ دستاویزات کی اسکرین پر دیکھیں۔"
    : "\n\nDocuments are read once, at upload. Every value the model produced keeps the page and snippet it came from. The Documents screen shows each one.";
  return { text: intro + lines.join("\n") + suffix, confidence: "high", citations: [], grounded: true, intent: "documents" };
}

function answerExtractions(items: ReviewItem[], urdu: boolean): AssistantReply {
  const byDoc: Record<string, { type: string; values: number; high: number; medium: number; low: number; unreadable: number; notable: Array<{ field: string; value: string; conf: string }>; cites: AssistantCitation[] }> = {};
  for (const item of items) {
    for (const ev of item.evidence) {
      const id = ev.source?.document_id;
      if (!id) continue;
      if (!byDoc[id]) {
        const type = id.includes("LED") ? "ledger" : id.includes("BNK") ? "bank_statement" : "invoice";
        byDoc[id] = { type, values: 0, high: 0, medium: 0, low: 0, unreadable: 0, notable: [], cites: [] };
      }
      const d = byDoc[id];
      d.values++;
      if (ev.unreadable) d.unreadable++;
      else if (ev.extraction_confidence === "high") d.high++;
      else if (ev.extraction_confidence === "medium") d.medium++;
      else d.low++;
      if (ev.unreadable || ev.extraction_confidence !== "high") {
        d.notable.push({ field: ev.field, value: ev.unreadable ? "unreadable" : String(ev.value), conf: ev.unreadable ? "unreadable" : ev.extraction_confidence });
        if (d.cites.length < 3 && ev.source) d.cites.push({ document_id: ev.source.document_id, page: ev.source.page, snippet: ev.source.text_snippet });
      }
    }
  }
  const docCount = Object.keys(byDoc).length;
  if (docCount === 0) {
    return { text: urdu ? "اس کیس کے لیے ابھی کچھ بھی نہیں پڑھا گیا۔" : "Nothing has been read from documents for this case yet.", confidence: "high", citations: [], grounded: true, intent: "extractions" };
  }
  const lines: string[] = [];
  const allCites: AssistantCitation[] = [];
  for (const [id, d] of Object.entries(byDoc)) {
    lines.push(urdu
      ? `• ${id} (${d.type}): ${d.values} قدر (${d.high} زیادہ، ${d.medium} درمیانی، ${d.low} کم اعتماد، ${d.unreadable} ناقابلِ مطالعہ)`
      : `• ${id} (${d.type}): ${d.values} values (${d.high} high, ${d.medium} medium, ${d.low} low confidence, ${d.unreadable} unreadable)`);
    for (const n of d.notable.slice(0, 3)) lines.push(`  – ${n.field}: ${n.value} (${n.conf})`);
    for (const c of d.cites) allCites.push(c);
  }
  const intro = urdu ? "ماڈل نے اس کیس کی دستاویزات سے کیا پڑھا:\n\n" : "What the model read from this case's documents:\n\n";
  const suffix = urdu
    ? "\n\nماڈل جو قدر نہ پڑھ سکے وہ ناقابلِ مطالعہ درج ہوتی ہے، کبھی گھڑی نہیں جاتی۔ ہر پڑھائی اپنا صفحہ اور اقتباس رکھتی ہے۔ نیچے کے حوالے اسی طرف لے جاتے ہیں۔"
    : "\n\nA field the model could not read is recorded as unreadable, never guessed. Every reading keeps the page and snippet it came from. The citations below lead to them.";
  return { text: intro + lines.join("\n") + suffix, confidence: "high", citations: dedupeCitations(allCites), grounded: true, intent: "extractions" };
}

function answerDecisions(items: ReviewItem[], urdu: boolean): AssistantReply {
  const decided = items.filter((i) => i.decision !== "pending");
  const approved = items.filter((i) => i.decision === "approved").length;
  const rejected = items.filter((i) => i.decision === "rejected").length;
  const pending = items.length - decided.length;
  if (decided.length === 0) {
    return { text: urdu ? "ابھی کوئی فیصلہ نہیں ہوا۔ ہر آئٹم انسانی فیصلے کا منتظر ہے۔ جائزہ اسکرین پر فیصلہ کریں۔" : "Nothing has been decided yet. Every item is still waiting for a human decision, taken on the Review screen.", confidence: "high", citations: [], grounded: true, intent: "decisions" };
  }
  const ordered = [...decided].sort((a, b) => (a.decided_at ?? "").localeCompare(b.decided_at ?? ""));
  const lines = ordered.map((item) => {
    const reason = item.rejection_reason
      ? (urdu ? `؛ وجہ: ${item.rejection_reason}` : `; reason: ${item.rejection_reason}`)
      : "";
    const when = item.decided_at ? item.decided_at.replace("T", " ").replace("Z", "") : "—";
    return urdu
      ? `• ${item.review_item_id} (${item.ledger_entry.party_name}، ${money(item.ledger_entry.amount, item.ledger_entry.currency)}): ${item.decision}، ${item.decided_by ?? "—"} نے ${when} پر${reason}`
      : `• ${item.review_item_id} (${item.ledger_entry.party_name}, ${money(item.ledger_entry.amount, item.ledger_entry.currency)}): ${item.decision} by ${item.decided_by ?? "—"} at ${when}${reason}`;
  });
  const intro = urdu
    ? `اب تک ${items.length} میں سے ${approved} آئٹم منظور اور ${rejected} مسترد ہوئے؛ ${pending} ابھی زیر التوا ہیں:\n\n`
    : `So far ${approved} item${approved !== 1 ? "s" : ""} approved and ${rejected} rejected, out of ${items.length}; ${pending} still pending:\n\n`;
  const suffix = urdu
    ? "\n\nہر فیصلہ آڈیٹر کا اپنا ہے اور ٹریل میں درج ہے؛ اسسٹنٹ کبھی منظور یا مسترد نہیں کرتا۔"
    : "\n\nEvery decision is the auditor's own and is recorded in the trail; the assistant never approves or rejects anything.";
  return { text: intro + lines.join("\n") + suffix, confidence: "high", citations: citationsFor(ordered, []), grounded: true, intent: "decisions" };
}

function answerReports(urdu: boolean): AssistantReply {
  return { text: urdu
    ? "اس کیس کے لیے ابھی کوئی رپورٹ نہیں بنی۔ جب آئٹمز کے فیصلے ہو جائیں تو رپورٹس اسکرین سے بنائیں۔ وہ ٹریل میں درج ہوتی ہے اور بعد میں نہیں بدلتی۔"
    : "No report has been generated for this case yet. Once the items have their decisions, generate one from the Reports screen. It is recorded in the trail and never changes afterwards.",
    confidence: "high", citations: [], grounded: true, intent: "reports" };
}

function answerHistory(items: ReviewItem[], urdu: boolean): AssistantReply {
  const events: Array<{ when: string; action: string; actor: string; detail: string }> = [];
  for (const item of items) {
    if (item.decision === "approved" || item.decision === "rejected") {
      events.push({
        when: item.decided_at ? item.decided_at.replace("T", " ").replace("Z", "") : "—",
        action: item.decision === "approved" ? "item_approved" : "item_rejected",
        actor: item.decided_by ?? "—",
        detail: item.decision === "rejected" && item.rejection_reason
          ? item.rejection_reason.slice(0, 90) : `${item.ledger_entry.party_name}, ${money(item.ledger_entry.amount, item.ledger_entry.currency)}`,
      });
    }
  }
  if (events.length === 0) {
    return { text: urdu ? "اس کیس کا ٹریل خالی ہے۔" : "The trail for this case is empty.", confidence: "high", citations: [], grounded: true, intent: "history" };
  }
  const recent = [...events].sort((a, b) => b.when.localeCompare(a.when)).slice(0, 8);
  const lines = recent.map((ev) => {
    const detail = ev.detail ? `: ${ev.detail}` : "";
    return urdu ? `• ${ev.when} · ${ev.action} (${ev.actor})${detail}` : `• ${ev.when} · ${ev.action} by ${ev.actor}${detail}`;
  });
  const intro = urdu
    ? `اس کیس کے ٹریل میں ${events.length} اندراج ہیں۔ حال ہی کے:\n\n`
    : `The trail records ${events.length} event${events.length !== 1 ? "s" : ""} for this case. Most recent:\n\n`;
  const suffix = urdu
    ? "\n\nٹریل صرف جمع ہونے والا ہے: کوئی اندراج کسی کے ہاتھوں نہیں بدل سکتا، نہ مٹ سکتا؛ نہ آپ کے ہاتھوں، نہ سسٹم کے۔"
    : "\n\nThe trail is append-only: no entry can be edited or removed, by anyone, including this system.";
  return { text: intro + lines.join("\n") + suffix, confidence: "high", citations: [], grounded: true, intent: "history" };
}

function answerTotals(items: ReviewItem[]): AssistantReply {
  if (items.length === 0) return { text: "The ledger has no rows.", confidence: "high", citations: [], grounded: true, intent: "totals" };
  const currency = items[0].ledger_entry.currency;
  const total = items.reduce((s, i) => s + i.ledger_entry.amount, 0);
  const matchedTotal = items.filter((i) => i.match.status === "matched").reduce((s, i) => s + i.ledger_entry.amount, 0);
  const partialTotal = items.filter((i) => i.match.status === "partial").reduce((s, i) => s + i.ledger_entry.amount, 0);
  const unmatchedTotal = items.filter((i) => i.match.status === "unmatched").reduce((s, i) => s + i.ledger_entry.amount, 0);
  const largest = items.reduce((a, b) => (b.ledger_entry.amount > a.ledger_entry.amount ? b : a));
  const dates = items.map((i) => i.ledger_entry.date).sort();
  return {
    text: `The ${items.length} ledger rows total ${money(total, currency)}, from ${dates[0]} to ${dates[dates.length - 1]}. Matched rows account for ${money(matchedTotal, currency)}, partial matches ${money(partialTotal, currency)}, and unmatched rows ${money(unmatchedTotal, currency)}. The largest single row is ${money(largest.ledger_entry.amount, largest.ledger_entry.currency)} to ${largest.ledger_entry.party_name} (${largest.review_item_id}). These are payments as recorded in the ledger; the ledger carries no income or profit figures.`,
    confidence: "high", citations: citationsFor([largest], []), grounded: true, intent: "totals",
  };
}

function answerSearchAmount(items: ReviewItem[], amount: number): AssistantReply {
  const currency = items[0]?.ledger_entry.currency ?? "PKR";
  const exact = items.filter((i) => Math.abs(i.ledger_entry.amount) === amount);
  const near = items.filter((i) => !exact.includes(i) && Math.abs(Math.abs(i.ledger_entry.amount) - amount) <= amount * 0.01);
  const bank = items.filter((i) => !exact.includes(i) && i.bank_transaction !== null && Math.abs(i.bank_transaction!.amount) === amount);
  if (!exact.length && !near.length && !bank.length) {
    return { text: `No payment of ${money(amount, currency)} appears in the ledger or the bank statement, and nothing within 1% of it.`, confidence: "high", citations: [], grounded: true, intent: "search_amount" };
  }
  const fmt = (item: ReviewItem) => `• ${item.ledger_entry.party_name}, ${money(item.ledger_entry.amount, item.ledger_entry.currency)} on ${item.ledger_entry.date} (${item.review_item_id}): ${item.match.reason}`;
  const parts: string[] = [];
  if (exact.length) parts.push(`Exactly ${money(amount, currency)} (${exact.length}):\n${exact.map(fmt).join("\n")}`);
  if (near.length) parts.push(`Within 1% (${near.length}):\n${near.map(fmt).join("\n")}`);
  if (bank.length) parts.push(`The bank statement shows that amount on these rows (${bank.length}):\n${bank.map(fmt).join("\n")}`);
  return { text: parts.join("\n\n"), confidence: "high", citations: citationsFor([...exact, ...near, ...bank], []), grounded: true, intent: "search_amount" };
}

function answerTopVendors(items: ReviewItem[]): AssistantReply {
  const totals: Record<string, number> = {};
  const counts: Record<string, number> = {};
  const names: Record<string, string> = {};
  for (const item of items) {
    const key = item.ledger_entry.party_name.toLowerCase().replace(/[^a-z0-9\s]/g, "").trim();
    totals[key] = (totals[key] ?? 0) + item.ledger_entry.amount;
    counts[key] = (counts[key] ?? 0) + 1;
    names[key] ??= item.ledger_entry.party_name;
  }
  const currency = items[0]?.ledger_entry.currency ?? "PKR";
  const grand = Object.values(totals).reduce((s, v) => s + v, 0);
  const ranked = Object.keys(totals).sort((a, b) => totals[b] - totals[a]).slice(0, 5);
  const lines = ranked.map((k) => `• ${names[k]}: ${money(totals[k], currency)} over ${counts[k]} payment(s), ${((totals[k] / grand) * 100).toFixed(1)}% of the total`);
  const vendorCount = Object.keys(totals).length;
  return {
    text: `The largest parties by amount paid, out of ${vendorCount} (total ${money(grand, currency)}):\n\n${lines.join("\n")}`,
    confidence: "high",
    citations: citationsFor(ranked.flatMap((k) => items.filter((i) => i.ledger_entry.party_name === names[k]).slice(0, 2)), []),
    grounded: true, intent: "top_vendors",
  };
}

// --- The results row by row, and the evidence behind them (mirror queries.py) ----

/** How many rows a listing prints before "…and N more". Counts always cover every row. */
const LIST_CAP = 25;

function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

function more(count: number): string {
  return count > 0 ? `\n\n…and ${count} more.` : "";
}

function counterpart(item: ReviewItem): string {
  const parts: string[] = [];
  if (item.bank_transaction) {
    const page = item.bank_transaction.source?.page ? `, p.${item.bank_transaction.source.page}` : "";
    parts.push(`bank line ${item.bank_transaction.bank_row_id} (${item.bank_transaction.date}${page})`);
  }
  if (item.invoice) parts.push(`invoice ${item.invoice.invoice_number}`);
  return parts.length ? parts.join("; ") : "no bank line and no invoice";
}

/** The ledger row, the bank line, the invoice, and the flags behind each item. */
function itemCitations(items: ReviewItem[]): AssistantCitation[] {
  const collected: AssistantCitation[] = [];
  const push = (citation: AssistantCitation | null) => {
    if (citation) collected.push(citation);
  };
  for (const item of items) {
    push(cite(item.ledger_entry.source));
    push(cite(item.bank_transaction?.source));
    push(cite(item.invoice?.source));
    item.flags.forEach((flag) => push(cite(flag.source)));
  }
  return dedupeCitations(collected, 8);
}

function byDateThenId(a: ReviewItem, b: ReviewItem): number {
  return a.ledger_entry.date.localeCompare(b.ledger_entry.date) || a.review_item_id.localeCompare(b.review_item_id);
}

function answerMatches(items: ReviewItem[], status: MatchStatus | null): AssistantReply {
  const chosen = (status ? items.filter((i) => i.match.status === status) : [...items]).sort(byDateThenId);
  const currency = items[0]?.ledger_entry.currency ?? "PKR";
  const total = chosen.reduce((s, i) => s + i.ledger_entry.amount, 0);
  const lines = chosen.slice(0, LIST_CAP).map(
    (i) =>
      `• ${i.ledger_entry.party_name}, ${money(i.ledger_entry.amount, i.ledger_entry.currency)} on ${i.ledger_entry.date} (${i.review_item_id}): ${i.match.status} (${i.match.match_strength}) by ${i.match.rule_id} with ${counterpart(i)}. ${i.match.reason}`,
  );
  const body = lines.join("\n") + more(chosen.length - LIST_CAP);
  if (status) {
    if (chosen.length === 0) {
      return { text: `No row in this case is ${status}.`, confidence: "high", citations: [], grounded: true, intent: "matches" };
    }
    return { text: `${plural(chosen.length, `${status} row`)}, totalling ${money(total, currency)}:\n\n${body}`, confidence: "high", citations: itemCitations(chosen), grounded: true, intent: "matches" };
  }
  const count = (s: MatchStatus) => items.filter((i) => i.match.status === s).length;
  const strength = (s: MatchStrength) => chosen.filter((i) => i.match.match_strength === s).length;
  return {
    text:
      `How the ${items.length} ledger rows reconciled: ${count("matched")} matched, ${count("partial")} partial, ${count("unmatched")} unmatched; ` +
      `match strength ${strength("high")} high, ${strength("medium")} medium, ${strength("low")} low. The rows total ${money(total, currency)}.\n\n${body}\n\n` +
      "Matching is deterministic code: the same rows always reconcile the same way, and the rule that decided each row is named. The decision on each row stays yours.",
    confidence: "high", citations: itemCitations(chosen), grounded: true, intent: "matches",
  };
}

// One thing by its identifier — mirrors planner.reference_named and queries._find_items.

const IDENTIFIER = /(?<![A-Za-z0-9])([A-Za-z]{2,6})(?:[-/][A-Za-z0-9]+)+(?![A-Za-z0-9])/g;
const KNOWN_PREFIXES = ["RI", "LED", "BNK", "INV", "DOC", "FLG", "RPT", "AUD", "CASE"];
const NUMBERED = /(?<![a-z0-9])(item|items|ri|row|rows|entry|line|invoice|invoices|inv|bill|flag)\s*(?:number|no\.?|num|#)?\s*(\d{1,6})(?![0-9,.])/;
const NUMBERED_KIND: Record<string, string> = {
  item: "ITEM", items: "ITEM", ri: "ITEM", row: "ROW", rows: "ROW", entry: "ROW", line: "ROW",
  invoice: "INVOICE", invoices: "INVOICE", inv: "INVOICE", bill: "INVOICE", flag: "FLAG",
};

function normaliseReference(value: string | null | undefined): string {
  return (value ?? "").toUpperCase().replace(/[^A-Z0-9]+/g, "");
}

function referencesOf(item: ReviewItem): string[] {
  const refs: Array<string | null | undefined> = [item.review_item_id, item.ledger_entry.ledger_row_id, item.ledger_entry.source?.document_id];
  if (item.bank_transaction) refs.push(item.bank_transaction.bank_row_id, item.bank_transaction.source?.document_id);
  if (item.invoice) refs.push(item.invoice.invoice_id, item.invoice.invoice_number, item.invoice.source?.document_id);
  item.flags.forEach((flag) => refs.push(flag.flag_id));
  return refs.filter((ref): ref is string => Boolean(ref));
}

function referenceNamed(question: string, items: ReviewItem[]): string | null {
  const known = new Map<string, string>();
  const prefixes = new Set(KNOWN_PREFIXES);
  for (const item of items) {
    for (const ref of referencesOf(item)) {
      known.set(normaliseReference(ref), ref);
      const head = /^[A-Za-z]+/.exec(ref);
      if (head) prefixes.add(head[0].toUpperCase());
    }
  }
  const tokens = question.match(/[A-Za-z0-9][A-Za-z0-9/-]*/g) ?? [];
  for (let index = 0; index < tokens.length; index++) {
    const candidates = [tokens[index]];
    if (index + 1 < tokens.length) candidates.push(tokens[index] + tokens[index + 1]);
    for (const candidate of candidates) {
      const norm = normaliseReference(candidate);
      const hit = norm.length >= 4 ? known.get(norm) : undefined;
      if (hit) return hit;
    }
  }
  for (const m of question.matchAll(IDENTIFIER)) {
    if (prefixes.has(m[1].toUpperCase()) && /\d/.test(m[0])) return m[0].toUpperCase();
  }
  const numbered = NUMBERED.exec(question.toLowerCase());
  if (numbered) return `${NUMBERED_KIND[numbered[1]]}:${numbered[2]}`;
  return null;
}

function suffixNumber(identifier: string): number | null {
  const m = /(\d+)$/.exec(identifier);
  return m ? parseInt(m[1], 10) : null;
}

function findItems(items: ReviewItem[], reference: string): ReviewItem[] {
  if (reference.includes(":")) {
    const [kind, digits] = reference.split(":", 2);
    const number = parseInt(digits, 10);
    return items.filter((item) => {
      if (kind === "ITEM") return suffixNumber(item.review_item_id) === number;
      if (kind === "ROW") return item.ledger_entry.source?.row_number === number || suffixNumber(item.ledger_entry.ledger_row_id) === number;
      if (kind === "INVOICE") {
        return Boolean(item.invoice && (normaliseReference(item.invoice.invoice_number).endsWith(digits) || normaliseReference(item.invoice.invoice_id).endsWith(digits)));
      }
      if (kind === "FLAG") return item.flags.some((flag) => suffixNumber(flag.flag_id) === number);
      return false;
    });
  }
  const wanted = normaliseReference(reference);
  if (!wanted) return [];
  return items.filter((item) => referencesOf(item).some((ref) => normaliseReference(ref) === wanted));
}

function referenceLabel(reference: string): string {
  if (!reference.includes(":")) return reference;
  const [kind, digits] = reference.split(":", 2);
  const labels: Record<string, string> = { ITEM: `item ${digits}`, ROW: `row ${digits}`, INVOICE: `invoice ${digits}`, FLAG: `flag ${digits}` };
  return labels[kind] ?? reference;
}

function decidedAt(item: ReviewItem): string {
  return item.decided_at ? item.decided_at.replace("T", " ").slice(0, 16) : "-";
}

function itemCard(item: ReviewItem): string {
  const ledger = item.ledger_entry;
  const bank = item.bank_transaction;
  const invoice = item.invoice;
  const lines = [`${item.review_item_id}: ${ledger.party_name}, ${money(ledger.amount, ledger.currency)} on ${ledger.date}.`];
  lines.push(`• Ledger: ${ledger.ledger_row_id} (sheet row ${ledger.source?.row_number ?? "-"}), "${ledger.description ?? "-"}", account ${ledger.account_code ?? "-"}.`);
  lines.push(
    bank
      ? `• Bank statement: ${bank.bank_row_id} on ${bank.date}, ${money(bank.amount, bank.currency)}, "${bank.description}" (page ${bank.source?.page ?? "-"}).`
      : "• Bank statement: none. No bank line was found for this row.",
  );
  lines.push(
    invoice
      ? `• Invoice: ${invoice.invoice_number} dated ${invoice.date}, ${money(invoice.amount, invoice.currency)}, ${invoice.party_name} (page ${invoice.source?.page ?? "-"}).`
      : "• Invoice: none attached.",
  );
  lines.push(`• Match: ${item.match.status} (${item.match.match_strength} strength) by rule ${item.match.rule_id}. ${item.match.reason}`);
  lines.push(
    item.flags.length
      ? `• Flags (${item.flags.length}): ${item.flags.map((flag) => `${flag.rule_id} (${flag.severity}): ${flag.explanation}`).join("; ")}`
      : "• Flags: none.",
  );
  const unreadable = item.evidence.filter((reading) => reading.unreadable).length;
  lines.push(`• Extraction confidence: ${item.extraction_confidence} (${plural(item.evidence.length, "reading")}, ${unreadable} unreadable).`);
  if (item.decision === "pending") {
    lines.push("• Decision: pending, awaiting an explicit human decision on the Review screen.");
  } else {
    const reason = item.rejection_reason ? `; reason: ${item.rejection_reason.replace(/\.$/, "")}` : "";
    lines.push(`• Decision: ${item.decision} by ${item.decided_by ?? "-"} at ${decidedAt(item)}${reason}.`);
  }
  return lines.join("\n");
}

function answerItem(items: ReviewItem[], reference: string): AssistantReply {
  const hits = findItems(items, reference);
  const label = referenceLabel(reference);
  if (hits.length === 0) {
    return {
      text: `No item in this case carries the reference "${label}". I can look up a review item (RI-0005), a ledger row (LED-0014 or "row 16"), a bank line (BNK-0051), an invoice number (INV-2026-0087 or "invoice 0087"), or a flag (FLG-0009).`,
      confidence: "high", citations: [], grounded: true, intent: "item",
    };
  }
  if (hits.length > 3) {
    const lines = hits.map((i) => `• ${i.ledger_entry.party_name}, ${money(i.ledger_entry.amount, i.ledger_entry.currency)} on ${i.ledger_entry.date} (${i.review_item_id}): ${i.match.status}, decision ${i.decision}`);
    return { text: `${hits.length} items reference "${label}":\n\n${lines.join("\n")}\n\nName one of them for its full detail.`, confidence: "high", citations: itemCitations(hits), grounded: true, intent: "item" };
  }
  const cards = hits.map(itemCard).join("\n\n");
  return { text: hits.length > 1 ? `"${label}" matches ${hits.length} items:\n\n${cards}` : cards, confidence: "high", citations: itemCitations(hits), grounded: true, intent: "item" };
}

function answerInvoices(items: ReviewItem[]): AssistantReply {
  const byId = new Map<string, { invoice: Invoice; paidBy: ReviewItem[] }>();
  for (const item of items) {
    if (!item.invoice) continue;
    const entry = byId.get(item.invoice.invoice_id) ?? { invoice: item.invoice, paidBy: [] };
    entry.paidBy.push(item);
    byId.set(item.invoice.invoice_id, entry);
  }
  const rows = [...byId.values()].sort((a, b) => a.invoice.date.localeCompare(b.invoice.date) || a.invoice.invoice_number.localeCompare(b.invoice.invoice_number));
  const without = items.filter((i) => !i.invoice).length;
  const currency = items[0]?.ledger_entry.currency ?? "PKR";
  if (rows.length === 0) {
    return {
      text: `No invoice is attached to any ledger row in this case: all ${without} rows have a bank line only, or nothing at all. Ask "which rows are missing evidence?" for the list.`,
      confidence: "high", citations: [], grounded: true, intent: "invoices",
    };
  }
  const total = rows.reduce((s, r) => s + r.invoice.amount, 0);
  const lines = rows.slice(0, LIST_CAP).map(({ invoice, paidBy }) => {
    const settled = paidBy.map((i) => `${i.review_item_id} on ${i.ledger_entry.date} (${i.match.status}, ${i.decision})`).join(", ");
    const twice = paidBy.length > 1 ? "; the same invoice paid more than once" : "";
    return `• ${invoice.invoice_number}: ${invoice.party_name}, ${money(invoice.amount, invoice.currency)}, dated ${invoice.date} (document ${invoice.source.document_id}, page ${invoice.source.page ?? "-"}). Settled by ${plural(paidBy.length, "ledger row")}: ${settled}${twice}`;
  });
  const citations = rows.map((r) => cite(r.invoice.source)).filter((c): c is AssistantCitation => c !== null);
  return {
    text:
      `${plural(rows.length, "invoice")} in the evidence, totalling ${money(total, currency)}; ${plural(without, "ledger row")} ${without === 1 ? "has" : "have"} no invoice behind ${without === 1 ? "it" : "them"}:\n\n` +
      `${lines.join("\n")}${more(rows.length - LIST_CAP)}\n\nName an invoice by its number for the full match detail behind it.`,
    confidence: "high", citations: dedupeCitations(citations, 8), grounded: true, intent: "invoices",
  };
}

function answerBank(items: ReviewItem[]): AssistantReply {
  const byId = new Map<string, { bank: BankTransaction; pays: ReviewItem[] }>();
  for (const item of items) {
    if (!item.bank_transaction) continue;
    const entry = byId.get(item.bank_transaction.bank_row_id) ?? { bank: item.bank_transaction, pays: [] };
    entry.pays.push(item);
    byId.set(item.bank_transaction.bank_row_id, entry);
  }
  const rows = [...byId.values()].sort((a, b) => a.bank.date.localeCompare(b.bank.date) || a.bank.bank_row_id.localeCompare(b.bank.bank_row_id));
  if (rows.length === 0) {
    return { text: "No bank statement line is matched to any ledger row in this case.", confidence: "high", citations: [], grounded: true, intent: "bank" };
  }
  const without = items.filter((i) => !i.bank_transaction).length;
  const currency = items[0]?.ledger_entry.currency ?? "PKR";
  const total = rows.reduce((s, r) => s + r.bank.amount, 0);
  const pageNumbers = rows.map((r) => r.bank.source.page).filter((p): p is number => typeof p === "number");
  const pages = [...new Set(pageNumbers)].sort((a, b) => a - b).join(", ") || "-";
  const lines = rows.slice(0, LIST_CAP).map(({ bank, pays }) => {
    const balance = bank.balance != null ? `, balance ${money(bank.balance, bank.currency)}` : "";
    const paid = pays.map((i) => `${i.review_item_id} ${i.ledger_entry.party_name}`).join(", ");
    return `• ${bank.bank_row_id}: ${bank.date}, ${money(bank.amount, bank.currency)}, "${bank.description}" (page ${bank.source.page ?? "-"}${balance}) → pays ${paid}`;
  });
  const citations = rows.map((r) => cite(r.bank.source)).filter((c): c is AssistantCitation => c !== null);
  return {
    text:
      `${plural(rows.length, "bank statement line")} ${rows.length === 1 ? "is" : "are"} matched to ledger rows, totalling ${money(total, currency)}, on page(s) ${pages}; ` +
      `${plural(without, "ledger row")} ${without === 1 ? "has" : "have"} no bank line.\n\n${lines.join("\n")}${more(rows.length - LIST_CAP)}\n\n` +
      "The statement is read by the vision model, and every line keeps the page it came from. Only lines matched to a ledger row are listed here. The Documents screen shows the whole statement.",
    confidence: "high", citations: dedupeCitations(citations, 8), grounded: true, intent: "bank",
  };
}

function distinctParties(items: ReviewItem[]): number {
  return new Set(items.map((i) => i.ledger_entry.party_name.toLowerCase().replace(/[^a-z0-9\s]/g, "").trim())).size;
}

function answerLedger(items: ReviewItem[]): AssistantReply {
  if (items.length === 0) return { text: "The ledger has no rows.", confidence: "high", citations: [], grounded: true, intent: "ledger" };
  const ordered = [...items].sort(byDateThenId);
  const currency = ordered[0].ledger_entry.currency;
  const total = items.reduce((s, i) => s + i.ledger_entry.amount, 0);
  const lines = ordered.slice(0, LIST_CAP).map((i) => {
    const flags = i.flags.length ? `, ${plural(i.flags.length, "flag")}` : "";
    return `• ${i.ledger_entry.date} · ${i.ledger_entry.party_name}, ${money(i.ledger_entry.amount, i.ledger_entry.currency)} (${i.review_item_id}, sheet row ${i.ledger_entry.source?.row_number ?? "-"}): ${i.match.status}, ${i.decision}${flags}; description: ${i.ledger_entry.description ?? "-"}`;
  });
  return {
    text:
      `The ledger has ${plural(items.length, "row")} totalling ${money(total, currency)}, dated ${ordered[0].ledger_entry.date} to ${ordered[ordered.length - 1].ledger_entry.date}, to ${plural(distinctParties(items), "party", "parties")}:\n\n` +
      `${lines.join("\n")}${more(items.length - LIST_CAP)}\n\n` +
      "The ledger is the client's own record, read by spreadsheet code; every row above was checked against the bank statement and the invoices. Ask \"match results\" for how each one reconciled.",
    confidence: "high", citations: citationsFor(ordered.slice(0, 8), []), grounded: true, intent: "ledger",
  };
}

// A day or a month — mirrors planner.date_named and queries._search_date.

const MONTHS: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
  jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, aug: 8, sep: 9, sept: 9, oct: 10, nov: 11, dec: 12,
};
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const MONTH_ALT = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join("|");
/** Month names that may stand alone; "may" needs a day or a year beside it — "may I ask" is not a month. */
const MONTH_ALONE_ALT = Object.keys(MONTHS).filter((name) => name.length > 3 && name !== "may").join("|");

interface DateNamed {
  year: number;
  month: number;
  /** null when only a month was named. */
  day: number | null;
}

function dateNamed(question: string, defaultYear: number): DateNamed | null {
  const text = question.toLowerCase();
  let m = /(?<![0-9])(20\d{2})-(\d{1,2})-(\d{1,2})(?![0-9])/.exec(text);
  if (m) return { year: +m[1], month: +m[2], day: +m[3] };
  m = /(?<![0-9])(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})(?![0-9])/.exec(text);
  if (m) return { year: +m[3], month: +m[2], day: +m[1] };
  m = new RegExp(`(?<![0-9])(\\d{1,2})(?:st|nd|rd|th)?\\s+(?:of\\s+)?(${MONTH_ALT})(?:[,\\s]+(20\\d{2}))?(?![a-z])`).exec(text);
  if (m) return { year: m[3] ? +m[3] : defaultYear, month: MONTHS[m[2]], day: +m[1] };
  m = new RegExp(`(?<![a-z])(${MONTH_ALT})\\s+(\\d{1,2})(?:st|nd|rd|th)?(?:[,\\s]+(20\\d{2}))?(?![0-9,.])`).exec(text);
  if (m) return { year: m[3] ? +m[3] : defaultYear, month: MONTHS[m[1]], day: +m[2] };
  m = new RegExp(`(?<![a-z])(${MONTH_ALT})\\s+(20\\d{2})(?![0-9])`).exec(text);
  if (m) return { year: +m[2], month: MONTHS[m[1]], day: null };
  m = new RegExp(`(?<![a-z])(${MONTH_ALONE_ALT})(?![a-z])`).exec(text);
  if (m) return { year: defaultYear, month: MONTHS[m[1]], day: null };
  return null;
}

function defaultYearOf(items: ReviewItem[]): number {
  const counts = new Map<number, number>();
  for (const item of items) {
    const year = parseInt(item.ledger_entry.date.slice(0, 4), 10);
    counts.set(year, (counts.get(year) ?? 0) + 1);
  }
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  return ranked[0]?.[0] ?? new Date().getFullYear();
}

function answerSearchDate(items: ReviewItem[], when: DateNamed): AssistantReply {
  const two = (n: number) => String(n).padStart(2, "0");
  const monthPrefix = `${when.year}-${two(when.month)}`;
  const target = when.day === null ? null : `${monthPrefix}-${two(when.day)}`;
  const hit = (value: string | null | undefined): boolean => {
    if (!value) return false;
    return target === null ? value.startsWith(monthPrefix) : value.slice(0, 10) === target;
  };
  const label = target ?? `${MONTH_NAMES[when.month - 1]} ${when.year}`;
  const ledger = items.filter((i) => hit(i.ledger_entry.date));
  const bank = items.filter((i) => hit(i.bank_transaction?.date));
  const invoices: ReviewItem[] = [];
  const seenInvoices = new Set<string>();
  for (const item of items) {
    if (item.invoice && hit(item.invoice.date) && !seenInvoices.has(item.invoice.invoice_id)) {
      seenInvoices.add(item.invoice.invoice_id);
      invoices.push(item);
    }
  }
  const decided = items.filter((i) => hit(i.decided_at));
  const currency = items[0]?.ledger_entry.currency ?? "PKR";
  if (!ledger.length && !bank.length && !invoices.length && !decided.length) {
    const dates = items.map((i) => i.ledger_entry.date).sort();
    return {
      text: `Nothing in this case is dated ${label}: no ledger row, bank line, invoice, or decision. The ledger runs from ${dates[0] ?? "-"} to ${dates[dates.length - 1] ?? "-"}.`,
      confidence: "high", citations: [], grounded: true, intent: "search_date",
    };
  }
  const total = ledger.reduce((s, i) => s + i.ledger_entry.amount, 0);
  const parts = [
    `${target ? "On" : "In"} ${label}: ${plural(ledger.length, "ledger row")} totalling ${money(total, currency)}, ${plural(bank.length, "bank line")}, ${plural(invoices.length, "invoice")} dated then, ${plural(decided.length, "decision")} taken.`,
  ];
  if (ledger.length) {
    parts.push("Ledger rows:\n" + ledger.map((i) => `• ${i.ledger_entry.party_name}, ${money(i.ledger_entry.amount, i.ledger_entry.currency)} (${i.review_item_id}): ${i.match.status}, decision ${i.decision}. ${i.match.reason}`).join("\n"));
  }
  if (bank.length) {
    parts.push("Bank lines:\n" + bank.map((i) => {
      const line = i.bank_transaction as BankTransaction;
      return `• ${line.bank_row_id}: ${money(line.amount, line.currency)}, "${line.description}" (page ${line.source.page ?? "-"}) → pays ${i.review_item_id} ${i.ledger_entry.party_name}`;
    }).join("\n"));
  }
  if (invoices.length) {
    parts.push("Invoices:\n" + invoices.map((i) => {
      const invoice = i.invoice as Invoice;
      return `• ${invoice.invoice_number}: ${money(invoice.amount, invoice.currency)}, ${invoice.party_name} → settled by ${i.review_item_id}`;
    }).join("\n"));
  }
  if (decided.length) {
    parts.push("Decisions:\n" + decided.map((i) => `• ${i.review_item_id}: ${i.decision} by ${i.decided_by ?? "-"} at ${decidedAt(i)}${i.rejection_reason ? `; reason: ${i.rejection_reason}` : ""}`).join("\n"));
  }
  const involved = [...new Set([...ledger, ...bank, ...invoices, ...decided])];
  return { text: parts.join("\n\n"), confidence: "high", citations: citationsFor(involved.slice(0, 8), []), grounded: true, intent: "search_date" };
}

function answerCaseInfo(items: ReviewItem[], dashboard: DashboardSummary | null): AssistantReply {
  const currency = items[0]?.ledger_entry.currency ?? "PKR";
  const dates = items.map((i) => i.ledger_entry.date).sort();
  const start = dashboard?.period_start ?? dates[0] ?? null;
  const end = dashboard?.period_end ?? dates[dates.length - 1] ?? null;
  const derived = !dashboard?.period_start && dates.length > 0;
  const count = (s: MatchStatus) => items.filter((i) => i.match.status === s).length;
  const decided = (d: ReviewDecision) => items.filter((i) => i.decision === d).length;
  const total = items.reduce((s, i) => s + i.ledger_entry.amount, 0);
  const flags = items.reduce((s, i) => s + i.flags.length, 0);
  const period = start && end ? ` Period ${start} to ${end}${derived ? " (taken from the ledger rows; the case record sets no period)" : ""}.` : "";
  return {
    text:
      `${dashboard?.client_name ?? "This client"}: case ${dashboard?.case_id ?? "—"}, status ready for review.${period} ` +
      `${plural(items.length, "ledger row")} totalling ${money(total, currency)} across ${plural(distinctParties(items), "party", "parties")}: ` +
      `${count("matched")} matched, ${count("partial")} partial, ${count("unmatched")} unmatched; ${decided("approved")} approved, ${decided("rejected")} rejected, ${decided("pending")} pending; ${plural(flags, "flag")}.`,
    confidence: "high", citations: [], grounded: true, intent: "case_info",
  };
}

function answerConfidence(items: ReviewItem[]): AssistantReply {
  const rank: Record<Confidence, number> = { high: 0, medium: 1, low: 2 };
  const level = (c: Confidence) => items.filter((i) => i.extraction_confidence === c).length;
  const unreadable = items.reduce((s, i) => s + i.evidence.filter((reading) => reading.unreadable).length, 0);
  const weak = items
    .filter((i) => i.extraction_confidence !== "high")
    .sort((a, b) => rank[b.extraction_confidence] - rank[a.extraction_confidence] || a.review_item_id.localeCompare(b.review_item_id));
  if (weak.length === 0 && unreadable === 0) {
    return { text: `Every one of the ${items.length} items was read with high confidence, and no source value was unreadable.`, confidence: "high", citations: [], grounded: true, intent: "confidence" };
  }
  const lines = weak.slice(0, LIST_CAP).map((i) => {
    const weakest = [...i.evidence].sort((a, b) => (a.unreadable ? 0 : 1) - (b.unreadable ? 0 : 1) || rank[b.extraction_confidence] - rank[a.extraction_confidence])[0];
    const reading = !weakest
      ? "no reading recorded"
      : weakest.unreadable
        ? `${weakest.field} unreadable in ${weakest.source.document_id}`
        : `${weakest.field} = ${String(weakest.value)} (${weakest.extraction_confidence}) from ${weakest.source.document_id}${weakest.source.page ? ` page ${weakest.source.page}` : ""}`;
    return `• ${i.ledger_entry.party_name}, ${money(i.ledger_entry.amount, i.ledger_entry.currency)} on ${i.ledger_entry.date} (${i.review_item_id}): ${i.extraction_confidence} confidence; weakest reading: ${reading}`;
  });
  const middle = lines.length ? `\n\nThe ${plural(weak.length, "item")} below high confidence:\n\n${lines.join("\n")}${more(weak.length - LIST_CAP)}` : "";
  return {
    text:
      `Extraction confidence across ${items.length} items: ${level("high")} high, ${level("medium")} medium, ${level("low")} low; ${plural(unreadable, "source value")} unreadable.${middle}\n\n` +
      "Confidence is the vision model's own, rolled up as the weakest reading behind each row; match strength is a separate, deterministic score. A low-confidence reading is a reason to open the page, not a verdict.",
    confidence: "high", citations: citationsFor(weak.slice(0, 8), []), grounded: true, intent: "confidence",
  };
}

/** Extract the first amount ≥ 100 from the question, mirroring planner._amount_named. */
function amountNamed(question: string): number | null {
  const re = /(?<![A-Za-z-])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Za-z-])\d{4,}(?:\.\d+)?/g;
  for (const m of question.matchAll(re)) {
    if (m[0].length === 4 && m[0].startsWith("20") && !m[0].includes(",")) continue; // a bare year
    const value = parseFloat(m[0].replace(/,/g, ""));
    if (!isNaN(value) && value >= 100) return value;
  }
  return null;
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

  if (items.length === 0) {
    return {
      text: "There is no case data to answer from yet. Upload a bank statement, invoices, and a ledger first.",
      confidence: "low",
      citations: [],
      grounded: false,
    };
  }

  // --- Concept / glossary (EN and UR, before anything else) ---------------
  const urdu = isUrdu(question);
  const topic = topicNamed(q);
  const mentionsRuleOrFlag = matchesAny(q, "flag*", "flagged", "rule*");
  if (topic !== null && isDefinitional(q) && (DEDICATED_TOPICS.has(topic) || !mentionsRuleOrFlag)) {
    return answerConcept(topic, urdu);
  }
  if (topic !== null && !DEDICATED_TOPICS.has(topic) && !mentionsRuleOrFlag && matchesAny(q, ..._EXPLAIN)) {
    return answerConcept(topic, urdu);
  }
  // --- Beginner -----------------------------------------------------------
  if (matchesAny(q, ..._BEGINNER)) {
    return { text: urdu ? _HELP_UR : _HELP_EN, confidence: "high", citations: [], grounded: true, intent: "help" };
  }

  // --- One thing, by its identifier: "RI-0005", "invoice INV-2026-0087",
  //     "row 16". The sharpest question there is, so it goes first. ----------
  const reference = referenceNamed(question, items);
  if (reference !== null) return answerItem(items, reference);

  // --- Urdu routing (concept + beginner handled above) --------------------
  if (urdu) {
    if (matchesAny(q, ..._META)) {
      return { text: _HELP_UR, confidence: "high", citations: [], grounded: true, intent: "help" };
    }
    if (matchesAny(q, "انوائس")) return answerInvoices(items);
    if (matchesAny(q, "بینک") && !matchesAny(q, "بینک میں نہیں")) return answerBank(items);
    if (matchesAny(q, "میچ", "ملاپ", "ملان") || (matchesAny(q, "مماثل") && !matchesAny(q, "غیر مماثل"))) return answerMatches(items, null);
    if (matchesAny(q, "کلائنٹ", "کیس کی مدت", "کیس کی حیثیت")) return answerCaseInfo(items, dashboard);
    if (matchesAny(q, "تمام کیس", "ہر کیس", "کتنے کیس", "دوسرے کیس")) return answerCases(items, dashboard, true);
    if (matchesAny(q, "کیا پڑھا", "پڑھا گیا")) return answerExtractions(items, true);
    if (matchesAny(q, "فیصلے", "فیصلہ")) return answerDecisions(items, true);
    if (matchesAny(q, "رپورٹ")) return answerReports(true);
    if (matchesAny(q, "لاگ", "تاریخچہ", "کیا ہوا", "کب ہوا")) return answerHistory(items, true);
    if (matchesAny(q, "کون سے دستاویزات", "کیا اپ لوڈ")) return answerDocuments(items, true);
    // Urdu flag summary fallback
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
      citations: citationsFor(allFlagged, allFlagged.flatMap((item) => item.flags)),
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
      "near-limit",
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

  // --- A specific day or month: "what was paid on 11 June", "payments in June"
  const when = dateNamed(question, defaultYearOf(items));
  if (when !== null) return answerSearchDate(items, when);

  // --- The evidence itself, and how it reconciled --------------------------
  if (matchesAny(q, "invoice*", "bill*")) return answerInvoices(items);
  if (matchesAny(q, "bank statement*", "bank line*", "bank transaction*", "bank entr*", "bank side", "bank record*", "bank payment*", "bank row*", "bank account*", "bank balance*", "balance*", "statement line*", "statement entr*", "in the bank", "on the bank", "from the bank", "bank shows", "bank say*")) {
    return answerBank(items);
  }
  if (matchesAny(q, "partial*", "partly")) return answerMatches(items, "partial");
  if (matchesAny(q, "match*", "reconciled", "reconciliation result*", "reconciliation status*", "three-way", "three way", "counterpart*")) {
    const onlyMatched = matchesAny(q, "matched") && !matchesAny(q, "result*", "all", "every", "how", "overview", "status*", "summar*");
    return answerMatches(items, onlyMatched ? "matched" : null);
  }

  // --- Engagement record (cases, extractions, decisions, reports, history, documents) ----
  if (matchesAny(q, "all cases", "all my cases", "every case", "which cases", "how many cases", "other case*", "another case", "across cases", "what case*")) {
    return answerCases(items, dashboard, false);
  }
  if (matchesAny(q, "what did you read", "what did the model read", "what did the ai read", "what did it read", "what did you extract", "what was read", "extract*", "extraction*", "vision model*", "read from the document*")) {
    return answerExtractions(items, false);
  }
  if (matchesAny(q, "decision*", "decided", "who approved", "who rejected", "approved so far", "approvals", "sign off", "sign-off", "signoff", "what did we decide")) {
    return answerDecisions(items, false);
  }
  if (matchesAny(q, "report*", "export*", "deliverable*")) {
    return answerReports(false);
  }
  if (matchesAny(q, "history", "timeline", "what happened", "audit trail*", "trail", "event log", "who did what", "when did", "when was")) {
    return answerHistory(items, false);
  }
  if (matchesAny(q, "what document*", "which document*", "what files", "which files", "uploaded", "upload*", "documents did", "documents are", "documents have", "document list", "what sources", "which sources")) {
    return answerDocuments(items, false);
  }
  // --- How sure the reading is, and the case itself -------------------------
  if (matchesAny(q, "confiden*", "how sure", "how reliable", "how accurate", "accura*", "certain*", "uncertain*", "read correctly", "misread*", "reading quality")) {
    return answerConfidence(items);
  }
  if (matchesAny(q, "client*", "case period", "audit period", "period cover*", "period of", "which period", "what period", "date range", "case status", "case detail*", "case info*", "about this case", "about the case", "which company", "what company", "whose", "case id")) {
    return answerCaseInfo(items, dashboard);
  }

  // --- Amounts, totals, vendors -------------------------------------------
  const namedAmount = amountNamed(question);
  if (namedAmount !== null && matchesAny(q, "amount*", "payment of", "paid", "find", "search", "who", "which", "any", "look")) {
    return answerSearchAmount(items, namedAmount);
  }
  if (matchesAny(q, "top vendor*", "top supplier*", "top part*", "biggest vendor*", "largest vendor*", "most paid", "paid the most", "by vendor", "by supplier", "by party", "per vendor", "which vendor*")) {
    return answerTopVendors(items);
  }
  if (matchesAny(q, "largest", "biggest", "highest", "top payment*", "top expense*", "top 5", "top five", "top ten", "top 10")) {
    return answerTopVendors(items);
  }
  if (matchesAny(q, "total*", "sum", "how much", "expense*", "expenditure*", "spend*", "spent", "paid out", "outflow*")) {
    return answerTotals(items);
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
    q.includes("overview") ||
    matchesAny(q, "result*", "outcome*", "finding*", "everything about", "all about", "full picture", "whole picture", "so far", "how many items")
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

  // --- Every row, listed --------------------------------------------------
  if (matchesAny(q, "all items", "all the items", "every item", "each item", "all rows", "all the rows", "every row", "all entries", "all the entries", "every entry", "all transactions", "all the transactions", "every transaction", "all payments", "all the payments", "every payment", "list items", "list the items", "list all", "list everything", "show all", "show everything", "show me everything", "full list", "whole list", "entire ledger", "whole ledger", "the ledger", "ledger row*", "ledger entr*", "ledger line*", "line item*", "how many rows", "how many entries", "how many transactions", "how many payments")) {
    return answerLedger(items);
  }

  // --- Greeting / capabilities — and "can I ask you something?": yes ------
  if (
    q.trim().length < 4 ||
    q.includes("help") ||
    q.includes("hello") ||
    q.includes("what can") ||
    q.includes("salam") ||
    q.includes("hi ") ||
    matchesAny(q, ..._META)
  ) {
    return {
      text: _HELP_EN,
      confidence: "high",
      citations: [],
      grounded: true,
      intent: "help",
    };
  }

  // --- Amount fallback (a bare amount in the question) --------------------
  const fallbackAmount = amountNamed(question);
  if (fallbackAmount !== null) {
    return answerSearchAmount(items, fallbackAmount);
  }

  // --- The refusal: rule 7 made visible. A question in the audit's own words
  //     is told so, with the shapes that work; an off-topic one is declined.
  const onTopic = matchesAny(q, ..._DOMAIN);
  return {
    text: urdu ? (onTopic ? _REFUSAL_ON_TOPIC_UR : _REFUSAL_UR) : onTopic ? _REFUSAL_ON_TOPIC_EN : _REFUSAL_EN,
    confidence: "low",
    citations: [],
    grounded: false,
    intent: "unknown",
  };
}
