import { command, coursePath, courseRequest, FreeCourseError } from './freeCourses';
export interface Answer {question_id:string;answer:string}
export interface AttemptRequest {course_version:number;scene_id:string;scene_version_id:string;exercise_id:string;exercise_version_id:string;answers:Answer[]}
export interface Attempt {attempt_id:string;binding:{course_version:number;scene_id:string;scene_version_id:string};exercise_id:string;exercise_version_id:string;answers:Answer[];completeness:'incomplete'|'complete';reliability:'provisional'|'verified'|'unavailable'|'withdrawn';comparison_score:number|null;question_results:{question_id:string;matches_reference:boolean;explanation:string}[];mastery_effect:'course_only'|'admitted'|'revoked';reason_code:string|null}
export async function submitAttempt(course:string,body:AttemptRequest,csrf:string,key:string):Promise<string>{
  const value=await courseRequest<{attempt_id:string}>(`${coursePath(course)}/attempts`,command(csrf,key,body));
  if(!value||typeof value.attempt_id!=='string')throw new FreeCourseError(502,'INVALID_RESPONSE');return value.attempt_id;
}
export async function readAttempt(course:string,id:string,signal?:AbortSignal):Promise<Attempt>{
  const value=await courseRequest<Attempt>(`${coursePath(course)}/attempts/${encodeURIComponent(id)}`,{signal});
  if(!value||value.attempt_id!==id||!value.binding||!Number.isInteger(value.binding.course_version)||typeof value.binding.scene_id!=='string'||typeof value.binding.scene_version_id!=='string'||typeof value.exercise_id!=='string'||typeof value.exercise_version_id!=='string'||!Array.isArray(value.answers)||!value.answers.every(a=>typeof a.question_id==='string'&&typeof a.answer==='string')||!['incomplete','complete'].includes(value.completeness)||!['provisional','verified','unavailable','withdrawn'].includes(value.reliability)||!['course_only','admitted','revoked'].includes(value.mastery_effect)||!Array.isArray(value.question_results))throw new FreeCourseError(502,'INVALID_RESPONSE');
  // Closed projection: partial/withdrawn comparisons can never reveal cached explanations.
  if(value.completeness==='incomplete'||['unavailable','withdrawn'].includes(value.reliability)){value.comparison_score=null;value.question_results=[];}
  else if(typeof value.comparison_score!=='number'||value.comparison_score<0||value.comparison_score>1||!value.question_results.every(q=>typeof q.question_id==='string'&&typeof q.matches_reference==='boolean'&&typeof q.explanation==='string'))throw new FreeCourseError(502,'INVALID_RESPONSE');
  if(value.mastery_effect==='admitted'&&(value.completeness!=='complete'||value.reliability!=='verified'))throw new FreeCourseError(502,'INVALID_RESPONSE');return value;
}
