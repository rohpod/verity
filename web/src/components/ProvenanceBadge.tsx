import { Badge, type Tone } from "@/components/ui";
import type { Source } from "@/data/types";

/** One `source` to one badge (D12, ADR 0031 decision 9). The record covers every `Source`, so a
 *  value added to the schema fails the typecheck until it has a badge. */
export const SOURCE_BADGES: Record<Source, { label: string; tone: Tone; meaning: string }> = {
  discovered: { label: "Live-discovered", tone: "good", meaning: "read from the AWS account by the crawler" },
  declared: { label: "Declared", tone: "info", meaning: "stated by a person in a reviewed file" },
  seeded: { label: "Seeded", tone: "neutral", meaning: "loaded from the reviewed content files" },
  synthetic: { label: "Synthetic", tone: "warn", meaning: "invented organisation data, not a real company or person" },
  derived: { label: "Derived", tone: "info", meaning: "computed by Verity from other records" },
  simulated: { label: "Simulated", tone: "simulated", meaning: "a stand-in for something that was not done for real" },
};

export function ProvenanceBadge({ source }: { source: Source }) {
  const badge = SOURCE_BADGES[source];
  return (
    <Badge tone={badge.tone} title={`${badge.label}: ${badge.meaning}`} data-testid="provenance-badge" data-source={source}>
      {badge.label}
    </Badge>
  );
}

/** The `simulated` flag on a derived row has its own badge beside Derived (ADR 0030). */
export function SimulatedFlag({ simulated }: { simulated: boolean }) {
  return simulated ? (
    <Badge tone="simulated" title="This result rests on a simulated sign-off by a fictional person" data-testid="simulated-flag">
      Simulated
    </Badge>
  ) : null;
}
