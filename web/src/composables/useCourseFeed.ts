import { onBeforeUnmount, ref, watch, type Ref } from 'vue';
import { ensureCatalogSession } from '../api/catalog';
import { coursePath, readCourse, readOperation, FreeCourseError, terminalOperation, writeStored, type Course, type Operation } from '../api/freeCourses';
/** GET-only snapshots and durable SSE. Every activation owns a separate abort/epoch. */
export function useCourseFeed(courseId: Ref<string>, operationId: Ref<string>, active: Ref<boolean>) {
  const course = ref<Course>(); const operation = ref<Operation>(); const owner = ref(''); const error = ref(''); const loading = ref(false);
  let epoch = 0; let controller: AbortController | undefined; let source: EventSource | undefined; let timer: ReturnType<typeof setTimeout> | undefined;
  let pending = false; let reading = false; let cursor = 0; let failures = 0;
  function stop(): void { epoch += 1; controller?.abort(); source?.close(); source = undefined; clearTimeout(timer); reading = false; pending = false; }
  async function refresh(token = epoch): Promise<void> {
    if (!active.value || token !== epoch) return;
    if (reading) { pending = true; return; } reading = true;
    try {
      const session = await ensureCatalogSession(); if (token !== epoch) return;
      if (owner.value && session.owner !== owner.value) { course.value = undefined; operation.value = undefined; stop(); error.value = '学习身份已变化，请重新打开课程。'; return; }
      owner.value = session.owner;
      const op = operationId.value ? await readOperation(courseId.value,operationId.value,controller?.signal) : undefined;
      const snapshot = await readCourse(courseId.value,controller?.signal); if (token !== epoch) return;
      operation.value = op; course.value = snapshot; error.value = '';
      // Snapshot covers all durable events up to this cursor; GET never replays commands.
      cursor = Math.max(cursor, op?.last_event_id ?? 0);
      if (op && terminalOperation(op.state)) { source?.close(); source = undefined; }
    } catch (failure) { if (token === epoch) { error.value = failure instanceof Error ? failure.message : '课程读取失败。'; if (failure instanceof FreeCourseError && [401,403,404].includes(failure.status)) { course.value = undefined; operation.value = undefined; source?.close(); } } }
    finally { if (token === epoch) { loading.value = false; reading = false; if (pending) { pending = false; void refresh(token); } } }
  }
  function connect(token: number): void {
    source?.close(); source = undefined;
    if (token !== epoch || !active.value || !operation.value || terminalOperation(operation.value.state) || failures >= 3) return;
    const key = `edumind:free:cursor:${owner.value}:${operationId.value}`;
    // The current snapshot is authoritative if browser cursor storage is stale/ahead.
    writeStored(key, cursor);
    const stream = new EventSource(`/api/free-courses${coursePath(courseId.value)}/operations/${encodeURIComponent(operationId.value)}/events?after=${cursor}`);
    source = stream;
    const receive = (event: Event): void => {
      if (token !== epoch || !active.value || typeof (event as MessageEvent).data !== 'string') return;
      try {
        const data = JSON.parse((event as MessageEvent<string>).data) as { schema_version: string; operation_id: string; seq: number; type: string };
        if (data.schema_version !== 'free-course-events-v1' || data.operation_id !== operationId.value || !Number.isInteger(data.seq) || data.seq <= cursor) return;
        cursor = data.seq; writeStored(key,cursor); void refresh(token);
        if (data.type === 'done') { stream.close(); if (source === stream) source = undefined; }
      } catch { stream.close(); error.value = '进度事件无效，请重新读取。'; }
    };
    for (const type of ['queued','started','clarification_required','outline_ready','scene_started','scene_ready','first_scene_ready','progress','cancel_requested','error','done']) stream.addEventListener(type,receive);
    stream.onerror = () => {
      if (token !== epoch) return; stream.close(); if (source === stream) source = undefined; failures += 1;
      timer = setTimeout(() => { void refresh(token).then(() => connect(token)); }, 1500 * failures);
    };
  }
  async function start(): Promise<void> {
    stop(); if (!active.value || !courseId.value) return;
    const token = epoch; controller = new AbortController(); course.value = undefined; operation.value = undefined; owner.value = ''; cursor = 0; failures = 0; loading.value = true; error.value = '';
    await refresh(token); if (token === epoch && !error.value) connect(token);
  }
  async function reload(): Promise<void> { failures = 0; await refresh(); if (!error.value) connect(epoch); }
  watch([courseId,operationId,active],start,{ immediate:true }); onBeforeUnmount(stop);
  return { course, operation, owner, error, loading, reload };
}
