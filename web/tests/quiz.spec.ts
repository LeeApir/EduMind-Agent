import { describe, expect, it, vi } from "vitest";
import { loadLatestQuizResult, parseQuizResult, submitQuizAttempt } from "../src/api/quiz";

const receipt = {
  evidence_id: "evidence-001", resource_id: "resource-001", resource_version: 1,
  question_results: [{ question_id: "q1", correct: false, explanation: "反馈", error_patterns: ["skipped"] }],
  score: 0, correct_count: 0, question_count: 1, quiz_schema_version: 1,
  scoring_rule_version: "quiz-exact-text-v1", mastery_changes: [],
  path_replan_required: false, profile_update_status: "no_change",
};
const options = {
  resourceId: "resource-001", resourceVersion: 1, answers: [{ question_id: "q1", answer: "" }],
  csrfToken: "csrf-token", idempotencyKey: "quiz-key-00000001",
};

describe("quiz API client", () => {
  it("sends exact version, CSRF and stable idempotency key without client score", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(Response.json(receipt));
    expect(await submitQuizAttempt({ ...options, fetchImpl })).toEqual(receipt);
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/quiz-submissions");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers["X-CSRF-Token"]).toBe("csrf-token");
    expect(init.headers["Idempotency-Key"]).toBe("quiz-key-00000001");
    expect(JSON.parse(init.body)).toEqual({ resource_id: "resource-001", resource_version: 1, answers: options.answers });
  });

  it("restores the owner server receipt and treats no submission as empty state", async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(Response.json(receipt)).mockResolvedValueOnce(new Response(null, { status: 404 }));
    expect(await loadLatestQuizResult({ ...options, fetchImpl })).toEqual(receipt);
    expect(fetchImpl.mock.calls[0][0]).toContain("resource_id=resource-001&resource_version=1");
    expect(await loadLatestQuizResult({ ...options, fetchImpl })).toBeNull();
  });

  it("finishes an absent receipt response before returning empty state", async () => {
    const missing = Response.json({ code: "NOT_FOUND" }, { status: 404 });
    expect(await loadLatestQuizResult({ ...options, fetchImpl: vi.fn().mockResolvedValue(missing) })).toBeNull();
    expect(missing.bodyUsed).toBe(true);
  });

  it("keeps conflict and connection errors explicit", async () => {
    const conflict = vi.fn().mockResolvedValue(Response.json({ code: "IDEMPOTENCY_CONFLICT", message: "请求键冲突" }, { status: 409 }));
    await expect(submitQuizAttempt({ ...options, fetchImpl: conflict })).rejects.toMatchObject({ code: "IDEMPOTENCY_CONFLICT" });
    await expect(submitQuizAttempt({ ...options, fetchImpl: vi.fn().mockRejectedValue(new Error("network")) })).rejects.toMatchObject({ code: "CONNECTION_FAILED" });
  });

  it("rejects malformed or wrong-version receipts rather than displaying invented mastery", async () => {
    expect(() => parseQuizResult({ ...receipt, score: 2 })).toThrow("响应无效");
    expect(() => parseQuizResult({ ...receipt, mastery_changes: [{ status: "mastered" }] })).toThrow("响应无效");
    const fetchImpl = vi.fn().mockResolvedValue(Response.json({ ...receipt, resource_version: 2 }));
    await expect(submitQuizAttempt({ ...options, fetchImpl })).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});
