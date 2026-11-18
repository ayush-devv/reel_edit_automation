import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Icon, type IconName } from "./icons";
import type { Badge } from "../lib/status";
import { STAGE_LABEL } from "../lib/status";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANT: Record<Variant, string> = {
  primary: "bg-ai text-white hover:brightness-110 border border-transparent",
  secondary: "bg-transparent text-fg-primary border border-line-strong hover:border-ai-glow hover:text-white",
  ghost: "bg-transparent text-fg-secondary border border-transparent hover:bg-bg-overlay hover:text-fg-primary",
  danger: "bg-transparent text-st-fail border border-st-fail/60 hover:bg-st-fail/10",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: 32 | 40;
  icon?: IconName;
  busy?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = 32, icon, busy, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-input font-medium whitespace-nowrap transition-[filter,background-color,border-color,color] duration-hover ease-std",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        size === 40 ? "h-10 px-4 text-body" : "h-8 px-3 text-[13px]",
        VARIANT[variant],
        className,
      )}
      {...rest}
    >
      {busy ? <Spinner size={14} /> : icon ? <Icon name={icon} size={size === 40 ? 18 : 16} /> : null}
      {children}
    </button>
  );
});

export function IconButton({ icon, label, className, ...rest }: Omit<ButtonProps, "children"> & { icon: IconName; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        "inline-flex h-8 w-8 items-center justify-center rounded-input text-fg-secondary hover:bg-bg-overlay hover:text-fg-primary transition-colors duration-hover disabled:opacity-40",
        className,
      )}
      {...rest}
    >
      <Icon name={icon} size={16} />
    </button>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="animate-spin" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

const BADGE: Record<Badge, { label: string; color: string; bg: string }> = {
  hold: { label: "Hold", color: "text-st-hold", bg: "bg-st-hold/[0.12]" },
  failed: { label: "Failed", color: "text-st-fail", bg: "bg-st-fail/[0.12]" },
  sendable: { label: "Sendable", color: "text-st-sendable", bg: "bg-st-sendable/[0.12]" },
  editing: { label: "Editing", color: "text-ai-glow", bg: "bg-ai/[0.16]" },
  queued: { label: "Queued", color: "text-fg-secondary", bg: "bg-st-queued/[0.12]" },
  delivered: { label: "Delivered", color: "text-fg-secondary", bg: "bg-fg-secondary/[0.10]" },
  draft: { label: "Draft", color: "text-fg-secondary", bg: "bg-st-queued/[0.12]" },
};
const DOT: Record<Badge, string> = {
  hold: "bg-st-hold",
  failed: "bg-st-fail",
  sendable: "bg-st-sendable",
  editing: "bg-ai-glow",
  queued: "bg-st-queued",
  delivered: "bg-fg-muted",
  draft: "bg-st-queued",
};

/** Status badge: a dot plus a label on a 12 % tint (design system). */
export function StatusBadge({ badge, stage, count, size = "md" }: { badge: Badge; stage?: string | null; count?: number; size?: "md" | "lg" }) {
  const b = BADGE[badge];
  let label = b.label;
  if (badge === "editing" && stage) label = `Editing · ${STAGE_LABEL[stage] ?? stage}`;
  if (badge === "hold" && count) label = `Hold · ${count}`;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full font-medium tracking-[0.02em] whitespace-nowrap",
        size === "lg" ? "h-8 px-3 text-body" : "h-6 px-2.5 text-label",
        b.color,
        b.bg,
      )}
    >
      <span className={cx("h-1.5 w-1.5 rounded-full", DOT[badge], badge === "editing" && "pulse-dot")} aria-hidden="true" />
      {label}
    </span>
  );
}

export function Panel({ title, actions, children, className, bodyClass, as: As = "section" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; as?: "section" | "div" | "aside" }) {
  return (
    <As className={cx("rounded-panel border border-line-subtle bg-bg-raised", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-4 px-6 pt-5">
          {title ? <h2 className="text-title text-fg-primary">{title}</h2> : <span />}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-6", title || actions ? "pt-4" : "", bodyClass)}>{children}</div>
    </As>
  );
}

export function Field({ label, hint, children, error, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; error?: string | null; htmlFor?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-label text-fg-secondary">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-label text-st-fail" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-label text-fg-muted font-normal">{hint}</p>
      ) : null}
    </div>
  );
}

const inputCls =
  "w-full rounded-input border border-line-subtle bg-bg-overlay px-3 text-body text-fg-primary placeholder:text-fg-muted transition-colors duration-hover hover:border-line-strong focus:border-ai focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ai disabled:opacity-60";

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput({ className, ...rest }, ref) {
  return <input ref={ref} className={cx(inputCls, "h-10", className)} {...rest} />;
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cx(inputCls, "py-2.5 min-h-[88px] resize-y leading-5", className)} {...rest} />;
});

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select className={cx(inputCls, "h-10 appearance-none pr-9", className)} {...rest}>
        {children}
      </select>
      <Icon name="chevronDown" size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-fg-muted" />
    </div>
  );
}

export function Toggle({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string; disabled?: boolean }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={id} className="text-body text-fg-primary">
          {label}
        </label>
        {description && <p className="text-label font-normal text-fg-muted">{description}</p>}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative mt-0.5 h-5 w-9 shrink-0 rounded-full border transition-colors duration-hover",
          checked ? "bg-ai border-ai" : "bg-bg-overlay border-line-strong",
          disabled && "opacity-50",
        )}
      >
        <span className={cx("absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-transform duration-hover ease-std", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
      </button>
    </div>
  );
}

export function Notice({ tone = "info", title, children, action }: { tone?: "info" | "error" | "warn" | "ok"; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  const t = {
    info: { c: "border-line-strong bg-bg-overlay", i: "info" as const, ic: "text-ai-glow" },
    error: { c: "border-st-fail/50 bg-st-fail/[0.08]", i: "alert" as const, ic: "text-st-fail" },
    warn: { c: "border-st-hold/50 bg-st-hold/[0.08]", i: "alert" as const, ic: "text-st-hold" },
    ok: { c: "border-st-sendable/50 bg-st-sendable/[0.08]", i: "check" as const, ic: "text-st-sendable" },
  }[tone];
  return (
    <div className={cx("flex items-start gap-3 rounded-card border px-4 py-3", t.c)} role={tone === "error" ? "alert" : "status"}>
      <Icon name={t.i} size={18} className={cx("mt-0.5 shrink-0", t.ic)} />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium text-fg-primary">{title}</p>}
        {children && <div className="text-fg-secondary">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ProgressBar({ value, label, tone = "ai" }: { value: number | null; label: string; tone?: "ai" | "ok" | "fail" }) {
  const color = tone === "ok" ? "bg-st-sendable" : tone === "fail" ? "bg-st-fail" : "bg-ai-glow";
  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-bg-overlay" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value === null ? undefined : Math.round(value * 100)}>
      {value === null ? (
        <div className={cx("indeterminate absolute inset-y-0 w-2/5 rounded-full", color)} />
      ) : (
        <div className={cx("h-full rounded-full transition-[width] duration-panel ease-std", color)} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      )}
    </div>
  );
}

export function Empty({ icon, title, children, action }: { icon: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-card border border-line-subtle bg-bg-overlay text-ai-glow">
        <Icon name={icon} size={22} />
      </div>
      <h3 className="text-title">{title}</h3>
      {children && <div className="max-w-md text-fg-secondary">{children}</div>}
      {action}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 px-2 py-8 text-fg-secondary" role="status">
      <Spinner /> {label}
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-mono tabular", className)}>{children}</span>;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-line-strong bg-bg-overlay px-1.5 py-0.5 font-mono text-[11px] text-fg-secondary">{children}</kbd>;
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-input border border-line-subtle bg-bg-overlay p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "h-7 rounded-[5px] px-3 text-[13px] font-medium transition-colors duration-hover",
            value === o.value ? "bg-bg-raised text-fg-primary shadow-[inset_0_0_0_1px_theme(colors.line.strong)]" : "text-fg-secondary hover:text-fg-primary",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
