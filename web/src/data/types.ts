import type { Snapshot as GeneratedSnapshot } from "../../generated/snapshot";

export type Snapshot = GeneratedSnapshot;
export type Node = Snapshot["nodes"][number];
export type Edge = Snapshot["edges"][number];
export type NodeType = Node["type"];
export type EdgeType = Edge["type"];
export type NodeOf<T extends NodeType> = Extract<Node, { type: T }>;
export type Source = Node["source"];
export type Finding = Snapshot["findings"][number];
export type RequirementStatus = Snapshot["requirement_statuses"][number];
export type ControlResult = Snapshot["control_results"][number];
export type Obligation = Snapshot["obligations"][number];
export type ProviderImpact = Snapshot["provider_impact"][number];
export type CrosswalkRow = Snapshot["crosswalk"][number];
export type Resolution = Obligation["resolution"];

/** Anything that has an envelope: nodes and edges both carry `source` and `valid_to`. */
export interface Open {
  valid_to: string | null;
}
