async (page) => {
 const base='http://127.0.0.1:5198/api/free-courses/eabc1bbb-1d5a-4b0c-9e8d-78ca3157b9ce',route=base+'/versions/2/scenes/bdd02733-7376-4929-a29a-d7199752220c';
 const scene=await(await page.request.get(route)).json();
 const ex=page.getByRole('region',{name:'随堂练习',exact:true});
 await ex.locator('textarea').first().waitFor();
 if(await ex.locator('textarea').count()!==4)throw new Error('Need four questions');
 const posts=[], errors=[];
 const onRequest=r=>{if(r.method()==='POST'&&r.url()===base+'/attempts')posts.push({method:r.method(),url:r.url(),body:r.postDataJSON()});};
 const onError=e=>errors.push(e.message);
 page.on('request',onRequest);page.on('pageerror',onError);
 const cases=[{name:'wrong',answers:['i1','[0]','[0]','0'],score:0},{name:'correct',answers:['i0','[11, 30, 40]','[\n30,40\n]','1'],score:1}];
 const results=[];
 for(const c of cases){
  if(c.name==='correct')await ex.getByRole('button',{name:'继续完善或新作答',exact:true}).click();
  for(let i=0;i<4;i++)await ex.locator('textarea').nth(i).fill(c.answers[i]);
  const pending=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/attempts');
  await ex.getByRole('button',{name:'提交本次作答',exact:true}).click();
  const response=await pending, submitted=await response.json();
  if(response.status()!==201)throw new Error('Attempt POST failed');
  await ex.getByText('与暂定参考的匹配比例：'+(c.score*100)+'%',{exact:true}).waitFor();
  const id=await ex.locator('select').inputValue();
  const read=await page.request.get(base+'/attempts/'+id),attempt=await read.json();
  if(read.status()!==200||attempt.comparison_score!==c.score||attempt.mastery_effect!=='course_only'||attempt.reliability!=='provisional'||attempt.question_results.length!==4||attempt.question_results.some(q=>q.matches_reference!==(c.score===1)))throw new Error('Feedback mismatch '+c.name);
  if(attempt.binding.course_version!==2||attempt.binding.scene_version_id!==scene.scene_version_id)throw new Error('Feedback binding mismatch');
  const feedback=await ex.getByRole('region',{name:'本次作答反馈',exact:true}).innerText();
  for(const q of attempt.question_results)if(!feedback.includes(q.explanation))throw new Error('Explanation absent');
  results.push({name:c.name,answers:c.answers,post_status:response.status(),submitted,get_status:read.status(),attempt,rendered_feedback:feedback});
 }
 const before=posts.length;
 await page.reload();await page.waitForLoadState('networkidle');
 const reloaded=page.getByRole('region',{name:'随堂练习',exact:true});
 await reloaded.getByText('与暂定参考的匹配比例：100%',{exact:true}).waitFor();
 const sceneAfter=await(await page.request.get(route)).json();
 const idAfter=await reloaded.locator('select').inputValue();
 const attemptAfter=await(await page.request.get(base+'/attempts/'+idAfter)).json();
 if(JSON.stringify(sceneAfter)!==JSON.stringify(scene))throw new Error('Full scene drift after reload');
 if(JSON.stringify(attemptAfter)!==JSON.stringify(results[1].attempt))throw new Error('Full feedback drift after reload');
 if(posts.length!==2||before!==2)throw new Error('Refresh resubmitted attempt');
 const restored=await reloaded.locator('textarea').evaluateAll(xs=>xs.map(x=>x.value));
 if(JSON.stringify(restored)!==JSON.stringify(cases[1].answers))throw new Error('Inputs not restored');
 if(errors.length)throw new Error('Browser errors '+errors.join(','));
 page.off('request',onRequest);page.off('pageerror',onError);
 return {course_id:scene.course_id,course_version:2,scene_version_id:scene.scene_version_id,candidate_digest:scene.generation_source.candidate_digest,results,posts,refresh:{full_scene_identical:true,full_attempt_identical:true,answers_restored:restored,posts_before:before,posts_after:posts.length,additional_posts:0,selected_attempt:idAfter},browser_errors:errors,provider_calls:0};
}
