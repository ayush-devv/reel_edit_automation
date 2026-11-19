// FR-9 Deliver: package file list, zip download, extra aspect ratios (variants), platform warnings,
// mark delivered (AC-13).
import { useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { PackageFile } from "../../api/types";
import { Icon, type IconName } from "../../components/icons";
import { Button, cx, IconButton, Loading, Mono, Notice, Panel } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { ago, bytes } from "../../lib/format";
import { useProject } from "./ProjectLayout";

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

export default function Deliver() {
  const { project: p, reload } = useProject();
  const api = useApi();
  const pkg = useQuery(() => api.packageListing(p.id), [api, p.id, p.versions.length]);
  const settings = useQuery(() => api.settings(), [api]);
  const [copied, setCopied] = useState<string | null>(null);
  const [variants, setVariants] = useState<string[]>(((p.brief?.deliverables as string[] | undefined) ?? []).slice());
  const [busy, setBusy] = useState<"variants" | "delivered" | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  if (p.verdict !== "sendable" && p.verdict !== "hold") return <Notice title="Nothing to deliver yet">Delivery opens when the edit has finished.</Notice>;

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
    <div className="grid grid-cols-12 gap-4">
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
              <a href={zip} download className="inline-flex h-8 items-center gap-2 rounded-input bg-ai px-3 text-[13px] font-medium text-white hover:brightness-110">
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
            <ul className="grid grid-cols-3 gap-4">
              {pictures.map((f) => (
                <li key={f.path} className="flex flex-col gap-2">
                  <div className="flex h-56 items-end justify-center rounded-card bg-bg-inset p-3">
                    <div className={cx("h-full max-w-full overflow-hidden rounded-[6px] border border-line-strong bg-[linear-gradient(160deg,#3a2a2f,#141018)]", aspectOf(f))}>
                      {f.thumb && <img src={api.mediaUrl(p.id, f.thumb, p.updated)} alt="" className="h-full w-full object-cover" />}
                    </div>
                  </div>
                  <p className="font-medium text-fg-primary">{f.label}</p>
                  <div className="flex items-center gap-1">
                    <Mono className="text-fg-muted">{bytes(f.bytes)}</Mono>
                    <span className="ml-auto flex gap-1">
                      <IconButton icon={copied === f.path ? "check" : "copy"} label={`Copy path of ${f.label}`} onClick={() => copy(f)} />
                      {api.mediaUrl(p.id, f.path, p.updated) && (
                        <a href={api.mediaUrl(p.id, f.path, p.updated)} download aria-label={`Download ${f.label}`} title="Download" className="inline-flex h-8 w-8 items-center justify-center rounded-input text-fg-secondary hover:bg-bg-overlay hover:text-fg-primary">
                          <Icon name="download" size={16} />
                        </a>
                      )}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="For editing software" actions={<span className="text-label font-normal text-fg-muted">Final Cut Pro · OpenTimelineIO · captions · stems</span>}>
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
            <p className="mt-3 text-label font-normal text-fg-muted">
              Package folder: <Mono className="text-fg-secondary">{root}/export/package</Mono>
            </p>
          )}
        </Panel>
      </div>

      <div className="col-span-12 space-y-4 xl:col-span-4">
        <Panel title="Extra versions">
          <p className="mb-3 text-fg-secondary">The 9:16 master is always made. Add feed and square versions for other placements.</p>
          {(
            [
              ["feed_4x5", "4:5 feed"],
              ["square", "Square 1:1"],
            ] as const
          ).map(([id, label]) => (
            <label key={id} className="flex cursor-pointer items-center gap-2 py-1">
              <input type="checkbox" className="h-4 w-4 accent-[#6A4BF0]" checked={variants.includes(id)} onChange={(e) => setVariants((v) => (e.target.checked ? [...v, id] : v.filter((x) => x !== id)))} />
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
              <Button variant="primary" icon="check" busy={busy === "delivered"} onClick={() => run("delivered")}>
                Mark delivered
              </Button>
            </>
          )}
        </Panel>
        <Panel title="Review link">
          <p className="text-fg-secondary">A private page with the review copy and a notes box for the client, expiring after a time you choose.</p>
          <p className="mt-2 text-label font-normal text-fg-muted">It’s only reachable from outside this Mac if you expose it on purpose (for example with a tunnel). Not available in this version yet.</p>
          <Button className="mt-3" icon="link" disabled>
            Create review link
          </Button>
        </Panel>
        {msg && <Notice tone={msg.tone === "ok" ? "ok" : "error"}>{msg.text}</Notice>}
      </div>
    </div>
  );
}
