import { command, coursePath, courseRequest, FreeCourseError } from './freeCourses';
export interface TutorBinding {course_version:number;scene_id:string;scene_version_id:string}
export interface TutorRequest extends TutorBinding {message:string;acknowledge_assisted_practice:true}
export interface TutorReceipt {operation_id:string;turn_id:string}
export interface TutorTurn {turn_id:string;operation_id:string;binding:TutorBinding;message:string;status:'queued'|'running'|'ready'|'failed'|'cancelled'|'timed_out'|'invalidated';markdown:string|null;anchor_refs:string[];reason_code:string|null}
export async function createTutor(course:string,body:TutorRequest,csrf:string,key:string):Promise<TutorReceipt>{
  const result=await courseRequest<TutorReceipt>(`${coursePath(course)}/tutor-turns`,command(csrf,key,body));
  if(!result||typeof result.operation_id!=='string'||typeof result.turn_id!=='string')throw new FreeCourseError(502,'INVALID_RESPONSE');return result;
}
export async function readTutor(course:string,receipt:TutorReceipt,signal?:AbortSignal):Promise<TutorTurn>{
  const value=await courseRequest<TutorTurn>(`${coursePath(course)}/tutor-turns/${encodeURIComponent(receipt.turn_id)}`,{signal});
  if(!value||value.turn_id!==receipt.turn_id||value.operation_id!==receipt.operation_id||!value.binding||!Number.isInteger(value.binding.course_version)||typeof value.binding.scene_id!=='string'||typeof value.binding.scene_version_id!=='string'||typeof value.message!=='string'||!['queued','running','ready','failed','cancelled','timed_out','invalidated'].includes(value.status)||!Array.isArray(value.anchor_refs))throw new FreeCourseError(502,'INVALID_RESPONSE');
  if(value.status!=='ready'){value.markdown=null;value.anchor_refs=[];}
  else if(typeof value.markdown!=='string'||!value.markdown.trim()||value.markdown.length>6000||!value.anchor_refs.every(a=>typeof a==='string'&&a.length<=128))throw new FreeCourseError(502,'INVALID_RESPONSE');return value;
}
