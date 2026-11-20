// FR-12 Settings, health and costs (AC-16): readiness checks with one-line fixes, AI usage, settings,
// and one-at-a-time project delete.
import { useEffect, useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { Settings as SettingsT } from "../../api/types";
import { Icon } from "../../components/icons";
import { PageHeader } from "../../components/Shell";
import { Button, cx, Field, Loading, Mono, Notice, Panel, Segmented, Select, TextInput, Toggle } from "../../components/ui";
import { notificationsOn, setNotifications } from "../../hooks/notify";
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
            <span className={cx("mt-0.5 shrink-0", t.ok ? "text-st-sendable" : t.required ? "text-st-fail" : "text-fg-muted")} aria-label={t.ok ? "OK" : "Problem"}>
              <Icon name={t.ok ? "check" : "x"} size={16} />
            </span>
            <div className="min-w-0">
              <p className="text-ui text-fg-primary">
                {t.name}
                {!t.ok && !t.required && <span className="ml-2 text-meta text-fg-muted">optional</span>}
              </p>
              <p className={cx("text-meta", t.ok || !t.required ? "text-fg-secondary" : "text-st-fail")}>{t.detail}</p>
            </div>
          </li>
        ))}
      </ul>
      <dl className="mt-2 grid grid-cols-3 gap-3 border-t border-line-subtle pt-4">
        <div>
          <dt className="text-meta text-fg-muted">Disk free</dt>
          <dd className="font-mono text-mono tabular">{health.disk_free_gb} GB</dd>
        </div>
        <div>
          <dt className="text-meta text-fg-muted">Memory in use</dt>
          <dd className="font-mono text-mono tabular">
            {health.memory_gb.used.toFixed(1)} / {health.memory_gb.budget} GB
            {typeof health.memory_gb.system?.available === "number" && <span className="block text-meta text-fg-muted">{health.memory_gb.system.available.toFixed(1)} GB free on this Mac</span>}
          </dd>
        </div>
        <div>
          <dt className="text-meta text-fg-muted">Jobs</dt>
          <dd className="font-mono text-mono tabular">
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
    <Panel title="AI usage" actions={<span className="text-meta text-fg-muted">last 30 days · estimated</span>}>
      <div className="flex items-end gap-8">
        <div>
          <p className="text-meta text-fg-muted">Total</p>
          <p className="font-mono text-timecode-lg tabular">{usd(c.total_usd)}</p>
        </div>
        <div>
          <p className="text-meta text-fg-muted">Today</p>
          <p className="font-mono text-timecode-lg tabular">{usd(today?.usd ?? 0)}</p>
        </div>
      </div>
      <div className="mt-4 flex h-24 items-end gap-1 border-b border-line-subtle" role="img" aria-label={`Cost per day: ${c.by_day.map((d) => `${d.date} ${usd(d.usd)}`).join(", ")}`}>
        {c.by_day.map((d, i) => (
          <div key={d.date} className="group relative flex-1">
            {/* Cost is data, not AI activity: graphite bars, today in primary. */}
            <div className={cx("transition-colors group-hover:bg-fg-primary", i === c.by_day.length - 1 ? "bg-fg-primary" : "bg-fg-muted")} style={{ height: `${Math.max(2, (d.usd / max) * 88)}px` }} />
            <span className="pointer-events-none absolute -top-6 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded-control bg-bg-overlay px-1.5 py-0.5 font-mono text-meta text-fg-primary shadow-menu group-hover:block">{usd(d.usd)}</span>
          </div>
        ))}
      </div>
      <h3 className="mb-2 mt-5 text-meta text-fg-muted">Per project</h3>
      {c.by_project.length === 0 && <p className="text-meta text-fg-muted">No AI use in the last 30 days.</p>}
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
  const [pixKey, setPixKey] = useState("");
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
            setS(await api.saveSettings({ ...s, ...(key ? { pexels_key: key } : {}), ...(pixKey ? { pixabay_key: pixKey } : {}) }));
            setKey("");
            setPixKey("");
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
        <Field label="Default language" hint="New edits start with these; each brief can change them.">
          <Segmented
            label="Default language"
            value={String(s.default_brief.language ?? "auto")}
            onChange={(v) => setS({ ...s, default_brief: { ...s.default_brief, language: v === "auto" ? null : (v as "en" | "hi" | "hinglish") } })}
            options={[
              { value: "auto", label: "Auto" },
              { value: "en", label: "English" },
              { value: "hi", label: "Hindi" },
              { value: "hinglish", label: "Hinglish" },
            ]}
          />
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
                <input type="checkbox" className="h-4 w-4 accent-[#F2A93B]" checked={s.default_deliverables.includes(k)} onChange={() => toggleDel(k)} />
                {l}
              </label>
            ))}
          </div>
        </fieldset>
        <Field
          label="Pixabay API key"
          htmlFor="pixabay"
          hint={s.pixabay_key_set ? "A key is saved on this Mac. Enter a new one to replace it." : "Free at pixabay.com/api/docs (log in; the key is shown on that page). Stored only on this Mac. Lets an edit find stock b-roll."}
        >
          <TextInput id="pixabay" type="password" autoComplete="off" value={pixKey} onChange={(e) => setPixKey(e.target.value)} placeholder={s.pixabay_key_set ? "••••••••••••" : "Paste your key…"} />
        </Field>
        <Field label="Pexels API key" htmlFor="pexels" hint={s.pexels_key_set ? "A key is saved on this Mac. Enter a new one to replace it." : "Stored only on this Mac. Enables stock search in Libraries."}>
          <TextInput id="pexels" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={s.pexels_key_set ? "••••••••••••" : "Paste your key"} />
        </Field>
        <Field label="Monthly AI spend cap (USD)" htmlFor="cap" hint="0 = no cap. Past it, a new edit, revision or notes run asks before it starts; an edit already running always finishes.">
          <TextInput id="cap" inputMode="decimal" value={String(s.monthly_cap_usd ?? 0)}
                     onChange={(e) => setS({ ...s, monthly_cap_usd: Math.max(0, Number(e.target.value.replace(/[^0-9.]/g, "")) || 0) })}
                     className="w-32 font-mono text-mono" />
        </Field>
        <Field label="Projects folder" htmlFor="pdir" hint="Where footage, renders and packages are stored. To use another folder, restart with: reel studio --projects <folder>">
          <TextInput id="pdir" value={s.projects_dir} readOnly className="font-mono text-mono text-fg-secondary" />
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

/** 4.1 cost guard: this month's AI spend against the cap, and paid requests waiting for approval. */
function SpendPanel() {
  const api = useApi();
  const q = useQuery(() => api.spend(), [api], { intervalMs: 30000 });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const st = q.data;
  return (
    <Panel title="AI spend this month">
      {!st ? (
        q.error ? <Notice tone="error">{friendlyError(q.error)}</Notice> : <Loading />
      ) : (
        <div className="space-y-3">
          <p className="text-fg-primary">
            <span className="font-mono">${st.month.total_usd.toFixed(2)}</span>
            {st.cap_usd ? <> of a <span className="font-mono">${st.cap_usd.toFixed(2)}</span> cap</> : " · no cap set"}
            {st.over_cap && <span className="text-st-hold"> · at the cap: new runs ask first</span>}
          </p>
          <p className="text-meta text-fg-muted">
            Claude ${st.month.claude_usd.toFixed(2)} · paid generators ${st.month.paid_usd.toFixed(2)}
            {st.estimate && <> · one more edit ≈ ${st.estimate.low_usd.toFixed(2)}–${st.estimate.high_usd.toFixed(2)}</>}
          </p>
          {st.pending.length > 0 && (
            <ul className="divide-y divide-line-subtle border-y border-line-subtle" aria-label="Paid requests waiting for approval">
              {st.pending.map((p) => (
                <li key={p.hash} className="flex items-center justify-between gap-3 py-2 text-meta">
                  <span className="min-w-0 truncate text-fg-secondary">{p.generator} · {p.what || p.hash}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="font-mono text-fg-primary">${p.quote_usd.toFixed(2)}</span>
                    <Button
                      busy={busy === p.hash}
                      onClick={async () => {
                        setBusy(p.hash);
                        setErr(null);
                        try {
                          await api.approveSpend(p.hash);
                          q.reload();
                        } catch (e) {
                          setErr(friendlyError(e));
                        } finally {
                          setBusy(null);
                        }
                      }}
                    >
                      Approve
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {err && <Notice tone="error">{err}</Notice>}
        </div>
      )}
    </Panel>
  );
}

/** E2: opt-in browser notifications (this browser only). */
function Notifications() {
  const [on, setOn] = useState(notificationsOn());
  const [msg, setMsg] = useState<string | null>(null);
  const supported = typeof Notification !== "undefined";
  return (
    <Panel title="Notifications">
      <Toggle
        checked={on}
        disabled={!supported}
        onChange={async (v) => {
          const res = await setNotifications(v);
          setOn(res);
          setMsg(v && !res ? "The browser didn’t allow notifications. Allow them for this page in the browser’s site settings." : null);
        }}
        label="Tell me when an edit needs me"
        description={supported ? "A notification when an edit turns Sendable, Hold or Failed, waits for the A/B pick, or a long recording has reels to pick. This browser only." : "This browser has no notifications."}
      />
      {msg && <p className="mt-2 text-label text-st-hold">{msg}</p>}
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
    <div className="w-full px-8 py-8">
      <PageHeader title="Settings" subtitle="Health, AI costs and how the studio runs." />
      <div className="grid grid-cols-12 gap-x-10 gap-y-6">
        <div className="col-span-12 xl:col-span-7">
          <Health />
          <Usage />
        </div>
        <div className="col-span-12 xl:col-span-5">
          <SettingsForm />
          <SpendPanel />
          <Notifications />
          <ProjectActions />
        </div>
      </div>
    </div>
  );
}
