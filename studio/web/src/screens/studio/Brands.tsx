// FR-10 Brand kits: client, colours, heading font, logo, locked caption style and look, with a live
// caption preview of the brand applied (AC-14).
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../../api/context";
import { friendlyError } from "../../api/errors";
import type { Brand, BrandEntry } from "../../api/types";
import { PageHeader } from "../../components/Shell";
import { Button, cx, Field, Loading, Notice, Panel, Select, TextInput } from "../../components/ui";
import { useQuery } from "../../hooks/useQuery";
import { LOOKS } from "../../lib/adjust";
import { prettyId } from "../../lib/format";

const FONTS = ["Inter", "Plus Jakarta Sans", "Montserrat", "Poppins", "Playfair Display", "DM Serif Display"];
const FAMILIES = ["bold_pop", "clean_phrase", "editorial_kinetic", "minimal_calm", "speaker_coded"];
const COLOR_KEYS = [
  ["primary", "Primary"],
  ["secondary", "Secondary"],
  ["accent", "Accent (caption emphasis)"],
  ["text", "Caption text"],
] as const;

const blank = (): Brand => ({ client: "", fonts: { heading: "Inter" }, colors: { primary: "#1A1E27", accent: "#FF5FA2", text: "#FFFFFF" }, logo: null, caption_family: null, caption_tokens: {}, look: null });
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const isHex = (s: string | null | undefined) => !!s && /^#[0-9a-fA-F]{6}$/.test(s);

function CaptionPreview({ b }: { b: Brand }) {
  const text = isHex(b.colors.text) ? b.colors.text! : "#FFFFFF";
  const accent = isHex(b.colors.accent) ? b.colors.accent! : isHex(b.colors.primary) ? b.colors.primary! : "#FFD400";
  const font = b.fonts.heading || "Inter";
  return (
    <div className="mx-auto aspect-[9/16] w-full max-w-[260px] overflow-hidden rounded-[22px] border-4 border-bg-high bg-[linear-gradient(160deg,#3a2a2f,#141018)] ring-1 ring-line-strong">
      <div className="relative h-full">
        <div className="absolute left-1/2 top-[22%] h-[30%] w-[46%] -translate-x-1/2 rounded-[45%] bg-[#c99a86]/80" aria-hidden="true" />
        <div className="absolute bottom-0 left-1/2 h-[28%] w-[86%] -translate-x-1/2 rounded-t-[50%] bg-[#6b4a52]" aria-hidden="true" />
        {b.logo && <div className="absolute right-3 top-3 rounded bg-white/85 px-1.5 py-0.5 text-[9px] font-bold text-black">LOGO</div>}
        <p className="absolute inset-x-3 bottom-[24%] text-center text-[19px] font-bold leading-tight" style={{ fontFamily: `"${font}", Inter, system-ui, sans-serif`, color: text, textShadow: "0 2px 8px rgba(0,0,0,0.7)" }}>
          Ten days <span style={{ color: accent }}>later</span> my skin felt <span style={{ color: accent }}>calm</span>
        </p>
        <div className="absolute inset-x-6 bottom-[8%] rounded-md py-1.5 text-center text-[11px] font-semibold" style={{ background: isHex(b.colors.primary) ? b.colors.primary! : "#000", color: text }}>
          Link in bio
        </div>
      </div>
    </div>
  );
}

function Editor({ entry, isNew, onSaved }: { entry: BrandEntry; isNew: boolean; onSaved: (id: string) => void }) {
  const api = useApi();
  const [b, setB] = useState<Brand>(entry.brand);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  useEffect(() => {
    setB(entry.brand);
    setMsg(null);
  }, [entry]);
  const id = isNew ? slug(b.client) : entry.id;

  return (
    <div className="grid grid-cols-12 gap-x-10 gap-y-6">
      <Panel title={isNew ? "New brand kit" : b.client} className="col-span-12 lg:col-span-7">
        <form
          className="grid grid-cols-2 gap-x-4 gap-y-5"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setMsg(null);
            try {
              await api.saveBrand(id, b, isNew);
              setMsg({ tone: "ok", text: "Saved. New edits for this client use it." });
              onSaved(id);
            } catch (err) {
              setMsg({ tone: "error", text: friendlyError(err) });
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="col-span-2">
            <Field label="Client name *" htmlFor="b-client" hint={isNew && b.client ? `Saved as brands/${id}.json` : undefined}>
              <TextInput id="b-client" value={b.client} onChange={(e) => setB({ ...b, client: e.target.value })} required />
            </Field>
          </div>
          {COLOR_KEYS.map(([k, label]) => (
            <Field key={k} label={label} htmlFor={`b-${k}`}>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  aria-label={`${label} picker`}
                  value={isHex(b.colors[k]) ? b.colors[k]! : "#000000"}
                  onChange={(e) => setB({ ...b, colors: { ...b.colors, [k]: e.target.value.toUpperCase() } })}
                  className="h-10 w-12 shrink-0 cursor-pointer rounded-control border border-line-control bg-bg-overlay p-1"
                />
                <TextInput id={`b-${k}`} value={b.colors[k] ?? ""} placeholder="#RRGGBB" onChange={(e) => setB({ ...b, colors: { ...b.colors, [k]: e.target.value || null } })} className={cx("font-mono text-mono", b.colors[k] && !isHex(b.colors[k]) && "border-st-fail")} />
              </div>
            </Field>
          ))}
          <Field label="Heading font" htmlFor="b-font">
            <Select id="b-font" value={b.fonts.heading ?? "Inter"} onChange={(e) => setB({ ...b, fonts: { ...b.fonts, heading: e.target.value } })}>
              {FONTS.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </Select>
          </Field>
          <Field label="Logo file" htmlFor="b-logo" hint="Path on this Mac (PNG with transparency).">
            <TextInput id="b-logo" value={b.logo ?? ""} onChange={(e) => setB({ ...b, logo: e.target.value || null })} placeholder="brands/client/logo.png" />
          </Field>
          <Field label="Locked caption style" htmlFor="b-family" hint="The Editor must use it.">
            <Select id="b-family" value={b.caption_family ?? ""} onChange={(e) => setB({ ...b, caption_family: e.target.value || null })}>
              <option value="">Editor chooses</option>
              {FAMILIES.map((f) => (
                <option key={f} value={f}>
                  {prettyId(f)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Locked colour look" htmlFor="b-look">
            <Select id="b-look" value={b.look ?? ""} onChange={(e) => setB({ ...b, look: e.target.value || null })}>
              <option value="">Editor chooses</option>
              {LOOKS.map((l) => (
                <option key={l.id} value={l.id}>
                  {prettyId(l.id)} — {l.note}
                </option>
              ))}
            </Select>
          </Field>
          <div className="col-span-2 flex items-center gap-3">
            <Button type="submit" variant="primary" busy={busy} disabled={!b.client.trim() || COLOR_KEYS.some(([k]) => b.colors[k] && !isHex(b.colors[k]))}>
              Save brand kit
            </Button>
            {msg && <span className={cx("text-label", msg.tone === "ok" ? "text-st-sendable" : "text-st-fail")}>{msg.text}</span>}
          </div>
        </form>
      </Panel>
      <Panel title="Live caption preview" className="col-span-12 lg:col-span-5">
        <CaptionPreview b={b} />
      </Panel>
    </div>
  );
}

export default function Brands() {
  const api = useApi();
  const q = useQuery(() => api.brands(), [api]);
  const [sel, setSel] = useState<string | "new" | null>(null);
  const list = q.data ?? [];
  const fresh = useMemo<BrandEntry>(() => ({ id: "", brand: blank() }), [sel]);
  const current = sel === "new" || !list.length ? fresh : list.find((b) => b.id === sel) ?? list[0];
  const isNew = sel === "new" || (!list.length && !!q.data);

  return (
    <div className="w-full px-8 py-8">
      <PageHeader title="Brand kits" subtitle="Lock a client’s colours, font, caption style and look." actions={<Button icon="plus" onClick={() => setSel("new")}>New brand kit</Button>} />
      {q.error ? <Notice tone="error">{friendlyError(q.error)}</Notice> : null}
      {!q.data ? (
        <Loading />
      ) : (
        <div className="grid grid-cols-12 gap-x-10 gap-y-6">
          <nav aria-label="Brand kits" className="col-span-12 lg:col-span-3">
            <ul className="space-y-1">
              {list.map((b) => (
                <li key={b.id}>
                  <button
                    type="button"
                    onClick={() => setSel(b.id)}
                    aria-current={current?.id === b.id && !isNew ? "true" : undefined}
                    className={cx("flex w-full items-center gap-3 rounded-control px-3 py-2.5 text-left text-ui transition-colors", current?.id === b.id && !isNew ? "bg-bg-overlay text-fg-primary" : "text-fg-secondary hover:bg-bg-raised")}
                  >
                    <span className="flex -space-x-1" aria-hidden="true">
                      {[b.brand.colors.primary, b.brand.colors.accent, b.brand.colors.text].filter(Boolean).map((c, i) => (
                        <span key={i} className="h-4 w-4 rounded-full border border-bg-base" style={{ background: c! }} />
                      ))}
                    </span>
                    <span className="truncate">{b.brand.client}</span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <div className="col-span-12 lg:col-span-9">
            {current && (
              <Editor
                entry={current}
                isNew={isNew}
                onSaved={(id) => {
                  q.reload();
                  setSel(id);
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
