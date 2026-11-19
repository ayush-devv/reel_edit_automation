// FR-10 Libraries: SFX, music, b-roll and caption families, with play buttons, licences, and indexing a
// folder (AC-14: unreadable files are listed).
import { useRef, useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { BrollItem, CaptionFamily, LicenceFields, MusicItem, SfxItem } from "../../api/types";
import { Icon } from "../../components/icons";
import { PageHeader } from "../../components/Shell";
import { Table } from "../../components/Table";
import { Button, Field, IconButton, Loading, Mono, Notice, Panel, Segmented, Select, TextInput } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { prettyId } from "../../lib/format";

type Tab = "sfx" | "music" | "broll" | "captions";

/** Licence as the gate sees it: the registry id, the text as recorded (hover), and a refusal reason in red. */
function LicenceCell({ r, extra }: { r: LicenceFields & { license: string; source?: string }; extra?: string | null }) {
  return (
    <span className="flex flex-col" title={[r.source, r.license, extra].filter(Boolean).join(" — ")}>
      <span className="text-fg-secondary">{r.licence_id ?? r.license}</span>
      {r.licence_problem && <span className="text-meta text-st-fail">{r.licence_problem}</span>}
    </span>
  );
}
const ms = (n: number) => (n >= 60000 ? `${Math.floor(n / 60000)}:${String(Math.round((n % 60000) / 1000)).padStart(2, "0")}` : `${(n / 1000).toFixed(1)} s`);

function PlayButton({ src, label }: { src: string; label: string }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  if (!src) return <IconButton icon="play" label={`${label} (preview needs the engine)`} disabled />;
  return (
    <IconButton
      icon={playing ? "pause" : "play"}
      label={`${playing ? "Stop" : "Play"} ${label}`}
      onClick={() => {
        if (!audio.current) {
          audio.current = new Audio(src);
          audio.current.onended = () => setPlaying(false);
        }
        if (playing) {
          audio.current.pause();
          audio.current.currentTime = 0;
          setPlaying(false);
        } else {
          void audio.current.play().then(() => setPlaying(true), () => setPlaying(false));
        }
      }}
    />
  );
}

function IndexForm({ onDone }: { onDone: () => void }) {
  const api = useApi();
  const [kind, setKind] = useState<"sfx" | "music">("sfx");
  const [folder, setFolder] = useState("");
  const [source, setSource] = useState("");
  const [license, setLicense] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  return (
    <Panel title="Add a folder">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setMsg(null);
          try {
            await api.indexLibrary(kind, folder.trim(), source.trim(), license.trim());
            setMsg({ tone: "ok", text: "Indexing started. Files appear here as they’re read; unreadable files are listed below." });
            onDone();
          } catch (err) {
            setMsg({ tone: "error", text: friendlyError(err) });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Kind">
          <Segmented label="Kind" value={kind} onChange={setKind} options={[{ value: "sfx", label: "Sound effects" }, { value: "music", label: "Music" }]} />
        </Field>
        <Field label="Folder on this Mac" htmlFor="lib-folder" hint="Full path, e.g. ~/Audio/Sonniss GDC 2024">
          <TextInput id="lib-folder" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="~/Audio/Sonniss GDC 2024" required />
        </Field>
        <Field label="Source" htmlFor="lib-source">
          <TextInput id="lib-source" value={source} onChange={(e) => setSource(e.target.value)} placeholder="Sonniss GDC 2024" required />
        </Field>
        <Field label="Licence" htmlFor="lib-license" hint="Shown next to every file and in the delivery package.">
          <TextInput id="lib-license" value={license} onChange={(e) => setLicense(e.target.value)} placeholder="Royalty-free commercial use" required />
        </Field>
        <Button type="submit" variant="primary" icon="folder" busy={busy}>
          Index folder
        </Button>
        {msg && <Notice tone={msg.tone === "ok" ? "ok" : "error"}>{msg.text}</Notice>}
      </form>
    </Panel>
  );
}

/** C2: the built-in packs (procedural + Kenney CC0 sound effects, Incompetech CC BY music), fetched as a job. */
function StarterPacks({ onStarted }: { onStarted: () => void }) {
  const api = useApi();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-control bg-bg-raised px-4 py-3">
      <p className="text-fg-secondary">The free starter packs give the Editor ~250 sound effects and ~30 music tracks, each with its licence.</p>
      <Button
        icon="download"
        busy={busy}
        onClick={async () => {
          setBusy(true);
          setMsg(null);
          try {
            await api.fetchStarterPacks();
            setMsg("Downloading — it shows in the jobs list; the library fills in when it finishes.");
            onStarted();
          } catch (e) {
            setMsg(friendlyError(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        Get the starter packs
      </Button>
      {msg && <span className="text-meta text-fg-secondary">{msg}</span>}
    </div>
  );
}

export default function Libraries() {
  const api = useApi();
  const lib = useQuery(() => api.libraries(), [api]);
  const [tab, setTab] = useState<Tab>("sfx");
  const [cat, setCat] = useState("");
  const d = lib.data;
  const cats = [...new Set((d?.sfx ?? []).map((s) => s.category))].sort();

  return (
    <div className="w-full px-8 py-8">
      <PageHeader title="Libraries" subtitle="Sounds, music and b-roll the Editor may use — each with its licence." />
      {lib.error ? <Notice tone="error">{friendlyError(lib.error)}</Notice> : null}
      {!d ? (
        <Loading />
      ) : (
        <div className="grid grid-cols-12 gap-x-10 gap-y-6">
          <div className="col-span-12 xl:col-span-8">
            <Panel
              title={
                <Segmented
                  label="Library"
                  value={tab}
                  onChange={setTab}
                  options={[
                    { value: "sfx", label: `Sound effects ${d.sfx.length}` },
                    { value: "music", label: `Music ${d.music.length}` },
                    { value: "broll", label: `B-roll ${d.broll.length}` },
                    { value: "captions", label: `Caption styles ${d.caption_families.length}` },
                  ]}
                />
              }
              actions={
                tab === "sfx" ? (
                  <div className="flex items-center gap-3">
                    <label htmlFor="lib-cat" className="text-meta text-fg-secondary">
                      Category
                    </label>
                    <div className="w-44">
                    <Select id="lib-cat" value={cat} onChange={(e) => setCat(e.target.value)}>
                      <option value="">All categories</option>
                      {cats.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </Select>
                    </div>
                  </div>
                ) : null
              }
            >
              {(tab === "sfx" || tab === "music") && d[tab].length === 0 && <StarterPacks onStarted={lib.reload} />}
              {tab === "sfx" && (
                <Table<SfxItem>
                  caption="Sound effects"
                  empty={cat ? `No sounds in “${cat}”.` : "No sound effects yet. Add a folder on the right, or run `reel assets fetch` for the built-in set."}
                  rows={d.sfx.filter((s) => !cat || s.category === cat)}
                  rowKey={(r) => r.id}
                  columns={[
                    { key: "p", label: "", className: "w-10", render: (r) => <PlayButton src={api.libraryMediaUrl("sfx", r.id)} label={r.id} /> },
                    { key: "id", label: "Sound", render: (r) => <span className="text-fg-primary">{r.id}</span> },
                    { key: "c", label: "Category", render: (r) => <span className="rounded bg-bg-overlay px-1.5 py-0.5 text-label text-fg-secondary">{r.category}</span> },
                    { key: "d", label: "Length", align: "right", render: (r) => <Mono className="text-fg-secondary">{ms(r.duration_ms)}</Mono> },
                    { key: "l", label: "Licence", render: (r) => <LicenceCell r={r} /> },
                  ]}
                />
              )}
              {tab === "music" && (
                <Table<MusicItem>
                  caption="Music"
                  empty="No music yet. Add a folder on the right, or run `reel assets fetch` for the licensed starter tracks."
                  rows={d.music}
                  rowKey={(r) => r.id}
                  columns={[
                    { key: "p", label: "", className: "w-10", render: (r) => <PlayButton src={api.libraryMediaUrl("music", r.id)} label={r.title} /> },
                    { key: "t", label: "Track", render: (r) => <span className="text-fg-primary">{r.title}</span> },
                    { key: "m", label: "Mood", render: (r) => <span className="text-fg-secondary">{r.mood}</span> },
                    { key: "b", label: "Tempo", align: "right", render: (r) => <Mono className="text-fg-secondary">{r.bpm} bpm</Mono> },
                    { key: "d", label: "Length", align: "right", render: (r) => <Mono className="text-fg-secondary">{ms(r.duration_ms)}</Mono> },
                    { key: "l", label: "Licence", render: (r) => <LicenceCell r={r} extra={r.attribution} /> },
                  ]}
                />
              )}
              {tab === "broll" && (
                <Table<BrollItem>
                  caption="B-roll"
                  empty="No b-roll clips yet. Add a Pexels key in Settings to let the Editor search stock footage."
                  rows={d.broll}
                  rowKey={(r) => r.id}
                  columns={[
                    { key: "p", label: "", className: "w-10", render: (r) => <PlayButton src={api.libraryMediaUrl("broll", r.id)} label={r.id} /> },
                    { key: "d", label: "Clip", render: (r) => <span className="text-fg-primary">{r.description}</span> },
                    { key: "s", label: "Shot", render: (r) => <span className="text-fg-secondary">{r.shot}</span> },
                    { key: "len", label: "Length", align: "right", render: (r) => <Mono className="text-fg-secondary">{ms(r.duration_ms)}</Mono> },
                    { key: "l", label: "Licence", render: (r) => <LicenceCell r={r} /> },
                  ]}
                />
              )}
              {tab === "captions" && (
                <Table<CaptionFamily>
                  caption="Caption styles"
                  empty="No caption styles found — the engine’s knowledge files may be missing. Check Settings → Health."
                  rows={d.caption_families}
                  rowKey={(r) => r.id}
                  columns={[
                    { key: "id", label: "Style", render: (r) => <span className="text-fg-primary">{prettyId(r.id)}</span> },
                    { key: "m", label: "Mood", render: (r) => <span className="text-fg-secondary">{r.mood}</span> },
                    { key: "f", label: "Best for", render: (r) => <span className="text-fg-secondary">{r.for.map(prettyId).join(", ")}</span> },
                  ]}
                />
              )}
            </Panel>
          </div>
          <div className="col-span-12 xl:col-span-4">
            <IndexForm onDone={lib.reload} />
            {(d.unreadable?.length ?? 0) > 0 && (
              <Panel title="Couldn’t read">
                <ul className="divide-y divide-line-subtle">
                  {d.unreadable!.map((u) => (
                    <li key={u.file} className="flex gap-3 py-3">
                      <Icon name="alert" size={16} className="mt-0.5 shrink-0 text-st-hold" />
                      <div className="min-w-0">
                        <Mono className="block truncate text-fg-primary">{u.file}</Mono>
                        <p className="text-meta text-fg-secondary">{u.reason}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
