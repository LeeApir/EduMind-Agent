import { describe, expect, it, vi } from "vitest";
import {
  controlPresetDemo, enrollCatalog, ensureCatalogSession, loadCatalogUnit, loadProductMode,
} from "../src/api/catalog";

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
describe("fixed catalog transport", () => {
  it("creates identity only for 401, not other errors", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({}, 401))
      .mockResolvedValueOnce(json({ user: { id: "owner" }, csrf_token: "csrf" }));
    expect(await ensureCatalogSession(fetch)).toEqual({ owner: "owner", csrf: "csrf" });
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(["/api/auth/session", "/api/auth/guest"]);
    const failure = vi.fn().mockResolvedValue(json({}, 500));
    await expect(ensureCatalogSession(failure)).rejects.toThrow();
    expect(failure).toHaveBeenCalledTimes(1);
  });
  it("fails closed on an unknown runtime or a generated resource unit", async () => {
    await expect(loadProductMode(vi.fn().mockResolvedValue(json({ mode: "unknown" })))).rejects.toThrow();
    await expect(loadCatalogUnit("unit", vi.fn().mockResolvedValue(json({ id: "unit", status: "ready",
      origin_type: "generated", catalog_release_id: null, knowledge_node_id: "array", scenes: [] })))).rejects.toThrow();
  });
  it("binds fixed requests to node/release, csrf and unchanged idempotency key", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ learning_unit_id: "unit", release_id: "release", node_id: "array" }));
    expect(await enrollCatalog("release", "array", "csrf", "fixed-key", fetch)).toBe("unit");
    const [path, options] = fetch.mock.calls[0];
    expect(path).toBe("/api/catalog/sessions");
    expect(JSON.parse(options.body)).toEqual({ release_id: "release", node_id: "array" });
    expect(options.headers).toMatchObject({ "X-CSRF-Token": "csrf", "Idempotency-Key": "fixed-key" });
    fetch.mockResolvedValue(json({ learning_unit_id: "other", release_id: "different", node_id: "array" }));
    await expect(enrollCatalog("release", "array", "csrf", "fixed-key", fetch)).rejects.toThrow();
  });
  it("sends a preset command with CAS and never calls the dynamic debate path", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ preset: true, return_resource_type: "code", classroom: {
      revision: 3, scene_key: "intro", scene_version: 1, scene_progress: 0, paused: false,
    } }));
    await controlPresetDemo("unit", "exit", "code", 2, "csrf", "key", fetch);
    expect(fetch.mock.calls[0][0]).toBe("/api/catalog/learning-units/unit/demo");
    expect(fetch.mock.calls[0][1].headers["If-Match-Classroom-Revision"]).toBe("2");
  });
});
