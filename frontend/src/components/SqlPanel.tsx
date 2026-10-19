import { useState } from "react";
import { ChevronRight, Code2, Copy, Check } from "lucide-react";
import type { QueryData } from "@/lib/api";

const PREVIEW_ROWS = 10;

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Collapsible panel with the generated SQL, its explanation and a preview of the rows. */
const SqlPanel = ({ query }: { query: QueryData }) => {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(query.sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const rowsLabel = `${query.row_count} row${query.row_count === 1 ? "" : "s"}${query.truncated ? " (truncated)" : ""}`;

  return (
    <div className="mt-2 rounded-xl border border-border bg-card text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`} />
        <Code2 className="h-3.5 w-3.5" />
        <span className="font-medium">{open ? "Hide SQL" : "Show SQL"}</span>
        <span className="ml-auto">{rowsLabel}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-border px-3 py-3">
          {query.explanation && <p className="text-muted-foreground">{query.explanation}</p>}

          <div className="relative">
            <pre className="overflow-x-auto rounded-lg bg-background p-3 pr-10 font-mono leading-relaxed text-foreground">
              {query.sql}
            </pre>
            <button
              onClick={copy}
              className="absolute right-2 top-2 rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
              title="Copy SQL"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>

          {query.rows.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full border-collapse">
                <thead className="bg-secondary/50 text-muted-foreground">
                  <tr>
                    {query.columns.map((c) => (
                      <th key={c} className="whitespace-nowrap px-2 py-1.5 text-left font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {query.rows.slice(0, PREVIEW_ROWS).map((row, i) => (
                    <tr key={i} className="border-t border-border">
                      {query.columns.map((c) => (
                        <td key={c} className="whitespace-nowrap px-2 py-1 font-mono text-foreground">
                          {formatCell(row[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {query.rows.length > PREVIEW_ROWS && (
                <p className="border-t border-border px-2 py-1 text-muted-foreground">
                  Showing {PREVIEW_ROWS} of {query.rows.length} rows
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SqlPanel;
