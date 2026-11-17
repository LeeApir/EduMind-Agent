'use strict';
// Local presentation fixture only. No requests, credentials, storage, or model calls.
const $ = (id) => document.getElementById(id);
const lessons = [
  ['指针，是找到结点的线索', '用 head 和 next 建立一个直观的认识', '讲解', '2 分钟'],
  ['一次头插，两个指针动作', '先连接原链表，再更新头指针', '演示', '3 分钟'],
  ['再插入一个结点会怎样？', '沿着指针走一遍，观察顺序的变化', '演示', '2 分钟'],
  ['把动作写成 C 代码', '对照语句，解释每一步改变了什么', '代码', '3 分钟'],
  ['用一组题检查理解', '判断头插后的遍历结果', '练习', '2 分钟'],
  ['回顾与下一步', '整理过程，再选择需要补充的内容', '回顾', '3 分钟'],
];
let scene = 1;
let step = 0;
let generationTimer;
let transitionTimer;
let notificationTimer;
let lastReady = false;

function notice(message) {
  clearTimeout(notificationTimer);
  $('notice').textContent = message;
  $('notice').hidden = false;
  notificationTimer = setTimeout(() => { $('notice').hidden = true; }, 3800);
}
function stopTimers() { clearTimeout(generationTimer); clearTimeout(transitionTimer); }
function showView(name, direct = false) {
  if (!['home', 'plan', 'course', 'graph', 'profile', 'records', 'settings'].includes(name)) name = 'home';
  stopTimers();
  clearTimeout(notificationTimer);
  $('notice').hidden = true;
  document.querySelectorAll('.view').forEach((view) => { view.hidden = view.id !== `${name}-view`; });
  document.querySelectorAll('.preview-bar [data-view]').forEach((button) => {
    if (button.dataset.view === name) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('breadcrumb').textContent = { home: '学习空间 / 学习', plan: '学习 / 生成课程', course: '学习 / 把链表头插看明白', graph: '学习空间 / 图谱与路径', profile: '学习空间 / 画像与掌握度', records: '学习空间 / 学习记录', settings: '设置 / 模型设置' }[name];
  document.querySelectorAll('.sidebar [data-view]').forEach((button) => {
    const selected = button.dataset.view === (['plan', 'course'].includes(name) ? 'home' : name);
    button.classList.toggle('selected', selected);
    if (selected) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('page-state').hidden = true;
  $('page-fixture').value = 'normal';
  $('global-nav').classList.remove('open');
  $('menu-button').setAttribute('aria-expanded', 'false');
  $('tutor').classList.remove('open');
  if (name === 'plan') {
    $('goal-quote').textContent = $('goal').value;
    $('plan-duration').textContent = `约 ${$('duration').value}`;
    $('enter-course').disabled = false;
    $('plan-status').textContent = '课程结构已准备好，第一节可开始预览。';
    $('stop-generation').hidden = true;
  }
  if (name === 'course' && direct) selectScene(1);
  history.replaceState(null, '', `#${name}`);
  window.scrollTo({ top: 0, behavior: 'instant' });
  const heading = document.querySelector(`#${name}-view h1`);
  heading?.setAttribute('tabindex', '-1');
  if (direct) heading?.focus({ preventScroll: true });
  window.dispatchEvent(new CustomEvent('prototype:view', { detail: name }));
}
document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view, true)));
document.querySelector('.brand').addEventListener('click', (event) => { event.preventDefault(); showView('home'); });
$('menu-button').addEventListener('click', () => { const open = $('global-nav').classList.toggle('open'); $('menu-button').setAttribute('aria-expanded', String(open)); });
$('preferences-button').addEventListener('click', () => { $('preferences').hidden = !$('preferences').hidden; $('preferences-button').setAttribute('aria-expanded', String(!$('preferences').hidden)); });
$('goal-form').addEventListener('submit', (event) => {
  event.preventDefault();
  if (!$('goal').value.trim()) { $('goal').setCustomValidity('请先描述一个学习目标。'); $('goal').reportValidity(); return; }
  showView('plan');
  $('plan-status').textContent = '模拟中：正在准备第一节，稍后自动进入课程。';
  $('enter-course').disabled = true;
  $('stop-generation').hidden = false;
  generationTimer = setTimeout(() => {
    $('plan-status').textContent = '模拟中：第一节已就绪，5 秒后进入课程。';
    $('enter-course').disabled = false;
    transitionTimer = setTimeout(() => { selectScene(0); showView('course'); }, 5000);
  }, 2200);
});
$('goal').addEventListener('input', () => $('goal').setCustomValidity(''));
$('continue-course').addEventListener('click', () => { selectScene(1); showView('course'); });
$('enter-course').addEventListener('click', () => { selectScene(0); showView('course'); });
$('stop-generation').addEventListener('click', () => {
  stopTimers();
  $('plan-status').textContent = '模拟生成已停止。大纲保留，可以查看已准备的示例课程。';
  $('enter-course').disabled = false;
  $('stop-generation').hidden = true;
});
$('edit-plan').addEventListener('click', () => {
  stopTimers();
  $('outline-edit').hidden = false;
  $('plan-status').textContent = '示例：旧生成已停止，正在调整大纲；确认后才开始新操作预览。';
  $('stop-generation').hidden = true;
  $('plan-note').focus();
});
$('save-plan').addEventListener('click', () => {
  if (!$('plan-confirm').checked) { notice('请先确认重新规划的影响。'); $('plan-confirm').focus(); return; }
  $('outline-edit').hidden = true;
  $('plan-status').textContent = '调整文字已保留在本页；示例大纲不变，点击开始学习预览。';
  $('enter-course').disabled = false;
  notice('预览已保留调整文字，未重新生成课程。');
});

$('outline-list').innerHTML = lessons.map((lesson, index) => `<li><span class="outline-number">0${index + 1}</span><div><h3>${lesson[0]}</h3><p>${lesson[1]} · ${lesson[3]}</p></div><span class="scene-type">${lesson[2]}</span></li>`).join('');
$('lesson-list').innerHTML = lessons.map((lesson, index) => `<button data-scene="${index}"><span>${index === 0 ? '✓' : `0${index + 1}`}</span><span>${lesson[0]}<small>${index === 5 ? '等待生成' : index === 2 ? '生成未完成' : `${lesson[2]} · ${lesson[3]}`}</small></span></button>`).join('');
document.querySelectorAll('[data-scene]').forEach((button) => button.addEventListener('click', () => selectScene(Number(button.dataset.scene))));
function showPanel(panel) {
  ['explain', 'code', 'quiz', 'waiting'].forEach((name) => { $(`${name}-panel`).hidden = name !== panel; });
  document.querySelectorAll('[data-panel]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.panel === panel)));
  updateCode();
}
document.querySelectorAll('[data-panel]').forEach((button) => button.addEventListener('click', () => showPanel(button.dataset.panel)));
function selectScene(index) {
  scene = index;
  setStep(0);
  document.querySelectorAll('[data-scene]').forEach((button) => {
    if (Number(button.dataset.scene) === index) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
  });
  $('lesson-number').textContent = `0${index + 1} / 06`;
  $('lesson-title').textContent = lessons[index][0];
  $('lesson-description').textContent = lessons[index][1] + '。';
  $('lesson-kind').textContent = `${lessons[index][2]} · 约 ${lessons[index][3]}`;
  // One complete lesson fixture demonstrates layout. Other scenes are explicitly previews.
  const notBuilt = index === 2 || (index === 5 && !lastReady);
  document.querySelector('.content-switch').hidden = notBuilt;
  if (notBuilt) {
    $('waiting-title').textContent = index === 2 ? '这一节暂未完成' : '这一节还在生成';
    $('waiting-text').textContent = index === 2 ? '演示局部失败状态：当前章节没有就绪，其他已完成章节仍可学习。' : '示例状态：可以先学习前面的讲解和代码。';
    $('retry-scene').textContent = index === 2 ? '重试状态演示' : '模拟本节就绪';
    showPanel('waiting');
  } else if (index === 3) showPanel('code');
  else if (index === 4) showPanel('quiz');
  else showPanel('explain');
  if (index === 0) $('lesson-description').textContent = 'head 是链表的入口，next 记录下一个结点。下面用一次头插观察它们的关系。';
  if (index === 5 && lastReady) $('lesson-description').textContent = '回看这两个动作：先连接原链表，再更新 head。下面复用状态演示整理过程。';
  $('next-lesson').textContent = index === 5 ? '返回学习首页 →' : '继续下一节 →';
  $('course-directory').classList.remove('open');
  $('toggle-directory').setAttribute('aria-expanded', 'false');
}
$('next-lesson').addEventListener('click', () => { if (scene === 5) showView('home'); else selectScene(scene + 1); });
$('retry-scene').addEventListener('click', () => {
  if (scene === 2) { $('waiting-title').textContent = '重试仍未完成'; $('waiting-text').textContent = '本原型未生成第二个演示。保留失败状态，可切换到代码或已完成章节。'; notice('局部失败不会隐藏其他已经完成的章节。'); }
  else { lastReady = true; selectScene(5); document.querySelector('[data-scene="5"] small').textContent = '回顾 · 3 分钟'; document.querySelector('.directory-foot').innerHTML = '<span class="tiny-dot"></span>示例：已生成 5 / 6 节<small>第 3 节仍未完成</small>'; }
});
const stepLabels = [
  '准备：head 指向 3，新结点 n 的 data 为 8。',
  '① n->next = head：让 8 的 next 指向原来的头结点 3。',
  '② head = n：head 改为指向 8。现在是 8 → 3 → NULL。',
];
function updateCode() {
  document.querySelectorAll('.code-line').forEach((line) => line.classList.toggle('highlight', Number(line.dataset.line) === step + 1));
}
function setStep(next) {
  step = Math.max(0, Math.min(2, next));
  $('diagram').dataset.step = String(step);
  $('trace-caption').textContent = stepLabels[step];
  $('diagram').setAttribute('aria-label', stepLabels[step]);
  $('prev-step').disabled = step === 0;
  $('next-step').textContent = step === 2 ? '重新演示 ↺' : '下一步 →';
  document.querySelectorAll('[data-step]').forEach((button) => button.setAttribute('aria-pressed', Number(button.dataset.step) === step ? 'true' : 'false'));
  updateCode();
}
document.querySelectorAll('[data-step]').forEach((button) => button.addEventListener('click', () => setStep(Number(button.dataset.step))));
$('prev-step').addEventListener('click', () => setStep(step - 1));
$('next-step').addEventListener('click', () => setStep(step === 2 ? 0 : step + 1));
$('code-step').addEventListener('click', () => { setStep(step === 2 ? 0 : step + 1); notice(stepLabels[step]); });
$('back-to-demo').addEventListener('click', () => showPanel('explain'));
$('quiz-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const one = $('answer-one').value.trim();
  const two = $('answer-two').value.trim();
  $('quiz-feedback').hidden = false;
  if ($('course-fixture').value === 'withdrawn') {
    $('quiz-feedback').textContent = '题组已停用，不能提交或查看原答案反馈。';
  } else if (!one && !two) {
    $('quiz-feedback').textContent = '请至少填写一个非空作答。';
  } else if (!one || !two) {
    $('quiz-feedback').textContent = '示例：部分作答已留在本页。题组尚未完整，不显示答案或逐题对错。';
  } else {
    $('quiz-feedback').textContent = '暂定比较 · 仅作学习参考：先执行 n->next = head，再执行 head = n，遍历为 8 → 3 → NULL。本例无独立核定，不计正式掌握度；你的文字没有被自动判为已掌握。';
  }
});
$('toggle-directory').addEventListener('click', () => { const open = $('course-directory').classList.toggle('open'); $('toggle-directory').setAttribute('aria-expanded', String(open)); });
$('open-tutor').addEventListener('click', () => { $('tutor').classList.add('open'); $('question').focus(); });
$('close-tutor').addEventListener('click', () => { $('tutor').classList.remove('open'); $('open-tutor').focus(); });
function reply() {
  if (!$('tutor-assistance').checked) { notice('请先了解提问对练习记录的影响。'); $('tutor-assistance').focus(); return; }
  if ($('course-fixture').value === 'generating') { notice('生成尚未结束。可以等待或主动停止生成后提问。'); return; }
  if ($('course-fixture').value === 'tutor-invalid') { notice('该回复来源已失效，正文停止展示。'); return; }
  $('tutor-reply').hidden = false;
  $('tutor-reply').textContent = '预设示例：如果先执行 head = n，再执行 n->next = head，n->next 就会指回 n 自己，形成自环。先连接旧 head，才能保留原链表。';
}
$('suggested-question').addEventListener('click', reply);
$('question-form').addEventListener('submit', (event) => { event.preventDefault(); if (!$('tutor-assistance').checked) { notice('请先确认练习辅助记录。'); $('tutor-assistance').focus(); return; } if (['generating', 'tutor-invalid'].includes($('course-fixture').value)) { notice('当前状态不能开始新的导师回复，请查看状态说明。'); return; } $('tutor-reply').hidden = false; $('tutor-reply').textContent = '你的问题已在本页输入。这个原型没有接入AI；可点击上面的示例问题预览回答样式。'; });
$('report-issue').addEventListener('click', () => $('feedback-dialog').showModal());
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { $('global-nav').classList.remove('open'); $('menu-button').setAttribute('aria-expanded', 'false'); $('tutor').classList.remove('open'); } });
selectScene(1);
setStep(0);
showView(location.hash.slice(1) || 'home');
// Direct fragment links and browser navigation must resolve the displayed page.
window.addEventListener('hashchange', () => {
  const name = location.hash.slice(1) || 'home';
  if (['home', 'plan', 'course', 'graph', 'profile', 'records', 'settings'].includes(name)) showView(name, true);
});
document.querySelector('.skip-link').addEventListener('click', (event) => {
  event.preventDefault(); $('main-content').focus(); $('main-content').scrollIntoView({ block: 'start' });
});
