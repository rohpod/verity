/** The indexes, built once per snapshot: nodes by ID, edges by `src` and `dst`. It keeps what
 *  Python's loader keeps for the open graph (`as_of=None`): a node or edge with no `valid_to`,
 *  and an edge only if both endpoints are kept (`graph/loader.py`). */
import { compareText } from "./time";
import type { Edge, EdgeType, Node, NodeOf, NodeType, Open, Snapshot } from "./types";

export function isOpen(record: Open): boolean {
  return record.valid_to === null;
}

/** The part of an edge that tells two edges of one type between one pair apart. */
export function qualifier(edge: Edge): string {
  if (edge.type === "APPLIES_TO") return edge.role;
  if (edge.type === "PROCESSES") return edge.purpose;
  return "";
}

/** Python's edge order: source, type, destination, qualifier. */
export function compareEdges(a: Edge, b: Edge): number {
  return (
    compareText(a.src, b.src) ||
    compareText(a.type, b.type) ||
    compareText(a.dst, b.dst) ||
    compareText(qualifier(a), qualifier(b))
  );
}

export class SnapshotIndex {
  readonly snapshot: Snapshot;
  readonly nodes: Map<string, Node>;
  readonly edges: Edge[];
  private readonly outgoing = new Map<string, Edge[]>();
  private readonly incoming = new Map<string, Edge[]>();
  private readonly byType = new Map<NodeType, Node[]>();

  constructor(snapshot: Snapshot) {
    this.snapshot = snapshot;
    this.nodes = new Map();
    for (const node of [...snapshot.nodes].sort((a, b) => compareText(a.id, b.id))) {
      if (!isOpen(node)) continue;
      this.nodes.set(node.id, node);
      const list = this.byType.get(node.type) ?? [];
      list.push(node);
      this.byType.set(node.type, list);
    }
    this.edges = snapshot.edges
      .filter((e) => isOpen(e) && this.nodes.has(e.src) && this.nodes.has(e.dst))
      .sort(compareEdges);
    for (const edge of this.edges) {
      push(this.outgoing, edge.src, edge);
      push(this.incoming, edge.dst, edge);
    }
  }

  node(id: string | null | undefined): Node | undefined {
    return id ? this.nodes.get(id) : undefined;
  }

  nodeOf<T extends NodeType>(id: string | null | undefined, type: T): NodeOf<T> | undefined {
    const found = this.node(id);
    return found?.type === type ? (found as NodeOf<T>) : undefined;
  }

  ofType<T extends NodeType>(type: T): NodeOf<T>[] {
    return (this.byType.get(type) ?? []) as NodeOf<T>[];
  }

  out(id: string, type?: EdgeType): Edge[] {
    const all = this.outgoing.get(id) ?? [];
    return type ? all.filter((e) => e.type === type) : all;
  }

  in(id: string, type?: EdgeType): Edge[] {
    const all = this.incoming.get(id) ?? [];
    return type ? all.filter((e) => e.type === type) : all;
  }

  /** A readable name for any node ID, falling back to the ID itself. */
  label(id: string): string {
    const node = this.nodes.get(id);
    if (!node) return id;
    if ("name" in node) return node.name;
    if ("title" in node) return node.title;
    if (node.type === "Requirement") return node.ref;
    return node.id;
  }
}

function push(map: Map<string, Edge[]>, key: string, edge: Edge): void {
  const list = map.get(key);
  if (list) list.push(edge);
  else map.set(key, [edge]);
}
