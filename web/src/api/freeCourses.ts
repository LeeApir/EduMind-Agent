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
export interface OperationStep { step_key: string; scene_id: string | null; state: 'pending' | 'blocked_dependency' | 'running' | 'ready' | 'failed' | 'invalidated' | 'cancelled'; reason_code: string | null }
export interface Operation { course_id: string; operation_id: string; kind: string; state: string; base_head_version: number | null; head_version: number | null; last_event_id: number; deadline_at: string; reason_code: string | null; clarification_questions: string[]; steps: OperationStep[]; budget: { max_attempts: number; max_seconds: number; [key: string]: unknown }; request_id: string }
export interface Impact { course_id: string; base_head_version: number | null; kind: 'adjust_outline' | 'revise_scene'; affected_scene_ids: string[]; requires_outline_adjustment: boolean; max_attempts: number; max_seconds: number; impact_digest: string }
export type OperationRequest = { kind: 'resume'; expected_head_version: number | null; source_operation_id: string } | { kind: 'clarify'; expected_head_version: number | null; source_operation_id: string; supplement: string } | { kind: 'adjust_outline'; expected_head_version: number | null; instruction: string; impact_digest: string };
export function coursePath(id: string): string { return `/${encodeURIComponent(id)}`; }
export const terminalOperation = (state: string): boolean => ['succeeded','partially_succeeded','awaiting_clarification','failed','cancelled','timed_out'].includes(state);
export async function readOperation(course: string, id: string, signal?: AbortSignal): Promise<Operation> {
  const value = await courseRequest<Operation>(`${coursePath(course)}/operations/${encodeURIComponent(id)}`, { signal });
  if (!value || value.course_id !== course || value.operation_id !== id || !['queued','running','cancel_requested','succeeded','partially_succeeded','awaiting_clarification','failed','cancelled','timed_out'].includes(value.state) || !Number.isInteger(value.last_event_id) || value.last_event_id < 0 || !Array.isArray(value.steps) || !value.steps.every(s => typeof s.step_key === 'string' && ['pending','blocked_dependency','running','ready','failed','invalidated','cancelled'].includes(s.state)) || !Array.isArray(value.clarification_questions) || !value.clarification_questions.every(q => typeof q === 'string')) throw new FreeCourseError(502,'INVALID_RESPONSE');
  return value;
}
export async function readImpact(course: string, version: number | null, signal?: AbortSignal): Promise<Impact> {
  const value = await courseRequest<Impact>(`${coursePath(course)}/impact?kind=adjust_outline${version === null ? '' : `&base_version=${version}`}`, { signal });
  if (!value || value.course_id !== course || value.base_head_version !== version || value.kind !== 'adjust_outline' || !Array.isArray(value.affected_scene_ids) || typeof value.impact_digest !== 'string') throw new FreeCourseError(502,'INVALID_RESPONSE');
  return value;
}
export async function submitOperation(course: string, body: OperationRequest, csrf: string, key: string): Promise<CreatedCourse> {
  const result = await courseRequest<CreatedCourse>(`${coursePath(course)}/operations`, command(csrf,key,body));
  if (!result || result.course_id !== course || typeof result.operation_id !== 'string') throw new FreeCourseError(502,'INVALID_RESPONSE');
  return result;
}
export async function cancelOperation(course: string, id: string, csrf: string, key: string): Promise<Operation> {
  return courseRequest<Operation>(`${coursePath(course)}/operations/${encodeURIComponent(id)}/cancel`, command(csrf,key,{}));
}
export type SceneBlock = {kind:'text';anchor_id:string;markdown:string} | {kind:'code';anchor_id:string;language:'c';source:string} | {kind:'exercise';anchor_id:string;exercise_id:string;exercise_version_id:string;question:string;items:{question_id:string;question:string;input_type:'short_text'}[]} | {kind:'exercise_unavailable';anchor_id:string;exercise_id:string;exercise_version_id:string;reason_code:string} | {kind:'visualization';anchor_id:string;text_alternative:string;visualization_type:string;steps:{caption:string;elements:unknown[];highlight_ids:string[]}[]};
export interface SceneProjection {course_id:string;course_version:number;scene_id:string;scene_version_id:string;blocks:SceneBlock[];actions:unknown[]}
export async function readScene(course: string, version: number, scene: string, signal?: AbortSignal): Promise<SceneProjection> {
  const value = await courseRequest<SceneProjection>(`${coursePath(course)}/versions/${version}/scenes/${encodeURIComponent(scene)}`,{signal});
  if (!value || value.course_id !== course || value.course_version !== version || value.scene_id !== scene || typeof value.scene_version_id !== 'string' || !Array.isArray(value.blocks) || !value.blocks.every(b => typeof b.anchor_id === 'string' && ['text','code','exercise','exercise_unavailable','visualization'].includes(b.kind))) throw new FreeCourseError(502,'INVALID_RESPONSE');
  return value;
}
