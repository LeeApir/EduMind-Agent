/** Bounded GET-only review recovery. Never restarts generation or posts a decision. */
export interface HybridOperation {
  id: string;
  status: string;
  phase?: string | null;
  error?: Record<string, unknown> | null;
  learning_unit_id?: string | null;
  publication_version?: number | null;
  review_summary?: {
    state: "pending" | "approved" | "rejected" | "invalidated";
    approval_source: "auto" | "human_assisted" | null;
    reason_code: string;
    updated_at: string;
  } | null;
}
export async function readHybridOperation(id: string, signal?: AbortSignal): Promise<HybridOperation> {
  const response = await fetch(`/api/learning-operations/${encodeURIComponent(id)}`, {
    credentials: "same-origin", cache: "no-store", signal,
  });
  if (!response.ok) throw new Error("原请求状态暂时无法读取。");
  const value = await response.json() as HybridOperation;
  if (value.id !== id || typeof value.status !== "string") throw new Error("原请求状态无效。");
  return value;
}
function isHidden(): boolean { return document.visibilityState === "hidden"; }
export function watchHybridOperation(options: {
  id: string;
  onUpdate: (value: HybridOperation) => void | Promise<void>;
  onError: (error: unknown) => void;
  read?: (id: string, signal: AbortSignal) => Promise<HybridOperation>;
  intervalMs?: number;
  maxReads?: number;
}): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let reading = false;
  let reads = 0;
  const maxReads = Number.isInteger(options.maxReads) ? Math.max(1, Math.min(options.maxReads!, 60)) : 60;
  const stop = (): void => {
    controller.abort();
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", changed);
  };
  const poll = async (): Promise<void> => {
    if (controller.signal.aborted || reading || isHidden()) return;
    if (reads >= maxReads) { stop(); return; }
    reads += 1;
    reading = true;
    try {
      const value = await (options.read ?? readHybridOperation)(options.id, controller.signal);
      if (controller.signal.aborted || isHidden()) return;
      if (value.id !== options.id) throw new Error("原请求状态无效。");
      await options.onUpdate(value);
      if (["completed", "published", "failed", "canceled", "rejected"].includes(value.status)) {
        stop(); return;
      }
    } catch (error) {
      if (!controller.signal.aborted) options.onError(error);
      stop(); return;
    } finally { reading = false; }
    if (!controller.signal.aborted) timer = setTimeout(() => { void poll(); }, options.intervalMs ?? 5000);
  };
  function changed(): void {
    clearTimeout(timer);
    if (!isHidden()) void poll();
  }
  document.addEventListener("visibilitychange", changed);
  void poll();
  return stop;
}
