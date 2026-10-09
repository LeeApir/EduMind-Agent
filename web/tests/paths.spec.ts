import { describe, expect, it, vi } from "vitest";
import { loadCurrentPath, loadGraph, loadMastery, parseLearningPath, replanPath } from "../src/api/paths";

import { pathFixture } from "./pathFixture";
export { pathFixture } from "./pathFixture";

describe("path API client", () => {
  it("reads owner path and handles missing path without creating one", async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(Response.json(pathFixture)).mockResolvedValueOnce(new Response(null, { status: 404 }));
    expect(await loadCurrentPath("linked-list-concept", fetchImpl)).toEqual(pathFixture);
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/path/current?target_node_id=linked-list-concept");
    expect(fetchImpl.mock.calls[0][1].credentials).toBe("same-origin");
    expect(await loadCurrentPath("linked-list-concept", fetchImpl)).toBeNull();
  });
  it("finishes an absent path response before returning empty state", async () => {
    const missing = Response.json({ code: "NOT_FOUND" }, { status: 404 });
    expect(await loadCurrentPath("array", vi.fn().mockResolvedValue(missing))).toBeNull();
    expect(missing.bodyUsed).toBe(true);
  });

  it("sends immutable replan command parameters and preserves version conflicts", async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(Response.json(pathFixture)).mockResolvedValueOnce(Response.json({ code: "PATH_VERSION_CONFLICT" }, { status: 409 }));
    const options = { targetNodeId: "linked-list-concept", expectedVersion: 1, csrfToken: "csrf", idempotencyKey: "path-key-00000001", reason: "mastery_changed" as const };
    await replanPath(options, fetchImpl);
    expect(fetchImpl.mock.calls[0][1].headers).toMatchObject({ "X-CSRF-Token": "csrf", "Idempotency-Key": options.idempotencyKey, "If-Match-Path-Version": "1" });
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ target_node_id: options.targetNodeId, reason: "mastery_changed" });
    await expect(replanPath(options, fetchImpl)).rejects.toMatchObject({ code: "PATH_VERSION_CONFLICT" });
  });
  it("validates graph and current mastery, not browser-derived mastery", async () => {
    expect(await loadGraph(vi.fn().mockResolvedValue(Response.json({ graph_version: "g1", nodes: [{ id: "array", name: "数组", prerequisites: [] }] })))).toMatchObject({ nodes: [{ id: "array" }] });
    expect(await loadMastery(vi.fn().mockResolvedValue(Response.json({ graph_version: "g1", items: [] })))).toEqual({ graph_version: "g1", items: [] });
    await expect(loadMastery(vi.fn().mockResolvedValue(Response.json({ graph_version: "g1", items: [{ status: "mastered" }] })))).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
  it("rejects inconsistent IDs, invalid statuses, wrong target and connection failures", async () => {
    expect(() => parseLearningPath({ ...pathFixture, nodes: ["array"] })).toThrow("响应无效");
    expect(() => parseLearningPath({ ...pathFixture, node_details: [{ ...pathFixture.node_details[0], status: "ready" }, pathFixture.node_details[1]] })).toThrow("响应无效");
    await expect(loadCurrentPath("array", vi.fn().mockResolvedValue(Response.json(pathFixture)))).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
    await expect(loadCurrentPath("array", vi.fn().mockRejectedValue(new Error("network")))).rejects.toMatchObject({ code: "CONNECTION_FAILED" });
  });
});
