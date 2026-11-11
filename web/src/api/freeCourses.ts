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
export interface Operation { course_id: string; operation_id: string; kind: string; state: string; base_head_version: number | null; head_version: number | null; last_event_id: number; deadline_at: string; reason_code: string | null; clarification_questions: string[]; steps: OperationStep[]; budget: { max_attempts: number; max_seconds: number; [key: string]: unknown } | null; execution_mode?:"finite_head_foreground"|"finite_stack_foreground"|"finite_queue_foreground"|"finite_binary_search_foreground"; request_id: string }
export interface Impact { course_id: string; base_head_version: number | null; kind: 'adjust_outline' | 'revise_scene'; affected_scene_ids: string[]; requires_outline_adjustment: boolean; max_attempts: number; max_seconds: number; impact_digest: string }
export type OperationRequest = { kind: 'resume'; expected_head_version: number | null; source_operation_id: string } | { kind: 'clarify'; expected_head_version: number | null; source_operation_id: string; supplement: string } | { kind: 'adjust_outline'; expected_head_version: number | null; instruction: string; impact_digest: string } | { kind:'revise_scene';expected_head_version:number;scene_id:string;instruction:string;impact_digest:string };
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
export interface HeadReplayFrame {frame_id:string;state_index:number;fact_id:string;kind:string;title:string;note:string;code_anchor:string;line:number|null;locals_scope:'active'|'inactive';state:{phase:string;attempt:number|null;caller_head:string|null;local_head:string|null;p:string|null;returned:string|null;code_line:number|null;nodes:Record<string,{data:number|'indeterminate';next:string|null}>}}
export interface StackCourseFrame {frame_id:string;code_anchor:string;line:number;popped:number|null;note:string}
export interface QueueCourseFrame extends Omit<StackCourseFrame, 'popped'> {dequeued:number|null}
export interface BinarySearchFrame extends Omit<StackCourseFrame, 'popped'> {
  phase: 'initial' | 'compare' | 'narrowed' | 'found'
  left: number
  right: number
  mid: number | null
  target: number
  comparison: 'less' | 'equal' | 'greater' | null
  iteration?: number | null
  comparison_frame_id?: string | null
  recomputed_mid?: boolean
  updated_endpoint?: 'left' | 'right' | null
  returned?: number | null
}
export interface VisualStep {caption:string;elements?:unknown[];highlight_ids?:string[];head_frame?:HeadReplayFrame;stack_frame?:StackCourseFrame;queue_frame?:QueueCourseFrame;binary_search_frame?:BinarySearchFrame}
export interface ReplaySource {mapping_version:string;origin:'existing_real_candidate_replay';batch:string;slot:string;candidate_digest:string;candidate_file_sha256:string;parent_digest:string|null;model:string;prompt_version:string}
export interface TrialReplaySource extends Omit<ReplaySource, "slot" | "candidate_file_sha256"> {
  mapping_version: "sealed-course-trial-replay-v1"
  topic: "head" | "stack"
  plan_source: "model_planned" | "fixed_outline"
  historical_stage: "authorized_citation_revision" | "first_draft"
  new_provider_calls: 0
  plan_digest: string
  materials_digest: string
}
export interface BinaryFramesSource extends Omit<TrialReplaySource, "mapping_version" | "topic" | "plan_source" | "historical_stage" | "parent_digest"> {
  mapping_version: "binary-search-program-frames-v1"
  topic: "binary-search"
  plan_source: "fixed_outline"
  historical_stage: "first_draft_teaching_failed"
  parent_digest: string
  source_request_sha256: string
  source_response_sha256: string
  original_materials_digest: string
  review_sha256: string
}
export type SceneBlock = {kind:'text';anchor_id:string;markdown:string} | {kind:'code';anchor_id:string;language:'c';source:string} | {kind:'exercise';anchor_id:string;exercise_id:string;exercise_version_id:string;question:string;items:{question_id:string;question:string;input_type:'short_text'|'json_integer_array'|'integer'}[]} | {kind:'exercise_unavailable';anchor_id:string;exercise_id:string;exercise_version_id:string;reason_code:string} | {kind:'visualization';anchor_id:string;text_alternative:string;visualization_type:string;steps:VisualStep[]};
export interface GenerationSource {unknown_echoes?:string[];origin:"head_goal_model_generation";batch:string;candidate_digest:string;parent_digest:string|null;model:string;prompt_version:string;stem_prompt_version?:"course-question-stem-v2";revision_version?:"shared-trial-limited-revision-v1";plan_source?:"model_planned"|"fixed_outline";plan_digest:string;materials_digest:string;evidence_kind:"actual_provider_response"|"offline_fixture"|"program_format_recovery"|"targeted_fact_revision"|"reviewed_paragraph_revision"|"evidence_bound_local_revision";teaching_evidence_version?:string;teaching_evidence_digest?:string;teaching_review?:{verdict:"pending"|"pass"|"needs_revision";independent_evaluator:string};format_recovery?:{rule_version:string;source_batch:string;original_raw_sha256:string;original_text_sha256:string;derived_output_sha256:string;original_request_sha256:string;duplicates:Array<{path:string[];removed_member_index:number;occurrence:number;value_sha256:string}>;new_provider_calls:0;model_first_structure_pass:false;assistant_text_edits:0}}
export interface FixedCourseSource extends Omit<GenerationSource, "origin" | "evidence_kind"> {
  origin: "stack_lifo_model_generation" | "queue_fifo_model_generation" | "binary_search_model_generation"
  evidence_kind: "actual_provider_response" | "evidence_bound_local_revision" | "offline_fixture"
  learner_case?: "array-first" | "operations-known"
}
export interface StackBoundariesSource extends Omit<FixedCourseSource, "origin"> {
  origin: "stack_boundaries_model_generation"
  scene_key: "normal" | "rejections"
  review_sha256: string
  source_request_sha256: string
  source_response_sha256: string
}
export interface ArchivedResponseSource extends Omit<GenerationSource, "origin" | "model" | "evidence_kind"> {
  origin: "reviewed_archived_response_import"
  evidence_kind: "reviewed_archived_response_import"
  requested_model: "gpt-6.1-sol"
  reported_model: null | "gpt-6.1-sol"
  reported_store: null | false
  strict_wire_verdict: "AIAPI_ENVELOPE" | "HEAD_AIAPI_ENVELOPE"
  new_provider_calls: 0
}
export interface SceneProjection {course_id:string;course_version:number;scene_id:string;scene_version_id:string;blocks:SceneBlock[];actions:unknown[];replay_source?:ReplaySource | TrialReplaySource | BinaryFramesSource;generation_source?:GenerationSource | ArchivedResponseSource | FixedCourseSource | StackBoundariesSource}
export async function readScene(course: string, version: number, scene: string, signal?: AbortSignal): Promise<SceneProjection> {
  const value = await courseRequest<SceneProjection>(`${coursePath(course)}/versions/${version}/scenes/${encodeURIComponent(scene)}`,{signal});
  if (!value || value.course_id !== course || value.course_version !== version || value.scene_id !== scene || typeof value.scene_version_id !== 'string' || !Array.isArray(value.actions) || !Array.isArray(value.blocks) || !value.blocks.every(b => typeof b.anchor_id === 'string' && ['text','code','exercise','exercise_unavailable','visualization'].includes(b.kind))) throw new FreeCourseError(502,'INVALID_RESPONSE');
  return value;
}
export async function readManifest(course: string, version: number, signal?: AbortSignal): Promise<Manifest> {
  const value = await courseRequest<Manifest>(`${coursePath(course)}/versions/${version}`,{signal});
  if (!validManifest(value) || value.course_id !== course || value.version !== version) throw new FreeCourseError(502,'INVALID_RESPONSE');
  return value;
}
export async function listVersions(course: string, cursor = '', signal?: AbortSignal): Promise<{items:{version:number;created_at:string}[];next_cursor:string|null}> {
  const value = await courseRequest<{items:{version:number;created_at:string}[];next_cursor:string|null}>(`${coursePath(course)}/versions?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,{signal});
  if (!value || !Array.isArray(value.items) || !value.items.every(v=>Number.isInteger(v.version)&&v.version>0) || !(value.next_cursor===null || typeof value.next_cursor==='string')) throw new FreeCourseError(502,'INVALID_RESPONSE');
  return value;
}
