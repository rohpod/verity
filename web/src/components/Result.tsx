import { Badge, type Tone } from "@/components/ui";
import { SimulatedFlag, ProvenanceBadge } from "@/components/ProvenanceBadge";
import type { ControlResult } from "@/data/types";
import { ASSURANCE_LEVELS, SIMULATED_SIGNOFF } from "@/lib/wording";
import { words } from "@/lib/utils";

const STATUS_TONE: Record<ControlResult["status"], Tone> = {
  implemented: "good",
  partially_implemented: "warn",
  not_implemented: "bad",
  not_assessed: "neutral",
  not_applicable: "neutral",
};
const FRESH_TONE = { fresh: "good", expiring: "warn", stale: "bad" } as const;

/** Status, level and freshness together, never a bare tick (ADR 0005). */
export function ResultCell({ result }: { result: ControlResult }) {
  const level = ASSURANCE_LEVELS[result.level];
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid="control-result">
      <Badge tone={STATUS_TONE[result.status]}>{words(result.status)}</Badge>
      <Badge title={level.meaning}>{level.name}</Badge>
      {result.freshness ? <Badge tone={FRESH_TONE[result.freshness]}>{result.freshness}</Badge> : <Badge>no evidence to age</Badge>}
      {result.level === 4 && result.simulated ? <Badge tone="simulated">{SIMULATED_SIGNOFF}</Badge> : <SimulatedFlag simulated={result.simulated} />}
      <ProvenanceBadge source={result.source} />
    </span>
  );
}
