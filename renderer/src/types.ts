// Props written by the Python engine (reel.overlay.build_props). Frames are output frames.

export type CaptionWord = { i: number; text: string; start_f: number; end_f: number; emph: boolean };
export type CaptionPage = { start_f: number; end_f: number; words: CaptionWord[] };
// timing "phrase": word times are unreliable (e.g. smeared Hinglish ASR) — show pages without per-word highlight
export type CaptionTrack = { family: string; tokens: Record<string, string>; script: string; timing?: string; pages: CaptionPage[] };
export type Title = { id: string; text: string; start_f: number; end_f: number; role: string; layer?: string };
export type Flash = { id: string; at_f: number; frames: number };
// picture-in-picture b-roll card; uri is relative to the workspace, which is the render's public dir
export type Pip = { id: string; uri: string; start_f: number; end_f: number; src_in_us: number; corner: string };
export type Box = { x: number; y: number; w: number; h: number }; // normalised to the output frame
// Per base clip: median face + burned-in text already in the footage (both to be kept clear).
export type FaceSpan = { start_f: number; end_f: number; box: Box | null; text: Box[] };

export type OverlayProps = {
  fps: number;
  width: number;
  height: number;
  duration_f: number;
  captions: CaptionTrack | null;
  titles: Title[];
  flashes: Flash[];
  pips?: Pip[];
  faces: FaceSpan[];
  safe: { top: number; bottom: number; right: number; left: number }; // px
  layer?: string; // "front" (default): everything over the picture · "behind": only titles that go behind the person
};

export const EMPTY: OverlayProps = {
  fps: 30, width: 1080, height: 1920, duration_f: 30, captions: null, titles: [], flashes: [], faces: [],
  safe: { top: 220, bottom: 420, right: 130, left: 60 },
};
