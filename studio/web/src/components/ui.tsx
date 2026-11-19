import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Icon, type IconName } from "./icons";
import type { Badge } from "../lib/status";
import { STAGE_LABEL } from "../lib/status";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variant = "primary" | "secondary" | "ghost" | "danger";
// Cutting Room: one amber primary per screen; everything else is graphite.
const VARIANT: Record<Variant, string> = {
  primary: "bg-signal text-signal-on border border-transparent shadow-[0_6px_24px_-8px_rgba(242,169,59,0.75)] hover:bg-signal-hover hover:shadow-[0_8px_28px_-6px_rgba(242,169,59,0.85)] active:bg-signal-pressed",
  secondary: "bg-bg-overlay text-fg-primary border border-line-strong hover:bg-bg-high hover:border-line-control",
  ghost: "bg-transparent text-fg-primary border border-transparent hover:bg-bg-overlay",
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
        "inline-flex items-center justify-center gap-2 rounded-control font-medium whitespace-nowrap transition-[background-color,border-color,color] duration-hover ease-std",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        size === 40 ? "h-10 px-4 text-body font-medium" : "h-9 px-4 text-ui",
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
        "inline-flex h-8 w-8 items-center justify-center rounded-control text-fg-secondary hover:bg-bg-overlay hover:text-fg-primary transition-colors duration-hover disabled:opacity-40",
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

const BADGE: Record<Badge, { label: string; color: string }> = {
  hold: { label: "Hold", color: "text-st-hold" },
  failed: { label: "Failed", color: "text-st-fail" },
  sendable: { label: "Sendable", color: "text-st-sendable" },
  editing: { label: "Editing", color: "text-ai" },
  queued: { label: "Queued", color: "text-fg-secondary" },
  delivered: { label: "Delivered", color: "text-fg-secondary" },
  draft: { label: "Draft", color: "text-fg-secondary" },
};
const DOT: Record<Badge, string> = {
  hold: "bg-st-hold",
  failed: "bg-st-fail",
  sendable: "bg-st-sendable",
  editing: "bg-ai",
  queued: "bg-st-queued",
  delivered: "bg-fg-muted",
  draft: "bg-st-queued",
};

/** Status: a dot plus a coloured label, no chip (Cutting Room). Colour is never the only cue. */
export function StatusBadge({ badge, stage, count, size = "md" }: { badge: Badge; stage?: string | null; count?: number; size?: "md" | "lg" }) {
  const b = BADGE[badge];
  let label = b.label;
  if (badge === "editing" && stage) label = `Editing · ${STAGE_LABEL[stage] ?? stage}`;
  if (badge === "hold" && count) label = `Hold · ${count}`;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-2 font-medium whitespace-nowrap",
        size === "lg" ? "h-8 text-ui" : "h-6 text-label",
        b.color,
      )}
    >
      <span className={cx("h-2 w-2 rounded-full [box-shadow:0_0_10px_1px_currentColor]", DOT[badge], badge === "editing" && "pulse-dot")} aria-hidden="true" />
      {label}
    </span>
  );
}

export function Panel({ title, actions, children, className, bodyClass, as: As = "section" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; as?: "section" | "div" | "aside" }) {
  return (
    // Cutting Room: no cards. A section is docked under a 1 px hairline; grouping comes from space and type.
    // The first section in a column sits right under the screen header's hairline, so it drops its own.
    <As className={cx("border-t border-line-subtle first:border-t-0 first:[&>header]:pt-0 first:[&>div:only-child]:pt-0", className)}>
      {(title || actions) && (
        <header className="flex min-h-8 items-center justify-between gap-4 pt-5">
          {/* Text titles are headings; a control passed as the title (e.g. a tab switch) is not. */}
          {typeof title === "string" || (title && typeof title === "object" && "type" in title && title.type === "span") ? (
            <h2 className="text-section text-fg-primary">{title}</h2>
          ) : title ? (
            <div>{title}</div>
          ) : (
            <span />
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("pb-6", title || actions ? "pt-4" : "pt-5", bodyClass)}>{children}</div>
    </As>
  );
}

export function Field({ label, hint, children, error, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; error?: string | null; htmlFor?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-meta text-fg-secondary">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-meta text-st-fail" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-meta text-fg-muted">{hint}</p>
      ) : null}
    </div>
  );
}

const inputCls =
  // Border is line/control: ≥ 3:1 against every surface (WCAG 1.4.11).
  "w-full rounded-control border border-line-control bg-bg-overlay px-3 text-body text-fg-primary placeholder:text-fg-muted transition-colors duration-hover hover:border-fg-muted focus:border-signal focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-signal read-only:border-line-strong read-only:text-fg-secondary disabled:opacity-60";

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput({ className, ...rest }, ref) {
  return <input ref={ref} className={cx(inputCls, "h-9", className)} {...rest} />;
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cx(inputCls, "py-2.5 min-h-[88px] resize-y leading-5", className)} {...rest} />;
});

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select className={cx(inputCls, "h-9 appearance-none pr-9", className)} {...rest}>
        {children}
      </select>
      <Icon name="chevronDown" size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-fg-muted" />
    </div>
  );
}

export function Toggle({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string; disabled?: boolean }) {
  const id = useId();
  return (
    <div className="flex items-start gap-3">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative mt-0.5 h-5 w-9 shrink-0 rounded-full border transition-colors duration-hover",
          checked ? "bg-signal border-signal" : "bg-bg-overlay border-line-control",
          disabled && "opacity-50",
        )}
      >
        <span className={cx("absolute left-0 top-0.5 h-3.5 w-3.5 rounded-full transition-transform duration-hover ease-std", checked ? "translate-x-[18px] bg-signal-on" : "translate-x-0.5 bg-fg-muted")} />
      </button>
      <div className="min-w-0">
        <label htmlFor={id} className="cursor-pointer text-body text-fg-primary">
          {label}
        </label>
        {description && <p className="text-meta text-fg-muted">{description}</p>}
      </div>
    </div>
  );
}

export function Notice({ tone = "info", title, children, action }: { tone?: "info" | "error" | "warn" | "ok"; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  const t = {
    info: { c: "border-l-line-control", i: "info" as const, ic: "text-info" },
    error: { c: "border-l-st-fail", i: "alert" as const, ic: "text-st-fail" },
    warn: { c: "border-l-st-hold", i: "alert" as const, ic: "text-st-hold" },
    ok: { c: "border-l-st-sendable", i: "check" as const, ic: "text-st-sendable" },
  }[tone];
  return (
    // Flat: a surface with a 2 px status rule on the left, no tinted card.
    <div className={cx("flex items-start gap-3 rounded-control border-l-2 bg-bg-raised px-4 py-3", t.c)} role={tone === "error" ? "alert" : "status"}>
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
  const color = tone === "ok" ? "bg-st-sendable" : tone === "fail" ? "bg-st-fail" : "bg-ai";
  return (
    <div className="relative h-1 w-full overflow-hidden rounded-full bg-bg-high" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value === null ? undefined : Math.round(value * 100)}>
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
    <div className="mx-auto flex max-w-[480px] flex-col items-start gap-3 px-6 py-16">
      <Icon name={icon} size={24} className="text-fg-muted" />
      <h3 className="mt-2 text-title">{title}</h3>
      {children && <div className="text-fg-secondary">{children}</div>}
      {action && <div className="mt-3">{action}</div>}
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
  return <kbd className="rounded-control border border-line-strong bg-bg-overlay px-1.5 py-0.5 font-mono text-meta text-fg-secondary">{children}</kbd>;
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex self-start rounded-control border border-line-control bg-bg-overlay p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            // 3 px inner radius: concentric inside the 4 px control.
            "h-7 rounded-[3px] px-3 text-ui transition-colors duration-hover",
            value === o.value ? "bg-bg-high text-fg-primary" : "text-fg-secondary hover:text-fg-primary",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
