// FR-12 Settings, health and costs (AC-16): readiness checks with one-line fixes, AI usage, settings,
// and one-at-a-time project delete.
import { useEffect, useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { Settings as SettingsT } from "../../api/types";
import { Icon } from "../../components/icons";
import { PageHeader } from "../../components/Shell";
import { Button, cx, Field, Loading, Mono, Notice, Panel, Segmented, Select, TextInput } from "../../components/ui";
import { useStatus } from "../../hooks/status";
import { useQuery } from "../../hooks/useQuery";
import { usd } from "../../lib/format";

function Health() {
  const { health, engine } = useStatus();
  if (!health) return <Panel title="Health">{engine === "checking" ? <Loading /> : <Notice tone="error">Engine is not running.</Notice>}</Panel>;
  return (
    <Panel title="Health" actions={<Mono className="text-fg-muted">engine v{health.version}</Mono>}>
      <ul className="divide-y divide-line-subtle">
        {health.tools.map((t) => (
          <li key={t.name} className="flex items-start gap-3 py-3">
            <span className={cx("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full", t.ok ? "bg-st-sendable/[0.16] text-st-sendable" : "bg-st-fail/[0.16] text-st-fail")} aria-label={t.ok ? "OK" : "Problem"}>
              <Icon name={t.ok ? "check" : "x"} size={12} />
            </span>
            <div className="min-w-0">
              <p className="font-medium text-fg-primary">{t.name}</p>
              <p className={cx(t.ok ? "text-fg-secondary" : "text-st-fail")}>{t.detail}</p>
            </div>
          </li>
        ))}
      </ul>
      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-line-subtle pt-4">
        <div>
          <dt className="text-label text-fg-muted">Disk free</dt>
          <dd className="font-mono text-[15px] tabular">{health.disk_free_gb} GB</dd>
        </div>
        <div>
          <dt className="text-label text-fg-muted">Memory in use</dt>
          <dd className="font-mono text-[15px] tabular">
            {health.memory_gb.used.toFixed(1)} / {health.memory_gb.budget} GB
          </dd>
        </div>
        <div>
          <dt className="text-label text-fg-muted">Jobs</dt>
          <dd className="font-mono text-[15px] tabular">
            {health.jobs.running}/{health.jobs.limit} · {health.jobs.queued} queued
          </dd>
        </div>
      </dl>
    </Panel>
  );
}

function Usage() {
  const api = useApi();
  const costs = useQuery(() => api.costs(30), [api]);
  const projects = useQuery(() => api.projects(), [api]);
  const names = new Map((projects.data ?? []).map((p) => [p.id, p.name]));
  const c = costs.data;
  if (costs.error) return <Panel title="AI usage"><Notice tone="error">{friendlyError(costs.error)}</Notice></Panel>;
  if (!c) return <Panel title="AI usage"><Loading /></Panel>;
  const max = Math.max(0.01, ...c.by_day.map((d) => d.usd));
  const today = c.by_day.at(-1);
  return (
    <Panel title="AI usage" actions={<span className="text-label font-normal text-fg-muted">last 30 days · estimated</span>}>
      <div className="flex items-end gap-8">
        <div>
          <p className="text-label text-fg-muted">Total</p>
          <p className="font-mono text-[28px] font-medium leading-8 tabular">{usd(c.total_usd)}</p>
        </div>
        <div>
          <p className="text-label text-fg-muted">Today</p>
          <p className="font-mono text-[20px] leading-7 tabular">{usd(today?.usd ?? 0)}</p>
        </div>
      </div>
      <div className="mt-4 flex h-24 items-end gap-1" role="img" aria-label={`Cost per day: ${c.by_day.map((d) => `${d.date} ${usd(d.usd)}`).join(", ")}`}>
        {c.by_day.map((d) => (
          <div key={d.date} className="group relative flex-1">
            <div className="rounded-t-[3px] bg-ai-glow/70 transition-colors group-hover:bg-ai-glow" style={{ height: `${Math.max(2, (d.usd / max) * 88)}px` }} />
            <span className="pointer-events-none absolute -top-6 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded bg-bg-overlay px-1.5 py-0.5 font-mono text-[11px] text-fg-primary group-hover:block">{usd(d.usd)}</span>
          </div>
        ))}
      </div>
      <h3 className="mb-2 mt-5 text-label text-fg-muted">Per project</h3>
      <ul className="divide-y divide-line-subtle">
        {c.by_project.map((p) => (
          <li key={p.id} className="flex items-center justify-between py-2">
            <span className="truncate text-fg-primary">{names.get(p.id) ?? p.id}</span>
            <Mono className="text-fg-secondary">{usd(p.usd)}</Mono>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function SettingsForm() {
  const api = useApi();
  const { refresh } = useStatus();
  const q = useQuery(() => api.settings(), [api]);
  const [s, setS] = useState<SettingsT | null>(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  useEffect(() => {
    if (q.data) setS(q.data);
  }, [q.data]);
  if (!s) return <Panel title="Settings">{q.error ? <Notice tone="error">{friendlyError(q.error)}</Notice> : <Loading />}</Panel>;
  const toggleDel = (d: "feed_4x5" | "square") => setS({ ...s, default_deliverables: s.default_deliverables.includes(d) ? s.default_deliverables.filter((x) => x !== d) : [...s.default_deliverables, d] });
  return (
    <Panel title="Settings">
      <form
        className="space-y-5"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setMsg(null);
          try {
            await api.saveSettings(key ? { ...s, pexels_key: key } : s);
            setKey("");
            setMsg({ tone: "ok", text: "Saved." });
            refresh();
            q.reload();
          } catch (err) {
            setMsg({ tone: "error", text: friendlyError(err) });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Edits allowed to run at once" hint="More than 3 risks running out of memory on a 16 GB Mac.">
          <Segmented label="Edits at once" value={String(s.max_jobs)} onChange={(v) => setS({ ...s, max_jobs: Number(v) })} options={["1", "2", "3"].map((v) => ({ value: v, label: v }))} />
        </Field>
        <Field label="Default platform" htmlFor="def-platform">
          <Select id="def-platform" value={String(s.default_brief.platform ?? "platform.instagram_reels")} onChange={(e) => setS({ ...s, default_brief: { ...s.default_brief, platform: e.target.value } })}>
            <option value="platform.instagram_reels">Instagram Reels</option>
            <option value="platform.youtube_shorts">YouTube Shorts</option>
            <option value="platform.tiktok">TikTok</option>
          </Select>
        </Field>
        <fieldset>
          <legend className="mb-2 text-label text-fg-secondary">Default extra deliverables</legend>
          <div className="flex gap-6">
            {(
              [
                ["feed_4x5", "4:5 feed"],
                ["square", "Square 1:1"],
              ] as const
            ).map(([k, l]) => (
              <label key={k} className="flex cursor-pointer items-center gap-2">
                <input type="checkbox" className="h-4 w-4 accent-[#6A4BF0]" checked={s.default_deliverables.includes(k)} onChange={() => toggleDel(k)} />
                {l}
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="Pexels API key" htmlFor="pexels" hint={s.pexels_key_set ? "A key is saved on this Mac. Enter a new one to replace it." : "Stored only on this Mac. Enables stock search in Libraries."}>
          <TextInput id="pexels" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={s.pexels_key_set ? "••••••••••••" : "Paste your key"} />
        </Field>
        <Field label="Projects folder" htmlFor="pdir" hint="Where footage, renders and packages are stored.">
          <TextInput id="pdir" value={s.projects_dir} onChange={(e) => setS({ ...s, projects_dir: e.target.value })} className="font-mono text-[13px]" />
        </Field>
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" busy={busy}>
            Save settings
          </Button>
          {msg && <span className={cx("text-label", msg.tone === "ok" ? "text-st-sendable" : "text-st-fail")}>{msg.text}</span>}
        </div>
      </form>
    </Panel>
  );
}

function ProjectActions() {
  const api = useApi();
  const q = useQuery(() => api.projects(), [api]);
  const [id, setId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const p = q.data?.find((x) => x.id === id);
  return (
    <Panel title="Remove a project">
      <p className="mb-3 text-fg-secondary">One at a time. Removed projects go to the trash folder inside the projects folder.</p>
      <div className="flex gap-2">
        <div className="flex-1">
          <Select aria-label="Project to remove" value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">Choose a project…</option>
            {(q.data ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
                {x.client ? ` — ${x.client}` : ""}
              </option>
            ))}
          </Select>
        </div>
        <Button
          variant="danger"
          icon="trash"
          busy={busy}
          disabled={!p}
          onClick={async () => {
            if (!p || !window.confirm(`Move “${p.name}”${p.client ? ` (${p.client})` : ""} to the trash? Its footage, renders and package go with it.`)) return;
            setBusy(true);
            setMsg(null);
            try {
              await api.deleteProject(p.id);
              setMsg({ tone: "ok", text: `Moved “${p.name}” to the trash.` });
              setId("");
              q.reload();
            } catch (e) {
              setMsg({ tone: "error", text: friendlyError(e) });
            } finally {
              setBusy(false);
            }
          }}
        >
          Remove
        </Button>
      </div>
      {msg && <p className={cx("mt-2 text-label", msg.tone === "ok" ? "text-st-sendable" : "text-st-fail")}>{msg.text}</p>}
    </Panel>
  );
}

export default function Settings() {
  return (
    <div className="mx-auto w-full max-w-[1440px] px-8 py-8">
      <PageHeader eyebrow="Studio" title="Settings" subtitle="Health, AI costs and how the studio runs." />
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 space-y-4 xl:col-span-7">
          <Health />
          <Usage />
        </div>
        <div className="col-span-12 space-y-4 xl:col-span-5">
          <SettingsForm />
          <ProjectActions />
        </div>
      </div>
    </div>
  );
}
