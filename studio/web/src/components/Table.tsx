import type { ReactNode } from "react";
import { cx } from "./ui";

export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  className?: string;
  align?: "left" | "right";
}

export function Table<T>({ rows, columns, rowKey, caption, empty }: { rows: T[]; columns: Column<T>[]; rowKey: (r: T) => string; caption: string; empty?: ReactNode }) {
  if (!rows.length) return <p className="py-6 text-fg-secondary">{empty ?? "Nothing here yet."}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line-subtle">
            {columns.map((c) => (
              <th key={c.key} scope="col" className={cx("px-3 py-2 text-label text-fg-muted", c.align === "right" && "text-right", c.className)}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} className="border-b border-line-subtle/70 last:border-0 hover:bg-bg-overlay/40">
              {columns.map((c) => (
                <td key={c.key} className={cx("px-3 py-2.5 align-middle", c.align === "right" && "text-right", c.className)}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
