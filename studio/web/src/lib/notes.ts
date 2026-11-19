// Client-note line parser, mirroring engine/src/reel/notes.py `parse` so the preview matches what the
// engine will read. Adds the "Couldn't read" bucket from FR-7 / AC-11.

export interface ParsedNote {
  line: string;
  t: number | null; // seconds into the reel; null = whole reel
  text: string;
}

const TC = /^\s*[[(]?\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\s*[\])]?\s*[-–:,]?\s*(.+)$/;
const SECS = /^\s*[[(]?\s*(\d+(?:\.\d+)?)\s*s(?:ec)?\s*[\])]?\s*[-–:,]?\s*(.+)$/i;

/** A note body we can't act on: no real words, or explicit confusion like "??". */
export function isUnreadable(body: string): boolean {
  const words = body.match(/[\p{L}]{2,}/gu) ?? [];
  if (words.length === 0) return true;
  if (/\?\?/.test(body)) return true;
  const letters = (body.match(/\p{L}/gu) ?? []).length;
  return letters / body.replace(/\s/g, "").length < 0.5;
}

export function parseNotes(text: string): { notes: ParsedNote[]; unreadable: string[] } {
  const notes: ParsedNote[] = [];
  const unreadable: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/^[-•*]+/, "").trim();
    if (!line) continue;
    let t: number | null = null;
    let body = line;
    const m = TC.exec(line);
    const s = m ? null : SECS.exec(line);
    if (m) {
      t = Number(m[1] ?? 0) * 3600 + Number(m[2]) * 60 + Number(m[3]);
      body = m[4].trim();
    } else if (s) {
      t = Number(s[1]);
      body = s[2].trim();
    }
    if (isUnreadable(body)) unreadable.push(line);
    else notes.push({ line, t, text: body });
  }
  return { notes, unreadable };
}

export function fmtTime(t: number): string {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(s % 1 ? 1 : 0).padStart(s % 1 ? 4 : 2, "0")}`;
}
