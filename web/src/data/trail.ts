/** The two answers that follow edges, ported from `graph/traversals.py` (ADR 0031, decision 1).
 *  Everything else the dashboard shows is read from the snapshot. `parity.test.ts` compares
 *  each with Python's answer. */
import { SnapshotIndex, compareEdges } from "./index";
import { compareText, compareTime } from "./time";
import type { Edge, NodeOf, Resolution } from "./types";

type MapsTo = Extract<Edge, { type: "MAPS_TO" }>;

export interface AuditEvidence {
  evidenceId: string;
  kind: string;
  collector: string;
  collectedAt: string;
  validUntil: string;
  sha256: string;
  source: string;
}

export interface AuditLink {
  controlId: string | null;
  mapping: MapsTo | null;
  resolution: Resolution;
  providerId: string | null;
  assessmentId: string | null;
  status: string | null;
  assuranceLevel: number | null;
  assessmentSource: string | null;
  assessedBy: string | null;
  signoffSource: string | null;
  evidence: AuditEvidence[];
}

export interface AuditTrail {
  requirementId: string;
  scopeId: string;
  links: AuditLink[];
}

interface Target {
  resolution: Resolution;
  providerId: string | null;
  scopeId: string | null;
}

const SCOPE_NODE_TYPE = {
  organisation: "Organisation",
  system: "AISystem",
  provider: "Provider",
} as const;

function organisation(index: SnapshotIndex): NodeOf<"Organisation"> | undefined {
  return index.ofType("Organisation")[0];
}

function providerTargets(index: SnapshotIndex, systemId: string): Target[] {
  const providers = new Set<string>();
  let unknown = false;
  const used = index.out(systemId, "USES_MODEL");
  for (const uses of used) {
    const model = index.nodeOf(uses.dst, "Model");
    const provided = index.out(uses.dst, "PROVIDED_BY");
    for (const edge of provided) providers.add(edge.dst);
    if (model?.origin === "third_party" && provided.length === 0) unknown = true;
  }
  const targets: Target[] = [...providers]
    .sort(compareText)
    .map((p) => ({ resolution: "inherited_provider", providerId: p, scopeId: p }));
  if (unknown || used.length === 0) {
    targets.push({ resolution: "provider_unknown", providerId: null, scopeId: null });
  }
  return targets.length ? targets : [{ resolution: "not_applicable", providerId: null, scopeId: null }];
}

function targetsFor(index: SnapshotIndex, scopeId: string, scopeType: string, control: NodeOf<"Control">): Target[] {
  const level = control.scope_level;
  if (scopeType === "AISystem") {
    if (level === "system") return [{ resolution: "direct", providerId: null, scopeId }];
    if (level === "organisation") {
      return [{ resolution: "inherited_org", providerId: null, scopeId: organisation(index)?.id ?? null }];
    }
    return providerTargets(index, scopeId);
  }
  if (SCOPE_NODE_TYPE[level] === scopeType) {
    return [{ resolution: "direct", providerId: null, scopeId }];
  }
  return [{ resolution: "not_applicable", providerId: null, scopeId: null }];
}

function assessmentFor(index: SnapshotIndex, controlId: string, scopeId: string | null): string | null {
  if (scopeId === null) return null;
  for (const assesses of index.in(controlId, "ASSESSES")) {
    if (index.out(assesses.src, "SCOPED_TO").some((s) => s.dst === scopeId)) return assesses.src;
  }
  return null;
}

function link(index: SnapshotIndex, mapping: MapsTo, control: NodeOf<"Control">, target: Target): AuditLink {
  const assessmentId = assessmentFor(index, control.id, target.scopeId);
  const ca = index.nodeOf(assessmentId, "ControlAssessment");
  const assessed = assessmentId ? index.in(assessmentId, "ASSESSED").sort(compareEdges) : [];
  const signoff = assessed.find((e) => ca && e.src === ca.assessor) ?? assessed[0];
  const evidence = (assessmentId ? index.in(assessmentId, "SUPPORTS") : [])
    .map((e) => index.nodeOf(e.src, "Evidence"))
    .filter((e): e is NodeOf<"Evidence"> => e !== undefined)
    .sort((a, b) => compareTime(a.collected_at, b.collected_at) || compareText(a.id, b.id));
  return {
    controlId: control.id,
    mapping,
    resolution: target.resolution,
    providerId: target.providerId,
    assessmentId,
    status: ca?.status ?? null,
    assuranceLevel: ca?.assurance_level ?? null,
    assessmentSource: ca?.source ?? null,
    assessedBy: signoff?.src ?? null,
    signoffSource: signoff?.source ?? null,
    evidence: evidence.map((e) => ({
      evidenceId: e.id,
      kind: e.kind,
      collector: e.collector,
      collectedAt: e.collected_at,
      validUntil: e.valid_until,
      sha256: e.sha256,
      source: e.source,
    })),
  };
}

/** `Req -> Ctl -> CA -> Evidence`, with hashes, collectors and the `ASSESSED` person. */
export function auditTrail(index: SnapshotIndex, requirementId: string, scopeId: string): AuditTrail {
  if (!index.nodeOf(requirementId, "Requirement")) {
    throw new Error(`${requirementId} is not a Requirement in the snapshot`);
  }
  const scope = index.node(scopeId);
  if (!scope || !["AISystem", "Organisation", "Provider"].includes(scope.type)) {
    throw new Error(`${scopeId} is not an AISystem, Organisation or Provider in the snapshot`);
  }
  const links: AuditLink[] = [];
  for (const mapping of index.out(requirementId, "MAPS_TO")) {
    const control = index.nodeOf(mapping.dst, "Control");
    if (mapping.type !== "MAPS_TO" || mapping.strm === "no_relationship" || !control) continue;
    for (const target of targetsFor(index, scopeId, scope.type, control)) {
      links.push(link(index, mapping, control, target));
    }
  }
  if (links.length === 0) {
    links.push({
      controlId: null, mapping: null, resolution: "unmapped", providerId: null, assessmentId: null,
      status: null, assuranceLevel: null, assessmentSource: null, assessedBy: null,
      signoffSource: null, evidence: [],
    });
  }
  links.sort((a, b) => compareText(a.controlId ?? "", b.controlId ?? "") || compareText(a.providerId ?? "", b.providerId ?? ""));
  return { requirementId, scopeId, links };
}

export interface StaleEvidence {
  evidenceId: string;
  resourceId: string;
  assessmentIds: string[];
}

export interface StaleImpact {
  changeId: string;
  evidence: StaleEvidence[];
}

/** `ChangeEvent -AFFECTS-> Resource <-COLLECTED_FROM- Evidence -SUPPORTS-> CA`. Only evidence
 *  collected before the change was detected is stale (ADR 0012). */
export function staleByChange(index: SnapshotIndex, changeId: string): StaleImpact {
  const change = index.nodeOf(changeId, "ChangeEvent");
  if (!change) throw new Error(`${changeId} is not a ChangeEvent in the snapshot`);
  const found: StaleEvidence[] = [];
  for (const affects of index.out(change.id, "AFFECTS")) {
    for (const collected of index.in(affects.dst, "COLLECTED_FROM")) {
      const evidence = index.nodeOf(collected.src, "Evidence");
      if (evidence && compareTime(evidence.collected_at, change.detected_at) < 0) {
        found.push({
          evidenceId: evidence.id,
          resourceId: affects.dst,
          assessmentIds: index.out(evidence.id, "SUPPORTS").map((e) => e.dst).sort(compareText),
        });
      }
    }
  }
  found.sort((a, b) => compareText(a.evidenceId, b.evidenceId) || compareText(a.resourceId, b.resourceId));
  return { changeId: change.id, evidence: found };
}

export function staleAssessmentIds(impact: StaleImpact): string[] {
  return [...new Set(impact.evidence.flatMap((e) => e.assessmentIds))].sort(compareText);
}
