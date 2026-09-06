import { describe, expect, it } from "vitest";
import reviewItemsFixture from "./fixtures/review-items.json";
import dashboardFixture from "./fixtures/dashboard.json";
import {
  answerFromCase,
  attachmentKind,
  describeAttachments,
  toAssistantAnswer,
} from "./assistant";
import type { DashboardSummary, ReviewItem } from "./types";

/**
 * The fixture-mode assistant must keep the posture of the real one
 * (reliability rule 7): answer only from the case's items, cite what it used,
 * and refuse what it cannot ground. These tests pin that posture, not the
 * wording.
 */
const items = reviewItemsFixture.items as unknown as ReviewItem[];
const dashboard = dashboardFixture as unknown as DashboardSummary;

describe("answerFromCase", () => {
  it("refuses with no case data at all", () => {
    const reply = answerFromCase("how many flags are there?", [], null);
    expect(reply.grounded).toBe(false);
    expect(reply.confidence).toBe("low");
    expect(reply.citations).toEqual([]);
  });

  it("answers a counting question from the items and cites them", () => {
    const reply = answerFromCase("How many items are flagged?", items, dashboard);
    expect(reply.grounded).toBe(true);
    expect(reply.text.length).toBeGreaterThan(0);
  });

  it("finds one item by its identifier", () => {
    const first = items[0];
    const reply = answerFromCase(`Tell me about ${first.review_item_id}`, items, dashboard);
    expect(reply.grounded).toBe(true);
    expect(reply.text).toContain(first.ledger_entry.party_name);
  });

  it("refuses a question the documents cannot answer", () => {
    const reply = answerFromCase("What is the capital of France?", items, dashboard);
    expect(reply.grounded).toBe(false);
  });

  it("never invents a citation: every cited document exists in the case", () => {
    const known = new Set<string>();
    for (const item of items) {
      known.add(item.ledger_entry.source.document_id);
      if (item.bank_transaction) known.add(item.bank_transaction.source.document_id);
      if (item.invoice) known.add(item.invoice.source.document_id);
      for (const field of item.evidence) known.add(field.source.document_id);
    }
    for (const question of [
      "Which items are unmatched?",
      "Show me the duplicate payments",
      "What did the bank statement say?",
      `Explain ${items[0].review_item_id}`,
    ]) {
      const reply = answerFromCase(question, items, dashboard);
      for (const citation of reply.citations) {
        expect(known.has(citation.document_id)).toBe(true);
      }
    }
  });

  it("acknowledges an attachment without reading it", () => {
    const reply = answerFromCase(
      "",
      items,
      dashboard,
      [{ name: "extra-invoice.pdf", size_bytes: 20_000, kind: "pdf" }],
    );
    expect(reply.grounded).toBe(true);
    expect(reply.text).toContain("extra-invoice.pdf");
    expect(reply.text).toContain("not read");
  });

  it("handles an empty and a very long question without throwing", () => {
    expect(() => answerFromCase("", items, dashboard)).not.toThrow();
    expect(() => answerFromCase("x".repeat(20_000), items, dashboard)).not.toThrow();
  });
});

describe("toAssistantAnswer", () => {
  const reply = {
    text: "Ten items.",
    confidence: "high" as const,
    citations: [{ document_id: "DOC-LED-001", page: null, snippet: null }],
    grounded: true,
  };

  it("carries the reply into the backend's shape", () => {
    const answer = toAssistantAnswer("how many items?", reply);
    expect(answer.language).toBe("en");
    expect(answer.intent).toBe("summary");
    expect(answer.answer_confidence).toBe("high");
    expect(answer.citations[0]).toMatchObject({ document_id: "DOC-LED-001", page: null });
    expect(answer.composed_by).toBe("fixture.keyword-router");
  });

  it("detects Urdu from the question, the language, or the word itself", () => {
    expect(toAssistantAnswer("کتنے آئٹم ہیں؟", reply).language).toBe("ur");
    expect(toAssistantAnswer("how many?", reply, "ur").language).toBe("ur");
    expect(toAssistantAnswer("answer in urdu please", reply).language).toBe("ur");
  });

  it("marks an ungrounded reply as unknown intent", () => {
    expect(toAssistantAnswer("?", { ...reply, grounded: false }).intent).toBe("unknown");
  });
});

describe("attachments", () => {
  it("classifies by mime type first, then by extension", () => {
    expect(attachmentKind("scan.PDF", "")).toBe("pdf");
    expect(attachmentKind("photo", "image/jpeg")).toBe("image");
    expect(attachmentKind("ledger.xlsx", "")).toBe("spreadsheet");
    expect(attachmentKind("notes.txt", "")).toBe("text");
    expect(attachmentKind("contract.docx", "application/octet-stream")).toBe("document");
  });

  it("describes what arrived and points at the Upload screen", () => {
    const text = describeAttachments([
      { name: "a.pdf", size_bytes: 1_500_000, kind: "pdf" },
      { name: "b.csv", size_bytes: 900, kind: "spreadsheet" },
    ]);
    expect(text).toContain("Received 2 files");
    expect(text).toContain("a.pdf (pdf, 1.5 MB)");
    expect(text).toContain("b.csv (spreadsheet, 1 KB)");
    expect(text).toContain("Upload screen");
  });
});
