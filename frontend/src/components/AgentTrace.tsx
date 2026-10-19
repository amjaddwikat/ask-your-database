import { Fragment } from "react";
import type { StepTrace } from "@/lib/api";

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

/** One-line summary of which agents ran and how long each took, e.g. "router 610ms → sql 1.0s". */
const AgentTrace = ({ trace }: { trace: StepTrace[] }) => {
  return (
    <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 px-1 font-mono text-[11px] text-muted-foreground">
      {trace.map((t, i) => (
        <Fragment key={`${t.step}-${i}`}>
          {i > 0 && <span aria-hidden>→</span>}
          <span title={t.detail ?? undefined}>
            {t.step} <span className="text-foreground/70">{formatMs(t.duration_ms)}</span>
          </span>
        </Fragment>
      ))}
    </p>
  );
};

export default AgentTrace;
