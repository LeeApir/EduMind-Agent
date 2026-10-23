import { courseRequest,coursePath,FreeCourseError } from './freeCourses';
export type RecordKind='attempt'|'operation'|'feedback'|'tutor';
export interface RecordRef {record_id:string;created_at:string}
export interface RecordPage {course_id:string;kind:RecordKind;items:RecordRef[];next_before_id:string|null}
export async function listCourseRecords(course:string,kind:RecordKind,before='',signal?:AbortSignal):Promise<RecordPage>{const value=await courseRequest<RecordPage>(`${coursePath(course)}/records?kind=${kind}&limit=20${before?`&before_id=${encodeURIComponent(before)}`:''}`,{signal});if(!value||value.course_id!==course||value.kind!==kind||!Array.isArray(value.items)||!value.items.every(r=>typeof r.record_id==='string'&&typeof r.created_at==='string')||value.next_before_id!==null&&typeof value.next_before_id!=='string')throw new FreeCourseError(502,'INVALID_RESPONSE');return value;}
