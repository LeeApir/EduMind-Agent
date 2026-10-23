<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ensureCatalogSession, loadCatalog, type CatalogListing } from '../api/catalog';
import { createCourse, listCourses, readStored, writeStored, type CourseSummary, type CreatedCourse, type CreateCourse } from '../api/freeCourses';
import WorkspaceState from './WorkspaceState.vue';
const props = defineProps<{ mode: 'catalog_only' | 'dynamic' }>();
const emit = defineEmits<{ open: [course: string, operation: string]; catalog: [] }>();
const goal = ref(''); const language = ref<'c' | ''>('c'); const owner = ref('');
const loading = ref(true); const busy = ref(false); const error = ref(''); const listError = ref('');
const courses = ref<CourseSummary[]>([]); const cursor = ref<string | null>(null); const catalog = ref<CatalogListing>();
let epoch = 0; const controller = new AbortController();
type Pending = { signature: string; key: string; body: CreateCourse; receipt?: CreatedCourse };
watch([goal, language], () => { if (owner.value) writeStored(`edumind:free:goal:${owner.value}`, { goal: goal.value, language: language.value }); });
async function initialize(): Promise<void> {
  const token = ++epoch; loading.value = true; listError.value = '';
  try {
    const session = await ensureCatalogSession(); if (token !== epoch) return;
    if (owner.value !== session.owner) { courses.value = []; cursor.value = null; goal.value = ''; owner.value = session.owner; const saved = readStored<{goal: string; language: string}>(`edumind:free:goal:${owner.value}`); if (saved && typeof saved.goal === 'string') { goal.value = saved.goal; language.value = saved.language === '' ? '' : 'c'; } }
    const results = await Promise.allSettled([listCourses('', controller.signal), loadCatalog()]);
    if (token !== epoch) return;
    const [drafts, signed] = results;
    if (drafts.status === 'fulfilled') { courses.value = drafts.value.items; cursor.value = drafts.value.next_cursor; } else listError.value = '暂时无法读取草稿记录。重新读取不会生成。';
    if (signed.status === 'fulfilled') catalog.value = signed.value; else listError.value += ' 签核目录未能读取。';
  } catch { if (token === epoch) listError.value = '无法读取当前学习身份，请重试。'; }
  finally { if (token === epoch) loading.value = false; }
}
async function more(): Promise<void> {
  if (loading.value || !cursor.value) return; const token = epoch; loading.value = true;
  try { const result = await listCourses(cursor.value, controller.signal); if (token !== epoch) return; courses.value = [...courses.value, ...result.items.filter(c => !courses.value.some(old => old.course_id === c.course_id))]; cursor.value = result.next_cursor; }
  catch { if (token === epoch) listError.value = '更多记录未能读取，可重试。'; }
  finally { if (token === epoch) loading.value = false; }
}
async function start(): Promise<void> {
  if (busy.value || !goal.value.trim() || goal.value.trim().length > 4000) return;
  if (props.mode !== 'dynamic') { error.value = '当前只开放签核课程，目标已保留。'; return; }
  busy.value = true; error.value = ''; const token = epoch;
  try {
    const session = await ensureCatalogSession(); if (token !== epoch) return;
    if (session.owner !== owner.value) { error.value = '学习身份已变化，请重新读取后提交。'; courses.value = []; return; }
    const body: CreateCourse = { goal: goal.value.trim(), teaching_language: 'zh-CN', code_language: language.value === 'c' ? 'c' : null };
    const signature = JSON.stringify(body); const key = `edumind:free:create:${owner.value}`;
    let pending = readStored<Pending>(key);
    if (!pending || pending.signature !== signature || typeof pending.key !== 'string') pending = { signature, body, key: crypto.randomUUID() };
    writeStored(key, pending);
    const receipt = pending.receipt ?? await createCourse(pending.body, session.csrf, pending.key);
    if (token !== epoch) return;
    pending.receipt = receipt; writeStored(key, pending); writeStored(`edumind:free:operation:${owner.value}:${receipt.course_id}`, receipt.operation_id);
    emit('open', receipt.course_id, receipt.operation_id);
  } catch (failure) { if (token === epoch) error.value = failure instanceof Error ? failure.message : '请求未能确认，输入已保留。'; }
  finally { if (token === epoch) busy.value = false; }
}
function openCourse(course: CourseSummary): void { emit('open', course.course_id, readStored<string>(`edumind:free:operation:${owner.value}:${course.course_id}`) ?? ''); }
onMounted(initialize); onBeforeUnmount(() => { epoch += 1; controller.abort(); });
</script>
<template>
  <main class="learning-home page-view">
    <p class="page-eyebrow">
      从一个真实问题开始
    </p><h1>今天，你想弄懂什么？</h1><p class="page-lead">
      说说你的目标。无需先选知识点，也不用填写一张画像问卷。
    </p>
    <form
      class="goal-card surface"
      @submit.prevent="start"
    >
      <label for="learning-goal">这次学习的目标</label>
      <textarea
        id="learning-goal"
        v-model="goal"
        rows="3"
        maxlength="4000"
        placeholder="例如：我懂 C 的基础语法，想看明白链表头插法的指针变化"
        :readonly="busy"
      />
      <details>
        <summary>学习偏好（可选）</summary><label for="code-language">代码语言</label><select
          id="code-language"
          v-model="language"
          :disabled="busy"
        >
          <option value="c">
            C 语言
          </option><option value="">
            不指定代码语言
          </option>
        </select><p>只使用你提供的信息，未提供的学情保持未知。</p>
      </details>
      <div class="goal-footer">
        <small>{{ mode === 'catalog_only' ? '当前仅开放签核课程，目标仍可保留。' : 'AI 草稿可能有误；第一节就绪即可开始。' }}</small><button
          class="primary"
          type="submit"
          :disabled="busy || loading || !goal.trim()"
        >
          {{ busy ? '正在确认请求…' : '组织我的课程 →' }}
        </button>
      </div>
      <p
        v-if="error"
        role="alert"
      >
        {{ error }}
      </p>
    </form>
    <section aria-labelledby="continue-title">
      <div class="section-heading">
        <h2 id="continue-title">
          继续你的学习
        </h2><button
          class="secondary"
          type="button"
          :disabled="loading"
          @click="initialize"
        >
          重新读取
        </button>
      </div>
      <WorkspaceState
        v-if="loading && !courses.length"
        kind="loading"
        detail="正在读取自己的课程记录。"
      />
      <WorkspaceState
        v-if="listError"
        kind="error"
        :detail="listError"
      />
      <WorkspaceState
        v-else-if="!loading && !courses.length"
        kind="empty"
        detail="还没有自由课程。你的第一门课程会从这里继续。"
      />
      <div class="course-cards">
        <article
          v-for="course in courses"
          :key="course.course_id"
          class="surface"
        >
          <span class="badge warning">AI 生成草稿 · 未签核</span><h3>{{ course.original_goal }}</h3><p>生成版本：{{ course.head_version === null ? '尚无可学场景' : `v${course.head_version}` }}</p><p>学习进度：尚未提供课程内进度，打开后恢复本机阅读位置。</p><button
            class="secondary"
            type="button"
            @click="openCourse(course)"
          >
            继续学习 →
          </button>
        </article>
      </div>
      <button
        v-if="cursor"
        class="secondary"
        type="button"
        :disabled="loading"
        @click="more"
      >
        读取更多课程
      </button>
    </section>
    <section aria-labelledby="catalog-title">
      <div class="section-heading">
        <h2 id="catalog-title">
          已有签核课程
        </h2><button
          class="secondary"
          type="button"
          @click="$emit('catalog')"
        >
          打开签核目录
        </button>
      </div>
      <WorkspaceState
        v-if="catalog?.status === 'not_ready' || catalog?.releases.length === 0"
        kind="empty"
        detail="还没有可用的签核课程。"
      />
      <div class="course-cards">
        <article
          v-for="release in catalog?.releases"
          :key="release.id"
          class="surface"
        >
          <span class="badge">签核课程 · {{ release.version }}</span><h3>{{ release.package_id }}</h3><p>{{ release.nodes.map(n => n.name).join('、') }}</p><p>{{ release.nodes.length }} 个可学习知识点</p><button
            class="secondary"
            type="button"
            @click="$emit('catalog')"
          >
            查看此目录
          </button>
        </article>
      </div>
    </section>
  </main>
</template>
