import type { FetchLike } from './catalog';
export interface CourseSummary { course_id: string; original_goal: string; course_kind: 'ai_draft'; endorsement: 'unendorsed'; head_version: number | null; created_at: string }
export interface SceneBinding { scene_id: string; title: string; scene_version_id: string | null }
export interface Manifest { course_id: string; version: number; plan_id: string; created_at: string; complete: boolean; scenes: SceneBinding[]; node_links: { scene_id: string | null; node_id: string; graph_version: string; relation: string; source: string }[] }
export interface Course { course_id: string; original_goal: string; teaching_language: 'zh-CN'; code_language: 'c' | null; course_kind: 'ai_draft'; endorsement: 'unendorsed'; head: Manifest | null }
export interface CreatedCourse { course_id: string; operation_id: string }
export interface CreateCourse { goal: string; teaching_language: 'zh-CN'; code_language: 'c' | null }
export class FreeCourseError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(status === 401 || status === 403 || status === 404 ? '无法访问此内容，请重新读取。' : code === 'FREE_COURSE_DISABLED' ? '当前只开放签核课程，目标已保留。' : status === 409 ? '课程状态已变化，请重新读取后确认。' : '请求未能确认，请保留输入并重试同一请求。');
  }
}
export async function courseRequest<T>(path: string, init: RequestInit = {}, fetchImpl: FetchLike = fetch): Promise<T> {
  const response = await fetchImpl(`/api/free-courses${path}`, { credentials: 'same-origin', cache: 'no-store', ...init });
  if (!response.ok) {
    let code = ''; try { const data = await response.json(); code = typeof data.code === 'string' ? data.code : ''; } catch { /* Never show arbitrary server output. */ }
    throw new FreeCourseError(response.status, code);
  }
  return await response.json() as T;
}
export function command(csrf: string, key: string, body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Idempotency-Key': key }, body: JSON.stringify(body) };
}
export function validManifest(value: Manifest): boolean {
  return Boolean(value && typeof value.course_id === 'string' && Number.isInteger(value.version) && value.version > 0 && typeof value.complete === 'boolean' && Array.isArray(value.scenes) && value.scenes.every(s => typeof s.scene_id === 'string' && typeof s.title === 'string' && (s.scene_version_id === null || typeof s.scene_version_id === 'string')) && Array.isArray(value.node_links));
}
export async function listCourses(cursor = '', signal?: AbortSignal): Promise<{ items: CourseSummary[]; next_cursor: string | null }> {
  const data = await courseRequest<{ items: CourseSummary[]; next_cursor: string | null }>(`?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, { signal });
  if (!data || !Array.isArray(data.items) || !data.items.every(c => typeof c.course_id === 'string' && typeof c.original_goal === 'string' && c.course_kind === 'ai_draft' && c.endorsement === 'unendorsed' && (c.head_version === null || Number.isInteger(c.head_version) && c.head_version > 0)) || !(data.next_cursor === null || typeof data.next_cursor === 'string')) throw new FreeCourseError(502, 'INVALID_RESPONSE');
  return data;
}
export async function createCourse(body: CreateCourse, csrf: string, key: string): Promise<CreatedCourse> {
  const result = await courseRequest<CreatedCourse>('', command(csrf, key, body));
  if (!result || typeof result.course_id !== 'string' || typeof result.operation_id !== 'string') throw new FreeCourseError(502, 'INVALID_RESPONSE');
  return result;
}
export async function readCourse(id: string, signal?: AbortSignal): Promise<Course> {
  const value = await courseRequest<Course>(`/${encodeURIComponent(id)}`, { signal });
  if (!value || value.course_id !== id || typeof value.original_goal !== 'string' || value.course_kind !== 'ai_draft' || value.endorsement !== 'unendorsed' || value.head !== null && (!validManifest(value.head) || value.head.course_id !== id)) throw new FreeCourseError(502, 'INVALID_RESPONSE');
  return value;
}
export function readStored<T>(key: string): T | null { try { const value = sessionStorage.getItem(key); return value ? JSON.parse(value) as T : null; } catch { return null; } }
export function writeStored(key: string, value: unknown): void { try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* Reading remains available without browser storage. */ } }
