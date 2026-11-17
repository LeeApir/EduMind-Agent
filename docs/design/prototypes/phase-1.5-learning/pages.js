'use strict';
// All state is local fixture state. No fetch, storage, credentials or real scoring.
let activeView = location.hash.slice(1) || 'home';
let returnView = 'home';
let detailOpener;
const viewNames = { home: '学习首页', plan: '生成大纲', course: '课程学习', graph: '图谱与路径', profile: '画像与掌握度', records: '学习记录', settings: '模型设置' };
window.addEventListener('prototype:view', (event) => {
  if (event.detail === 'settings' && activeView !== 'settings') returnView = activeView;
  activeView = event.detail;
});
const stateContent = {
  loading: ['正在读取已有记录', '读取与生成是两件事。原型不会发送请求，你可以返回正常示例继续核对。'],
  empty: ['还没有可展示的记录', '未知如实保留。可以从一个学习目标开始，不会补上示例成绩。'],
  error: ['这次没有读到记录', '已有内容没有被删除。正式页面重试只重新读取，不会重新生成课程或重复付费。'],
  forbidden: ['这份内容无法访问', '可能不存在或不属于当前学习者，不展示课程内容或其他用户资料。'],
  invalid: ['这个版本暂不可用', '不会自动换到另一个版本。原始作答仍可从自己的学习记录查看，失效答案不再展示。'],
};
$('page-fixture').addEventListener('change', () => {
  const mode = $('page-fixture').value;
  document.querySelectorAll('.view').forEach((view) => { view.hidden = view.id !== `${activeView}-view` || mode !== 'normal'; });
  $('page-state').hidden = mode === 'normal';
  if (mode !== 'normal') {
    stopTimers();
    $('state-context').textContent = `${viewNames[activeView]} · 状态设计`;
    [$('state-title').textContent, $('state-description').textContent] = stateContent[mode];
  }
});
$('state-action').addEventListener('click', () => showView(activeView, true));
$('return-from-settings').addEventListener('click', () => showView(returnView, true));
function openDetail(title, body, opener) {
  detailOpener = opener || document.activeElement;
  $('detail-title').textContent = title;
  $('detail-body').replaceChildren();
  body.forEach((line) => {
    const paragraph = document.createElement('p');
    paragraph.textContent = line;
    $('detail-body').append(paragraph);
  });
  $('detail-dialog').showModal();
}
function closeDetail() { $('detail-dialog').close(); detailOpener?.focus(); }
$('close-detail').addEventListener('click', closeDetail);
$('detail-confirm').addEventListener('click', closeDetail);
$('detail-dialog').addEventListener('cancel', () => setTimeout(() => detailOpener?.focus(), 0));

const nodeFixtures = {
  array: ['数组', '从连续存储与下标理解访问和遍历。', '签核课程样式 · 示例', '学习中，示例签核题组记录', '查看示例依据 →'],
  pointer: ['C 指针', '用地址和 next 建立连接的直觉，是链表学习的前置。', '可以按目标规划', '未知，没有可靠测量', '带入这个学习目标 →'],
  insert: ['链表头插', '用两次指针赋值，把新结点接到链表头部。', 'AI 草稿 · 4 / 6 节就绪', '未知，尚无有效题组证据', '继续示例课程 →'],
  delete: ['链表删除', '理解前驱如何绕过目标结点，以及何时释放空间。', '尚无签核课程；可按目标规划', '未知，没有作答记录', '带入这个学习目标 →'],
  stack: ['栈与队列', '从进入和离开的顺序，比较两类线性结构。', '可按目标规划', '未知，没有作答记录', '带入这个学习目标 →'],
};
let selectedNode = 'insert';
document.querySelectorAll('[data-node]').forEach((button) => button.addEventListener('click', () => {
  selectedNode = button.dataset.node;
  const node = nodeFixtures[selectedNode];
  ['node-title', 'node-description', 'node-availability', 'node-mastery', 'node-action'].forEach((id, index) => { $(id).textContent = node[index]; });
  document.querySelectorAll('.map-node').forEach((element) => {
    const selected = element.dataset.node === selectedNode;
    element.classList.toggle('active', selected);
    element.setAttribute('aria-pressed', String(selected));
  });
}));
function graphMode(list) {
  $('knowledge-map').hidden = list;
  $('knowledge-list').hidden = !list;
  $('graph-map-button').setAttribute('aria-pressed', String(!list));
  $('graph-list-button').setAttribute('aria-pressed', String(list));
}
$('graph-map-button').addEventListener('click', () => graphMode(false));
$('graph-list-button').addEventListener('click', () => graphMode(true));
$('node-action').addEventListener('click', () => {
  if (selectedNode === 'insert') showView('course', true);
  else if (selectedNode === 'array') showView('profile', true);
  else { $('goal').value = `我想学习${nodeFixtures[selectedNode][0]}，请从基础开始解释。`; showView('home', true); $('goal').focus(); }
});
$('choose-prerequisite').addEventListener('click', () => { $('goal').value = '我想先理解 C 指针和 next，再继续学习链表头插。'; showView('home', true); $('goal').focus(); });
$('edit-profile').addEventListener('click', () => $('profile-edit-dialog').showModal());
$('close-profile-edit').addEventListener('click', () => { $('profile-edit-dialog').close(); $('edit-profile').focus(); });
$('save-profile-edit').addEventListener('click', () => {
  const value = $('profile-self-edit').value.trim();
  if (!value) { $('profile-self-edit').focus(); notice('请写下希望保留的自述。'); return; }
  $('profile-background').textContent = value + ' · 来自自述';
  $('profile-edit-dialog').close(); $('edit-profile').focus();
  notice('自述仅在本页更新，不改变题目成绩或正式掌握度。');
});
$('explain-mastery').addEventListener('click', () => openDetail('为什么没有掌握度分数？', ['这份草稿题组只有暂定答案比较，尚无可靠答案和单节点核定。', '即使完整作答，也只保留课程内表现，不计正式掌握度。未知不代表你不会。']));
$('record-filter').addEventListener('change', () => {
  const filter = $('record-filter').value;
  document.querySelectorAll('[data-record]').forEach((row) => { row.hidden = filter !== 'all' && row.dataset.record !== filter; });
});
$('restore-course').addEventListener('click', () => { showView('course', true); notice('示例：恢复阅读版本 1，不重新生成或调用模型。'); });
$('resume-generation').addEventListener('click', () => openDetail('继续生成缺失内容', ['这会开始一次新的生成操作，只补缺失或失败及其必要依赖。', '已就绪内容保留；仍受课程累计额度约束。此处只预览确认，不发送请求。']));
$('open-attempt').addEventListener('click', () => openDetail('暂定反馈 · 题组版本 1', ['你的原始文字：先连接旧 head，再更新 head。', '参考答案尚未独立核定；不计正式掌握度。新题的答案不会用于重新评价这次作答。']));
$('open-withdrawn-attempt').addEventListener('click', () => openDetail('原始作答 · 反馈已撤销', ['你的原始作答仍然保留：先连接原链表，再改变入口。', '对应参考答案已失效，原对错判断及答案停止展示。相关掌握度贡献已撤销，路径待更新。']));
$('preview-connection-test').addEventListener('click', () => {
  $('connection-state').textContent = '仍未验证 · 原型没有联网';
  notice('只演示检查后的说明，没有发送请求，不能标为连接成功。');
});
$('preview-credential-remove').addEventListener('click', () => openDetail('移除凭据 · 操作确认样式', ['正式操作会停用对应连接的后续调用，并处理受影响操作。', '此处没有读取或删除真实凭据，点击完成只关闭预览。']));
$('model-form').addEventListener('submit', (event) => {
  event.preventDefault();
  $('model-saved').hidden = false;
  $('model-saved').textContent = '偏好仅在本页预览。正式保存用于下一次新操作；运行中的配置不变，也不触发连接检查。';
});

$('course-fixture').addEventListener('change', () => {
  const mode = $('course-fixture').value;
  const notes = {
    generating: '示例：后续内容还在生成。提问暂不可用；可以等待或主动停止生成，再开始导师操作。',
    withdrawn: '示例：这份题组已确认有误并停用。讲解和代码仍可读；原始作答保留，错误反馈不再展示。',
    'tutor-invalid': '示例：原导师回复引用的来源已失效，回复正文停止展示。你的原问题仍保留。',
  };
  $('course-state-note').hidden = mode === 'ready';
  $('course-state-note').textContent = notes[mode] || '';
  $('quiz-form').querySelectorAll('input, button').forEach((element) => { element.disabled = mode === 'withdrawn'; });
  $('quiz-feedback').hidden = mode !== 'withdrawn';
  if (mode === 'withdrawn') { showPanel('quiz'); $('quiz-feedback').textContent = '题组已停用。原答案和对错判断停止展示，不产生新评分。'; }
  $('tutor-reply').hidden = true;
  $('question-form').querySelector('button').disabled = mode === 'generating' || mode === 'tutor-invalid';
  $('suggested-question').disabled = mode === 'generating' || mode === 'tutor-invalid';
  document.querySelector('.directory-foot').textContent = `示例：已生成 ${lastReady ? 5 : 4} / 6 节 · ${mode === 'generating' ? '后续生成中' : '生成已停止'}`;
});
$('plan-fixture').addEventListener('change', () => {
  stopTimers();
  const mode = $('plan-fixture').value;
  const notes = {
    clarify: '示例：你的要求同时包含“只讲指针”和“不讲指针”。请先补充真正想学的范围；没有新场景生成。',
    unknown: '示例：上次调用结果无法确认，已暂停后续调用。不会自动重试；已有可读内容保留，待确认后才能继续。',
    stopped: '示例：生成已停止。恢复阅读不重新生成；继续生成需明确开始新操作。',
  };
  $('plan-fixture-note').hidden = mode === 'ready';
  $('plan-fixture-note').textContent = notes[mode] || '';
  $('enter-course').disabled = mode === 'clarify';
});
$('revise-scene').addEventListener('click', () => { $('revision-dialog').showModal(); });
$('close-revision').addEventListener('click', () => $('revision-dialog').close());
$('start-revision').addEventListener('click', () => {
  if (!$('revision-note').value.trim()) { $('revision-note').focus(); notice('请先写下希望调整的内容。'); return; }
  if (!$('revision-confirm').checked) { $('revision-confirm').focus(); notice('请确认影响范围和新操作。'); return; }
  $('revision-status').textContent = '调整中（固定示例）：仍在阅读旧版，等待受影响的内容全部就绪。';
  $('complete-revision').hidden = false;
});
$('complete-revision').addEventListener('click', () => {
  $('answer-one').value = ''; $('answer-two').value = ''; $('quiz-feedback').hidden = true;
  document.querySelector('#quiz-panel .small-label').textContent = '短文本题组 · 版本 2 · 新题需重新作答';
  $('course-version-note').textContent = '示例修订版本 2 已就绪 · 受影响内容一起切换 · 原作答仍绑定旧题';
  $('revision-dialog').close();
  $('revise-scene').focus();
  notice('示例：全部修订就绪后才切换，没有混合新旧题目。');
});

// Compact overlays keep keyboard focus inside and return focus on Escape.
$('menu-button').addEventListener('click', () => { if ($('global-nav').classList.contains('open')) $('global-nav').querySelector('a,button:not(:disabled)').focus(); });
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if ($('global-nav').contains(document.activeElement)) $('menu-button').focus();
    else if ($('tutor').contains(document.activeElement)) $('open-tutor').focus();
  }
  if (event.key !== 'Tab') return;
  const panel = document.querySelector('dialog[open]') || ($('global-nav').classList.contains('open') ? $('global-nav') : $('tutor').classList.contains('open') ? $('tutor') : null);
  if (!panel) return;
  const items = [...panel.querySelectorAll('a,button:not(:disabled),input,textarea')].filter((element) => element.getClientRects().length);
  if (!items.length) return;
  const first = items[0]; const last = items.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

$('close-menu').addEventListener('click', () => { $('global-nav').classList.remove('open'); $('menu-button').setAttribute('aria-expanded', 'false'); $('menu-button').focus(); });

$('report-issue').addEventListener('click', () => {
  $('feedback-location').textContent = $('lesson-title').textContent + ' · ' + $('course-version-note').textContent;
});
$('feedback-dialog').addEventListener('close', () => {
  if ($('feedback-dialog').returnValue === 'confirm') notice('示例反馈处于待核实状态，不会直接撤回整课；本页没有发送或保存。');
});
