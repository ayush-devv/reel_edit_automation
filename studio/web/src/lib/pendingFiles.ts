// Files dropped on the Projects home travel to the New edit screen through this tiny hand-off (FR-2).
let pending: File[] = [];

export function setPendingFiles(files: File[]) {
  pending = files;
}

export function takePendingFiles(): File[] {
  const f = pending;
  pending = [];
  return f;
}

export const VIDEO_EXT = ["mp4", "mov", "m4v", "mkv", "webm"] as const;
export const MAX_BYTES = 4 * 1024 ** 3;

/** Split dropped files into accepted videos and rejections with a message naming each file (AC-3). */
export function screenFiles(files: File[]): { ok: File[]; rejected: { name: string; reason: string }[] } {
  const ok: File[] = [];
  const rejected: { name: string; reason: string }[] = [];
  for (const f of files) {
    const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
    if (!(VIDEO_EXT as readonly string[]).includes(ext)) rejected.push({ name: f.name, reason: `${f.name} isn't a video (use mp4, mov, m4v, mkv or webm).` });
    else if (f.size > MAX_BYTES) rejected.push({ name: f.name, reason: `${f.name} is larger than 4 GB.` });
    else ok.push(f);
  }
  return { ok, rejected };
}
