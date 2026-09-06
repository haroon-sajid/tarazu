import { beforeAll, describe, expect, it } from "vitest";

/**
 * The API client in fixture mode: the whole review flow has to work with no
 * backend, exactly as the public demo does, and it has to keep the same
 * guarantees as the live routes — every decision is explicit, nothing is
 * decided twice, and a rejection always carries a reason.
 *
 * `API_URL` is read once when the module loads, so the env is pinned before
 * the import.
 */
type Api = typeof import("./api");

let api: Api;

beforeAll(async () => {
  process.env.NEXT_PUBLIC_TARAZU_API_URL = "";
  api = await import("./api");
  expect(api.FIXTURE_MODE).toBe(true);
});

/** The sample queue ships with one approved and one rejected item already. */
const SEEDED = { approved: 1, rejected: 1 };

describe("the review queue in fixture mode", () => {
  it("lists the sample case with its items", async () => {
    const queue = await api.getReviewItems();
    expect(queue.total).toBeGreaterThan(0);
    expect(queue.items.filter((item) => item.decision === "pending").length).toBe(
      queue.total - SEEDED.approved - SEEDED.rejected,
    );
    expect(queue.case_status).toBe("ready_for_review");
  });

  it("filters by decision, match status, and flagged", async () => {
    const flagged = await api.getReviewItems({ flagged: true });
    expect(flagged.total).toBeGreaterThan(0);
    expect(flagged.items.every((item) => item.flags.length > 0)).toBe(true);
    const matched = await api.getReviewItems({ match_status: "matched" });
    expect(matched.items.every((item) => item.match.status === "matched")).toBe(true);
    const rejected = await api.getReviewItems({ decision: "rejected" });
    expect(rejected.total).toBe(SEEDED.rejected);
    expect(rejected.items.every((item) => item.rejection_reason)).toBe(true);
  });

  it("refuses to decide an item that already carries a decision", async () => {
    const decided = await api.getReviewItems({ decision: "approved" });
    await expect(api.approveReviewItem(decided.items[0].review_item_id)).rejects.toMatchObject(
      { status: 409 },
    );
  });

  it("records an approval once, and refuses a second decision", async () => {
    const queue = await api.getReviewItems({ decision: "pending" });
    const target = queue.items[0].review_item_id;

    const approved = await api.approveReviewItem(target, "Vouched.");
    expect(approved.review_item.decision).toBe("approved");
    expect(approved.review_item.decided_by).toBe(api.DEMO_USER_ID);
    expect(approved.audit_record.action).toBe("item_approved");
    expect(approved.audit_record.detail).toBe("Vouched.");

    await expect(api.approveReviewItem(target)).rejects.toMatchObject({ status: 409 });
    await expect(api.rejectReviewItem(target, "changed my mind")).rejects.toMatchObject({
      status: 409,
    });

    const audit = await api.getReviewItemAudit(target);
    expect(audit).toHaveLength(1);
    expect(audit[0].item_id).toBe(target);
  });

  it("requires a reason to reject", async () => {
    const queue = await api.getReviewItems({ decision: "pending" });
    const target = queue.items[0].review_item_id;
    await expect(api.rejectReviewItem(target, "   ")).rejects.toMatchObject({ status: 422 });
    const rejected = await api.rejectReviewItem(target, "Amount disagrees with the bank.");
    expect(rejected.review_item.decision).toBe("rejected");
    expect(rejected.review_item.rejection_reason).toBe("Amount disagrees with the bank.");
  });

  it("keeps the trail append-only and in order", async () => {
    const trail = await api.getAuditTrail();
    expect(trail.total).toBe(2);
    expect(trail.records.map((record) => record.action)).toEqual([
      "item_approved",
      "item_rejected",
    ]);
    expect(new Set(trail.records.map((record) => record.audit_id)).size).toBe(2);
  });

  it("counts decisions on the dashboard from the same store", async () => {
    const dashboard = await api.getDashboard();
    expect(dashboard.decisions.approved).toBe(SEEDED.approved + 1);
    expect(dashboard.decisions.rejected).toBe(SEEDED.rejected + 1);
    expect(dashboard.decisions.pending).toBe(
      dashboard.decisions.approved + dashboard.decisions.rejected + dashboard.decisions.pending
        - SEEDED.approved - SEEDED.rejected - 2,
    );
  });

  it("answers an unknown item with a 404", async () => {
    await expect(api.approveReviewItem("RI-NOPE")).rejects.toMatchObject({ status: 404 });
  });
});

describe("cases in fixture mode", () => {
  it("renames, refuses a blank name, deletes, and re-opens on upload", async () => {
    const before = await api.listCases();
    expect(before.total).toBe(1);
    const caseId = before.cases[0].case_id;

    const renamed = await api.updateCase(caseId, { client_name: "Renamed Client" });
    expect(renamed.client_name).toBe("Renamed Client");
    await expect(api.updateCase(caseId, { client_name: "  " })).rejects.toMatchObject({
      status: 422,
    });

    await api.deleteCase(caseId);
    expect((await api.listCases()).total).toBe(0);
    await expect(api.deleteCase(caseId)).rejects.toMatchObject({ status: 404 });

    const upload = await api.uploadDocuments({
      bankStatement: new File([new Uint8Array([1])], "statement.pdf"),
      ledger: new File([new Uint8Array([1])], "ledger.xlsx"),
      invoices: [new File([new Uint8Array([1])], "invoice.pdf")],
    });
    expect(upload.status).toBe("ready_for_review");
    expect(upload.documents).toHaveLength(3);
    expect(upload.job_id).toBeUndefined();
    expect((await api.listCases()).total).toBe(1);
  });
});

describe("auth in fixture mode", () => {
  it("signs the demo auditor in with any credentials, and refuses empty ones", async () => {
    const session = await api.login("someone@firm.pk", "secret");
    expect(session.user_id).toBe(api.DEMO_USER_ID);
    expect(session.expires_in).toBeGreaterThan(0);
    await expect(api.login("", "")).rejects.toMatchObject({ status: 401 });
  });

  it("enforces the password rule on signup", async () => {
    await expect(api.signup("a@b.pk", "short", "Firm")).rejects.toMatchObject({ status: 422 });
    const created = await api.signup("a@b.pk", "long-enough-password", "Firm");
    expect(created.role).toBe("owner");
  });

  it("changes a password with the same rules as the backend", async () => {
    await expect(api.changePassword("", "new-password-1")).rejects.toMatchObject({
      status: 400,
    });
    await expect(api.changePassword("old", "short")).rejects.toMatchObject({ status: 422 });
    await expect(api.changePassword("same-password", "same-password")).rejects.toMatchObject({
      status: 400,
    });
    const changed = await api.changePassword("old-password", "new-password-1");
    expect(changed.message).toContain("Password changed");
  });
});

describe("API keys in fixture mode", () => {
  it("creates, renames, revokes, and deletes a key, showing the secret once", async () => {
    await expect(api.createApiKey("", ["read"])).rejects.toMatchObject({ status: 422 });
    await expect(api.createApiKey("x", [])).rejects.toMatchObject({ status: 422 });

    const created = await api.createApiKey("nightly job", ["read", "write"]);
    expect(created.api_key.startsWith("trz_live_")).toBe(true);
    expect(created.key.key_prefix).toBe(created.api_key.slice(0, 17));

    const renamed = await api.renameApiKey(created.key.key_id, "nightly");
    expect(renamed.name).toBe("nightly");

    const revoked = await api.revokeApiKey(created.key.key_id);
    expect(revoked.revoked).toBe(true);
    expect(revoked.revoked_at).not.toBeNull();

    const deleted = await api.deleteApiKey(created.key.key_id);
    expect(deleted.deleted).toBe(true);
    await expect(api.deleteApiKey(created.key.key_id)).rejects.toMatchObject({ status: 404 });
  });
});

describe("live-only features say so in fixture mode", () => {
  it("names the backend as the missing piece, never a made-up result", async () => {
    await expect(api.generateReport()).rejects.toMatchObject({ status: 501 });
    await expect(api.getInsights()).rejects.toMatchObject({ status: 501 });
    await expect(api.createClient({ name: "X" } as never)).rejects.toMatchObject({
      status: 501,
    });
    await expect(api.getJob("JOB-x")).rejects.toMatchObject({ status: 404 });
  });
});
