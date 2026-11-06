/** Joins and lookups over the snapshot. Nothing here computes a status, finding, severity,
 *  applicability, freshness or crosswalk (ADR 0031, decision 1). */
import type { SnapshotIndex } from "./index";
import { compareText } from "./time";
import type { ControlResult, Finding, NodeOf, Obligation, RequirementStatus } from "./types";

/** The frameworks a requirement sits under, through any chain of PART_OF. */
export function frameworksOf(index: SnapshotIndex, requirementId: string): string[] {
  const found = new Set<string>();
  const seen = new Set<string>();
  const stack = [requirementId];
  while (stack.length) {
    const current = stack.pop() as string;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const edge of index.out(current, "PART_OF")) {
      if (index.node(edge.dst)?.type === "Framework") found.add(edge.dst);
      stack.push(edge.dst);
    }
  }
  return [...found].sort(compareText);
}

export function findingsFor(index: SnapshotIndex, subject: string): Finding[] {
  return index.snapshot.findings.filter((f) => f.subject === subject);
}

export function statusesFor(index: SnapshotIndex, systemId: string): RequirementStatus[] {
  return index.snapshot.requirement_statuses.filter((s) => s.system_id === systemId);
}

export function obligationsFor(index: SnapshotIndex, systemId: string): Obligation[] {
  return index.snapshot.obligations.filter((o) => o.system_id === systemId);
}

export function resultFor(index: SnapshotIndex, controlId: string, scopeId: string): ControlResult | undefined {
  return index.snapshot.control_results.find((r) => r.control_id === controlId && r.scope_id === scopeId);
}

export function ownersOf(index: SnapshotIndex, id: string): NodeOf<"Person">[] {
  return index
    .in(id, "OWNS")
    .map((e) => index.nodeOf(e.src, "Person"))
    .filter((p): p is NodeOf<"Person"> => p !== undefined);
}

/** The AWS resources a system runs on. */
export function resourcesOf(index: SnapshotIndex, systemId: string): NodeOf<"AWSResource">[] {
  return index
    .out(systemId, "RUNS_ON")
    .map((e) => index.nodeOf(e.dst, "AWSResource"))
    .filter((r): r is NodeOf<"AWSResource"> => r !== undefined);
}

export function severityRank(severity: string): number {
  return severity === "high" ? 0 : severity === "medium" ? 1 : 2;
}
