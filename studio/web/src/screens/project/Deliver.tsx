// FR-9 Deliver: package file list, zip download, extra aspect ratios (variants), platform warnings,
// mark delivered (AC-13).
import { useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { PackageFile } from "../../api/types";
import { Icon, type IconName } from "../../components/icons";
import { Button, cx, IconButton, Loading, Mono, Notice, Panel, Select } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { ago, bytes } from "../../lib/format";
import { NotYet, useProject } from "./ProjectLayout";

const KIND_ICON: Record<PackageFile["kind"], IconName> = {
  final: "film",
  variant: "film",
  review_copy: "eye",
  timeline: "layers",
  captions: "edit",
  stems: "music",
  overlay: "layers",
  edit_list: "info",
  other: "folder",
};

const ASPECT: Record<string, string> = { final: "aspect-[9/16]", feed_4x5: "aspect-[4/5]", square: "aspect-square" };

function aspectOf(f: PackageFile) {
  if (f.kind === "final") return ASPECT.final;
  if (f.path.includes("4x5")) return ASPECT.feed_4x5;
  if (f.path.includes("square")) return ASPECT.square;
  return ASPECT.final;
}

const left = (expires: number) => {
  const h = (expires - Date.now() / 1000) / 3600;
  return h >= 48 ? `${Math.round(h / 24)} days` : h >= 1 ? `${Math.round(h)} h` : `${Math.max(1, Math.round(h * 60))} min`;
};

/** FR-9 review link: a private client page with the review copy and a notes box, expiring after a set time. */
function ReviewLinkPanel({ projectId }: { projectId: string }) {
  const api = useApi();
  const q = useQuery(() => api.reviewLinks(projectId), [api, projectId], { intervalMs: 15000 });
  const [hours, setHours] = useState("72");
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const active = (q.data?.links ?? []).filter((l) => l.state === "active");
  const old = (q.data?.links ?? []).length - active.length;

  async function create() {
    setBusy("create");
    setErr(null);
    try {
      const l = await api.createReviewLink(projectId, Number(hours));
      await navigator.clipboard?.writeText(origin + l.path).then(() => setCopied(l.id), () => undefined);
      q.reload();
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }
  async function revoke(id: string) {
    if (!window.confirm("Turn this link off? The client will see “This review link no longer works”.")) return;
    setBusy(id);
    setErr(null);
    try {
      await api.revokeReviewLink(projectId, id);
      q.reload();
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel title="Review link">
      <p className="text-fg-secondary">A private page with the watermarked review copy and a notes box for the client. Their notes arrive in Revise.</p>
      <p className="mt-2 text-meta text-fg-muted">The studio only listens on this Mac, so the link works elsewhere only if you expose it on purpose (for example with a tunnel).</p>
      {q.data && !q.data.ready ? (
        <p className="mt-3 text-meta text-fg-secondary">Available once the edit has rendered. Creating a link makes a small watermarked copy of the reel.</p>
      ) : (
        <div className="mt-4 flex items-end gap-2">
          <div className="w-32">
            <label htmlFor="rl-hours" className="mb-1.5 block text-meta text-fg-secondary">
              Expires after
            </label>
            <Select id="rl-hours" value={hours} onChange={(e) => setHours(e.target.value)}>
              <option value="24">1 day</option>
              <option value="72">3 days</option>
              <option value="168">7 days</option>
              <option value="720">30 days</option>
            </Select>
          </div>
          <Button icon="link" busy={busy === "create"} onClick={create}>
            Create review link
          </Button>
        </div>
      )}
      {active.length > 0 && (
        <ul className="mt-4 divide-y divide-line-subtle border-y border-line-subtle" aria-label="Active review links">
          {active.map((l) => (
            <li key={l.id} className="py-3">
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate font-mono text-mono text-fg-primary" title={origin + l.path}>
                  {origin + l.path}
                </span>
                <IconButton
                  icon={copied === l.id ? "check" : "copy"}
                  label="Copy link"
                  onClick={() => navigator.clipboard?.writeText(origin + l.path).then(() => setCopied(l.id), () => undefined)}
                />
                <a href={l.path} target="_blank" rel="noreferrer" aria-label="Open the client page" title="Open the client page" className="inline-flex h-8 w-8 items-center justify-center rounded-control text-fg-secondary hover:bg-bg-overlay hover:text-fg-primary">
                  <Icon name="eye" size={16} />
                </a>
              </div>
              <div className="mt-1 flex items-center justify-between gap-3 text-meta text-fg-muted">
                <span>
                  Expires in {left(l.expires)} · {l.notes} note{l.notes === 1 ? "" : "s"}
                  {copied === l.id && <span className="text-st-sendable"> · copied</span>}
                </span>
                <button type="button" className="text-fg-secondary hover:text-st-fail disabled:opacity-50" disabled={busy === l.id} onClick={() => revoke(l.id)}>
                  Turn off…
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {old > 0 && <p className="mt-3 text-meta text-fg-muted">{old} expired or turned-off link{old === 1 ? "" : "s"}.</p>}
      {err || q.error ? (
        <div className="mt-3">
          <Notice tone="error">{err ?? friendlyError(q.error)}</Notice>
        </div>
      ) : null}
    </Panel>
  );
}

export default function Deliver() {
  const { project: p, reload } = useProject();
  const api = useApi();
  const pkg = useQuery(() => api.packageListing(p.id), [api, p.id, p.versions.length]);
  const settings = useQuery(() => api.settings(), [api]);
  const [copied, setCopied] = useState<string | null>(null);
  const [variants, setVariants] = useState<string[]>(((p.brief?.deliverables as string[] | undefined) ?? []).slice());
  const [busy, setBusy] = useState<"variants" | "delivered" | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  if (p.verdict !== "sendable" && p.verdict !== "hold") return <NotYet what="deliver" icon="download" opens="The package (reel, versions, captions, timeline) appears here when the edit has finished." />;

  const root = settings.data ? `${settings.data.projects_dir.replace(/\/$/, "")}/${p.id}` : null;
  const fullPath = (f: PackageFile) => (root ? `${root}/${f.path}` : f.path);
  async function copy(f: PackageFile) {
    try {
      await navigator.clipboard.writeText(fullPath(f));
      setCopied(f.path);
      setTimeout(() => setCopied(null), 1600);
    } catch {
      setMsg({ tone: "error", text: "The browser blocked clipboard access. Select the path and copy it instead." });
    }
  }
  async function run(kind: "variants" | "delivered") {
    setBusy(kind);
    setMsg(null);
    try {
      if (kind === "variants") {
        await api.deliver(p.id, variants);
        setMsg({ tone: "ok", text: "Making the extra versions — they’ll appear in the list when ready." });
      } else {
        await api.markDelivered(p.id);
        reload();
        setMsg({ tone: "ok", text: "Marked as delivered. It moves down the home list." });
      }
    } catch (e) {
      setMsg({ tone: "error", text: friendlyError(e) });
    } finally {
      setBusy(null);
    }
  }

  const zip = api.packageZipUrl(p.id);
  const pictures = (pkg.data?.files ?? []).filter((f) => f.kind === "final" || f.kind === "variant");
  const rest = (pkg.data?.files ?? []).filter((f) => f.kind !== "final" && f.kind !== "variant");

  return (
    <div className="grid grid-cols-12 gap-x-10 gap-y-6">
      <div className="col-span-12 space-y-4 xl:col-span-8">
        {p.verdict === "hold" && (
          <Notice tone="warn" title="This reel is on Hold">
            You can still download it, but the tool doesn’t think it’s safe to send yet.
          </Notice>
        )}
        {pkg.data?.warnings.map((w) => (
          <Notice key={w} tone="warn" title="Platform note">
            {w}
          </Notice>
        ))}
        <Panel
          title="The reel"
          actions={
            zip ? (
              <a href={zip} download className="inline-flex h-9 items-center gap-2 rounded-control bg-signal px-4 text-ui text-signal-on hover:bg-signal-hover">
                <Icon name="download" size={16} /> Download all (.zip)
              </a>
            ) : (
              <Button icon="download" disabled title="Available with the engine running">
                Download all (.zip)
              </Button>
            )
          }
        >
          {pkg.loading && !pkg.data ? (
            <Loading />
          ) : pkg.error ? (
            <Notice tone="error">{friendlyError(pkg.error)}</Notice>
          ) : (
            pictures.length === 0 ? (
              <p className="py-6 text-fg-secondary">No rendered files in the package yet. If the edit just finished, they appear in a moment; otherwise run the edit again from Live.</p>
            ) : (
            <ul className="grid grid-cols-3 gap-6">
              {pictures.map((f) => (
                <li key={f.path} className="flex flex-col gap-2">
                  <div className="flex h-56 items-end justify-center rounded-surface bg-bg-inset p-3">
                    <div className={cx("h-full max-w-full overflow-hidden rounded-control bg-bg-high ring-1 ring-line-strong", aspectOf(f))}>
                      {f.thumb && <img src={api.mediaUrl(p.id, f.thumb, p.updated)} alt="" className="h-full w-full object-cover" />}
                    </div>
                  </div>
                  <p className="text-ui text-fg-primary">{f.label}</p>
                  <div className="flex items-center gap-1">
                    <Mono className="text-fg-muted">{bytes(f.bytes)}</Mono>
                    <span className="ml-auto flex gap-1">
                      <IconButton icon={copied === f.path ? "check" : "copy"} label={`Copy path of ${f.label}`} onClick={() => copy(f)} />
                      {api.mediaUrl(p.id, f.path, p.updated) && (
                        <a href={api.mediaUrl(p.id, f.path, p.updated)} download aria-label={`Download ${f.label}`} title="Download" className="inline-flex h-8 w-8 items-center justify-center rounded-control text-fg-secondary hover:bg-bg-overlay hover:text-fg-primary">
                          <Icon name="download" size={16} />
                        </a>
                      )}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            )
          )}
        </Panel>
        <Panel title="For editing software" actions={<span className="text-meta text-fg-muted">Final Cut Pro · OpenTimelineIO · captions · stems</span>}>
          <ul className="divide-y divide-line-subtle">
            {rest.map((f) => (
              <li key={f.path} className="flex items-center gap-3 py-2.5">
                <Icon name={KIND_ICON[f.kind]} size={18} className="shrink-0 text-fg-muted" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-fg-primary">{f.label}</p>
                  <Mono className="block truncate text-fg-muted">{f.path}</Mono>
                </div>
                <Mono className="shrink-0 text-fg-muted">{bytes(f.bytes)}</Mono>
                <IconButton icon={copied === f.path ? "check" : "copy"} label={`Copy path of ${f.label}`} onClick={() => copy(f)} />
              </li>
            ))}
          </ul>
          {root && (
            <p className="mt-3 text-meta text-fg-muted">
              Package folder: <Mono className="text-fg-secondary">{root}/export/package</Mono>
            </p>
          )}
        </Panel>
      </div>

      <div className="col-span-12 xl:col-span-4">
        <Panel title="Extra versions">
          <p className="mb-3 text-fg-secondary">The 9:16 master is always made. Add feed and square versions for other placements.</p>
          {(
            [
              ["feed_4x5", "4:5 feed"],
              ["square", "Square 1:1"],
            ] as const
          ).map(([id, label]) => (
            <label key={id} className="flex cursor-pointer items-center gap-2 py-1">
              <input type="checkbox" className="h-4 w-4 accent-[#F2A93B]" checked={variants.includes(id)} onChange={(e) => setVariants((v) => (e.target.checked ? [...v, id] : v.filter((x) => x !== id)))} />
              {label}
            </label>
          ))}
          <Button className="mt-3" icon="film" busy={busy === "variants"} disabled={!variants.length} onClick={() => run("variants")}>
            Make versions
          </Button>
        </Panel>
        <Panel title="Hand-off">
          {p.delivered_at ? (
            <p className="flex items-center gap-2 text-st-sendable">
              <Icon name="check" size={16} /> Delivered {ago(p.delivered_at)}
            </p>
          ) : (
            <>
              <p className="mb-3 text-fg-secondary">Once you’ve sent the files, mark it delivered. It records the date and moves the project down the home list.</p>
              <Button icon="check" busy={busy === "delivered"} onClick={() => run("delivered")}>
                Mark delivered
              </Button>
            </>
          )}
        </Panel>
        <ReviewLinkPanel projectId={p.id} />

        {msg && <Notice tone={msg.tone === "ok" ? "ok" : "error"}>{msg.text}</Notice>}
      </div>
    </div>
  );
}
