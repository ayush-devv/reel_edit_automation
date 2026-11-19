// FR-2 Start a new edit: drop videos, fill the brief, pick a brand, start (or queue) the run.
import { useEffect, useId, useRef, useState, type DragEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../api/context";
import { friendlyError } from "../api/errors";
import { Icon } from "../components/icons";
import { PageHeader } from "../components/Shell";
import { Button, cx, Field, Notice, Panel, ProgressBar, Segmented, Select, TextArea, TextInput } from "../components/ui";
import { useStatus } from "../hooks/status";
import { useQuery } from "../hooks/useQuery";
import { EMPTY_FORM, formErrors, formWithDefaults, GENRES, GOALS, loadTemplates, PLATFORMS, saveTemplate, toBrief, type BriefForm } from "../lib/brief";
import { bytes, prettyId } from "../lib/format";
import { screenFiles, takePendingFiles } from "../lib/pendingFiles";

function useFieldId() {
  return useId();
}

function TF({ label, value, onChange, hint, placeholder, error, required }: { label: string; value: string; onChange: (v: string) => void; hint?: ReactNode; placeholder?: string; error?: string; required?: boolean }) {
  const id = useFieldId();
  return (
    <Field label={label + (required ? " *" : "")} htmlFor={id} hint={hint} error={error}>
      <TextInput id={id} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} aria-required={required} aria-invalid={!!error} />
    </Field>
  );
}

function TA({ label, value, onChange, hint, placeholder, rows = 3 }: { label: string; value: string; onChange: (v: string) => void; hint?: ReactNode; placeholder?: string; rows?: number }) {
  const id = useFieldId();
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <TextArea id={id} value={value} placeholder={placeholder} rows={rows} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function SF({ label, value, onChange, children, hint }: { label: string; value: string; onChange: (v: string) => void; children: ReactNode; hint?: ReactNode }) {
  const id = useFieldId();
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </Select>
    </Field>
  );
}

export default function NewEdit() {
  const api = useApi();
  const nav = useNavigate();
  const { health, jobs } = useStatus();
  const brands = useQuery(() => api.brands(), [api]);
  const settings = useQuery(() => api.settings(), [api]);
  const [files, setFiles] = useState<File[]>([]);
  const [rejected, setRejected] = useState<{ name: string; reason: string }[]>([]);
  const [form, setForm] = useState<BriefForm>(EMPTY_FORM);
  const [brand, setBrand] = useState("");
  const [refUrl, setRefUrl] = useState("");
  const [sent, setSent] = useState<{ loaded: number; total: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [templates, setTemplates] = useState(loadTemplates);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const addFiles = (list: File[]) => {
    const { ok, rejected: bad } = screenFiles(list);
    setFiles((f) => [...f, ...ok.filter((n) => !f.some((x) => x.name === n.name && x.size === n.size))]);
    setRejected(bad);
    if (ok.length && !form.name) set("name", ok[0].name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
  };

  // Settings → default brief / deliverables fill the empty form once (the name the files suggested is kept).
  const defaultsApplied = useRef(false);
  useEffect(() => {
    if (!settings.data || defaultsApplied.current) return;
    defaultsApplied.current = true;
    const d = formWithDefaults(settings.data.default_brief, settings.data.default_deliverables);
    setForm((f) => ({ ...d, name: f.name }));
  }, [settings.data]);

  useEffect(() => {
    const pending = takePendingFiles();
    if (pending.length) addFiles(pending);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function set<K extends keyof BriefForm>(k: K, v: BriefForm[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  const errors = formErrors(form);
  const running = jobs?.running.length ?? health?.jobs.running ?? 0;
  const limit = health?.jobs.limit ?? 3;
  const willQueue = running >= limit;

  // Per-file progress from the cumulative bytes of the multipart body (files are sent in order).
  const perFile = (i: number): number | null => {
    if (!sent) return null;
    const scale = sent.total / Math.max(1, files.reduce((a, f) => a + f.size, 0));
    const before = files.slice(0, i).reduce((a, f) => a + f.size, 0) * scale;
    return Math.max(0, Math.min(1, (sent.loaded - before) / Math.max(1, files[i].size * scale)));
  };

  async function start() {
    setTouched(true);
    setError(null);
    if (Object.keys(errors).length) return;
    if (!files.length) {
      setError("Add at least one video file.");
      return;
    }
    setBusy(true);
    try {
      const { id } = await api.createProject({ files, name: form.name.trim(), brief: toBrief(form), brand: brand || null, reference_url: refUrl.trim() || null }, (loaded, total) =>
        setSent({ loaded, total }),
      );
      nav(`/p/${id}/live`);
    } catch (e) {
      setError(friendlyError(e));
      setBusy(false);
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    addFiles([...e.dataTransfer.files]);
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] px-8 py-8">
      <PageHeader
        title="New edit"
        subtitle="Add the raw footage and the client’s brief. Only the project name is required."
        actions={
          Object.keys(templates).length > 0 ? (
            <div className="w-56">
              <Select
                aria-label="Use a saved brief template"
                value=""
                onChange={(e) => {
                  const t = templates[e.target.value];
                  if (t) setForm((f) => ({ ...t, name: f.name }));
                }}
              >
                <option value="">Use a brief template…</option>
                {Object.keys(templates).map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </Select>
            </div>
          ) : null
        }
      />

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 space-y-4 xl:col-span-5">
          <Panel title="Footage">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={cx(
                "flex flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed px-6 py-10 text-center transition-colors duration-hover",
                dragOver ? "border-ai-glow bg-ai/[0.08]" : "border-line-strong bg-bg-inset",
              )}
            >
              <Icon name="upload" size={26} className="text-ai-glow" />
              <p className="font-medium">Drop video files here</p>
              <p className="text-label font-normal text-fg-muted">mp4, mov, m4v, mkv or webm · up to 4 GB each</p>
              <Button className="mt-2" icon="folder" onClick={() => fileInput.current?.click()}>
                Choose files
              </Button>
              <input
                ref={fileInput}
                type="file"
                multiple
                accept=".mp4,.mov,.m4v,.mkv,.webm,video/*"
                className="sr-only"
                tabIndex={-1}
                aria-label="Choose video files"
                onChange={(e) => {
                  addFiles([...(e.target.files ?? [])]);
                  e.target.value = "";
                }}
              />
            </div>
            {rejected.length > 0 && (
              <div className="mt-4 space-y-2">
                {rejected.map((r) => (
                  <Notice key={r.name} tone="error" title="Not added">
                    {r.reason}
                  </Notice>
                ))}
              </div>
            )}
            {files.length > 0 && (
              <ul className="mt-4 space-y-3" aria-label="Files to upload">
                {files.map((f, i) => (
                  <li key={f.name + f.size} className="rounded-card border border-line-subtle bg-bg-overlay px-3 py-2.5">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <Icon name="film" size={16} className="shrink-0 text-fg-muted" />
                        <span className="truncate">{f.name}</span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className="font-mono text-mono text-fg-muted">{bytes(f.size)}</span>
                        {!busy && (
                          <button type="button" className="text-fg-muted hover:text-fg-primary" aria-label={`Remove ${f.name}`} onClick={() => setFiles((x) => x.filter((_, j) => j !== i))}>
                            <Icon name="x" size={16} />
                          </button>
                        )}
                      </span>
                    </div>
                    <ProgressBar value={perFile(i) ?? 0} label={`Upload ${f.name}`} tone={perFile(i) === 1 ? "ok" : "ai"} />
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Extras">
            <div className="space-y-4">
              <SF label="Brand kit" value={brand} onChange={setBrand} hint="Locks the brand’s colours, caption style and look.">
                <option value="">No brand kit</option>
                {(brands.data ?? []).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.brand.client}
                  </option>
                ))}
              </SF>
              <TF label="Reference reel (optional)" value={refUrl} onChange={setRefUrl} placeholder="/Users/you/Downloads/reference.mp4" hint="A video file on this Mac (links aren’t supported). The Editor studies its pacing and caption style." />
            </div>
          </Panel>
        </div>

        <div className="col-span-12 xl:col-span-7">
          <Panel title="Brief">
            <div className="grid grid-cols-2 gap-x-4 gap-y-5">
              <TF label="Project name" required value={form.name} onChange={(v) => set("name", v)} error={touched ? errors.name : undefined} placeholder="e.g. Glow serum testimonial" />
              <TF label="Client" value={form.client} onChange={(v) => set("client", v)} placeholder="e.g. DearMa Skincare" />
              <Field label="Language">
                <Segmented
                  label="Language"
                  value={form.language}
                  onChange={(v) => set("language", v)}
                  options={[
                    { value: "auto", label: "Auto" },
                    { value: "en", label: "English" },
                    { value: "hi", label: "Hindi" },
                    { value: "hinglish", label: "Hinglish" },
                  ]}
                />
              </Field>
              <Field label="Caption script">
                <Segmented
                  label="Caption script"
                  value={form.script}
                  onChange={(v) => set("script", v)}
                  options={[
                    { value: "latin", label: "Latin" },
                    { value: "devanagari", label: "Devanagari" },
                    { value: "mixed", label: "Mixed" },
                  ]}
                />
              </Field>
              <SF label="Platform" value={form.platform} onChange={(v) => set("platform", v)}>
                {PLATFORMS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </SF>
              <SF label="Goal" value={form.goal} onChange={(v) => set("goal", v)}>
                <option value="">Let the Editor decide</option>
                {GOALS.map((g) => (
                  <option key={g} value={g}>
                    {prettyId(g)}
                  </option>
                ))}
              </SF>
              <SF label="Genre" value={form.genre} onChange={(v) => set("genre", v)}>
                <option value="">Detect from footage</option>
                {GENRES.map((g) => (
                  <option key={g} value={g}>
                    {prettyId(g)}
                  </option>
                ))}
              </SF>
              <TF label="Audience" value={form.audience} onChange={(v) => set("audience", v)} placeholder="e.g. women 22–35 with sensitive skin" />
              <Field label="Target length (seconds)" error={touched ? errors.maxLen : undefined}>
                <div className="flex items-center gap-2">
                  <TextInput aria-label="Minimum seconds" inputMode="numeric" value={form.minLen} onChange={(e) => set("minLen", e.target.value)} />
                  <span className="text-fg-muted">to</span>
                  <TextInput aria-label="Maximum seconds" inputMode="numeric" value={form.maxLen} onChange={(e) => set("maxLen", e.target.value)} />
                </div>
              </Field>
              <TF label="Tone" value={form.tone} onChange={(v) => set("tone", v)} placeholder="e.g. warm, honest" />
              <TF label="Call to action" value={form.cta} onChange={(v) => set("cta", v)} placeholder="e.g. Link in bio" />
              <TF label="Product names" value={form.products} onChange={(v) => set("products", v)} hint="Comma-separated." placeholder="DearMa, Glow Serum" />
              <div className="col-span-2">
                <TA label="Must-keep lines" value={form.mustKeep} onChange={(v) => set("mustKeep", v)} hint="One per line. The validator refuses edits that drop them." placeholder="ten days later my skin felt calm" />
              </div>
              <TA label="Banned claims" value={form.banned} onChange={(v) => set("banned", v)} hint="One per line." placeholder="cures acne" rows={2} />
              <TA label="Spelling vocabulary" value={form.vocabulary} onChange={(v) => set("vocabulary", v)} hint="Names and terms to spell right, comma-separated." placeholder="DearMa, niacinamide" rows={2} />
              <div className="col-span-2">
                <TA label="Notes for the Editor" value={form.notes} onChange={(v) => set("notes", v)} rows={2} />
              </div>
              <fieldset className="col-span-2">
                <legend className="mb-2 text-label text-fg-secondary">Extra deliverables (the 9:16 master is always made)</legend>
                <div className="flex gap-6">
                  {(
                    [
                      ["feed45", "4:5 feed"],
                      ["square", "Square 1:1"],
                    ] as const
                  ).map(([k, l]) => (
                    <label key={k} className="flex cursor-pointer items-center gap-2">
                      <input type="checkbox" className="h-4 w-4 accent-[#6A4BF0]" checked={form[k]} onChange={(e) => set(k, e.target.checked)} />
                      {l}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
          </Panel>

          <div className="sticky bottom-0 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-panel border border-line-subtle bg-bg-raised/95 px-6 py-4 backdrop-blur">
            <div className="min-w-[260px] flex-1 text-fg-secondary">
              {willQueue ? (
                <span className="flex items-center gap-2 text-st-hold">
                  <Icon name="clock" size={16} /> {running} of {limit} edits running — this one will be queued and starts when a slot frees up.
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-st-sendable" aria-hidden="true" /> {running} of {limit} edits running — starts right away.
                </span>
              )}
              {error && (
                <p className="mt-1 text-st-fail" role="alert">
                  {error}
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                onClick={() => {
                  const n = window.prompt("Save this brief as a template named:", form.client || "My template");
                  if (n) {
                    saveTemplate(n, form);
                    setTemplates(loadTemplates());
                  }
                }}
              >
                Save as template
              </Button>
              <Button variant="primary" size={40} icon="play" busy={busy} onClick={start}>
                {busy ? "Uploading…" : willQueue ? "Queue edit" : "Start edit"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
