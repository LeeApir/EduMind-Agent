export type ResourceType = "explanation" | "code" | "exercise";
export interface CatalogNode { id: string; name: string; description: string; prerequisites: string[]; }
export interface CatalogRelease { id: string; package_id: string; version: string; digest: string; nodes: CatalogNode[]; }
export interface CatalogListing { status: "ready" | "not_ready"; releases: CatalogRelease[]; }
export interface CatalogResource { id: string; type: ResourceType; version: number; content: Record<string, unknown>; }
export interface CatalogScene { id: string; scene_key: string; version: number; is_current: boolean; resources: CatalogResource[]; }
export interface CatalogUnit { id: string; status: "ready"; knowledge_node_id: string; catalog_release_id: string; origin_type: "curated"; scenes: CatalogScene[]; }
export interface CatalogClassroom {
  revision: number; scene_key: string; scene_version: number; scene_progress: number; paused: boolean;
  detour?: { kind: string; return_point?: { resource_type: ResourceType } };
}
export interface PresetDemo { preset: true; release_id: string; demo_digest: string; script: { title: string; perspectives: { title: string; text: string }[]; summary: string }; classroom: CatalogClassroom | null; }
export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export class CatalogRequestError extends Error {
  constructor(message: string, readonly status = 0) { super(message); }
}

function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
async function request(path: string, init: RequestInit = {}, fetchImpl: FetchLike = fetch): Promise<unknown> {
  const response = await fetchImpl(path, { credentials: "same-origin", cache: "no-store", ...init });
  if (!response.ok) throw new CatalogRequestError(response.status === 404 || response.status === 409
    ? "课程或学习状态已变化，请重新读取。" : "课程暂时无法读取，请重试。", response.status);
  try { return await response.json(); } catch { throw new CatalogRequestError("课程响应无效，请重新读取。"); }
}
function invalid(): never { throw new CatalogRequestError("课程响应无效，请重新读取。"); }
function commandHeaders(csrf: string, key: string): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": key };
}
export async function loadProductMode(fetchImpl: FetchLike = fetch): Promise<"catalog_only" | "dynamic"> {
  const data = await request("/api/runtime", {}, fetchImpl);
  if (!object(data) || !["catalog_only", "dynamic"].includes(String(data.mode))) invalid();
  return data.mode as "catalog_only" | "dynamic";
}
export async function ensureCatalogSession(fetchImpl: FetchLike = fetch): Promise<{ owner: string; csrf: string }> {
  let data: unknown;
  try { data = await request("/api/auth/session", {}, fetchImpl); }
  catch (error) {
    if (!(error instanceof CatalogRequestError) || error.status !== 401) throw error;
    data = await request("/api/auth/guest", { method: "POST" }, fetchImpl);
  }
  if (!object(data) || !object(data.user) || typeof data.user.id !== "string"
    || typeof data.csrf_token !== "string" || !data.csrf_token) invalid();
  return { owner: data.user.id, csrf: data.csrf_token };
}
export async function loadCatalog(fetchImpl: FetchLike = fetch): Promise<CatalogListing> {
  const data = await request("/api/catalog", {}, fetchImpl);
  if (!object(data) || !["ready", "not_ready"].includes(String(data.status)) || !Array.isArray(data.releases)
    || !data.releases.every((release) => object(release) && typeof release.id === "string"
      && typeof release.version === "string" && typeof release.digest === "string" && Array.isArray(release.nodes)
      && release.nodes.every((node: unknown) => object(node) && typeof node.id === "string"
        && typeof node.name === "string" && typeof node.description === "string"
        && Array.isArray(node.prerequisites) && node.prerequisites.every((id: unknown) => typeof id === "string")))) invalid();
  return data as unknown as CatalogListing;
}
export async function enrollCatalog(releaseId: string, nodeId: string, csrf: string, key: string,
  fetchImpl: FetchLike = fetch): Promise<string> {
  const data = await request("/api/catalog/sessions", { method: "POST", headers: commandHeaders(csrf, key),
    body: JSON.stringify({ release_id: releaseId, node_id: nodeId }) }, fetchImpl);
  if (!object(data) || typeof data.learning_unit_id !== "string"
    || data.release_id !== releaseId || data.node_id !== nodeId) invalid();
  return data.learning_unit_id;
}
export async function loadCatalogUnit(unitId: string, fetchImpl: FetchLike = fetch): Promise<CatalogUnit> {
  const data = await request(`/api/learning-units/${encodeURIComponent(unitId)}`, {}, fetchImpl);
  if (!object(data) || data.id !== unitId || data.status !== "ready" || data.origin_type !== "curated"
    || typeof data.catalog_release_id !== "string" || typeof data.knowledge_node_id !== "string"
    || !Array.isArray(data.scenes) || !data.scenes.every((scene) => object(scene)
      && typeof scene.id === "string" && typeof scene.scene_key === "string" && Number.isInteger(scene.version)
      && Number(scene.version) >= 1 && typeof scene.is_current === "boolean" && Array.isArray(scene.resources)
      && scene.resources.every((resource: unknown) => object(resource) && typeof resource.id === "string"
        && ["explanation", "code", "exercise"].includes(String(resource.type)) && Number.isInteger(resource.version)
        && Number(resource.version) >= 1 && object(resource.content)))) invalid();
  return data as unknown as CatalogUnit;
}
function classroom(value: unknown): value is CatalogClassroom {
  return object(value) && Number.isInteger(value.revision) && Number(value.revision) >= 1
    && typeof value.paused === "boolean" && typeof value.scene_key === "string"
    && Number.isInteger(value.scene_version) && Number(value.scene_version) >= 1
    && Number.isInteger(value.scene_progress) && Number(value.scene_progress) >= 0;
}
export async function loadPresetDemo(unitId: string, fetchImpl: FetchLike = fetch): Promise<PresetDemo> {
  const data = await request(`/api/catalog/learning-units/${encodeURIComponent(unitId)}/demo`, {}, fetchImpl);
  if (!object(data) || data.preset !== true || typeof data.release_id !== "string" || typeof data.demo_digest !== "string"
    || !object(data.script) || typeof data.script.title !== "string" || typeof data.script.summary !== "string"
    || !Array.isArray(data.script.perspectives) || data.script.perspectives.length !== 3
    || !data.script.perspectives.every((p: unknown) => object(p) && typeof p.title === "string" && typeof p.text === "string")
    || (data.classroom !== null && !classroom(data.classroom))) invalid();
  return data as unknown as PresetDemo;
}
export async function createCatalogClassroom(unitId: string, csrf: string, key: string,
  fetchImpl: FetchLike = fetch): Promise<CatalogClassroom> {
  const data = await request(`/api/learning-units/${encodeURIComponent(unitId)}/classroom`,
    { method: "POST", headers: commandHeaders(csrf, key) }, fetchImpl);
  if (!classroom(data)) invalid();
  return data;
}
export async function controlPresetDemo(unitId: string, action: "begin" | "exit", resource: ResourceType,
  revision: number, csrf: string, key: string, fetchImpl: FetchLike = fetch):
  Promise<{ classroom: CatalogClassroom; return_resource_type: ResourceType }> {
  const data = await request(`/api/catalog/learning-units/${encodeURIComponent(unitId)}/demo`, {
    method: "POST", headers: { ...commandHeaders(csrf, key), "If-Match-Classroom-Revision": String(revision) },
    body: JSON.stringify({ action, return_resource_type: resource }),
  }, fetchImpl);
  if (!object(data) || data.preset !== true || !classroom(data.classroom)
    || !["explanation", "code", "exercise"].includes(String(data.return_resource_type))) invalid();
  return data as unknown as { classroom: CatalogClassroom; return_resource_type: ResourceType };
}
