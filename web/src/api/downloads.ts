export type DownloadKind = "notes" | "mp4" | "srt";

export class DownloadError extends Error {
  constructor(readonly code: "missing" | "unavailable" | "failed") {
    super(code === "missing" ? "文件已不存在，请重新请求动画。"
      : code === "unavailable" ? "文件暂时不可用，请稍后重试下载。"
        : "下载失败，请检查网络后重试。");
  }
}

export function notesUrl(unitId: string): string {
  return `/api/learning-units/${encodeURIComponent(unitId)}/notes.md`;
}

function safeFilename(disposition: string | null, fallback: string): string {
  const match = disposition?.match(/(?:^|;)\s*filename="?([A-Za-z0-9_.-]+)"?(?:;|$)/i);
  const value = match?.[1];
  return value && !value.startsWith(".") && !value.includes("..") ? value : fallback;
}

export async function downloadFile(
  url: string, fallbackName: string, isCurrent: () => boolean = () => true,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  let response: Response;
  try {
    response = await fetchImpl(url, { credentials: "same-origin" });
  } catch { throw new DownloadError("failed"); }
  if (response.status === 503) throw new DownloadError("unavailable");
  if (response.status === 404) throw new DownloadError("missing");
  if (!response.ok) throw new DownloadError("failed");
  let file: Blob;
  try { file = await response.blob(); } catch { throw new DownloadError("failed"); }
  if (!isCurrent()) return;
  const objectUrl = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = safeFilename(response.headers.get("Content-Disposition"), fallbackName);
  document.body.append(link);
  try { link.click(); } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  }
}
