import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";

cytoscape.use(fcose as unknown as cytoscape.Ext);

export interface GraphNode { id: string; label: string; type: string }
export interface GraphEdge { id: string; source: string; target: string; label: string }

const COLOURS: Record<string, string> = {
  AISystem: "#1d4ed8", Candidate: "#b45309", AWSResource: "#0f766e", Model: "#7c3aed", Provider: "#be185d",
  Dataset: "#4d7c0f", Risk: "#b91c1c", Control: "#334155", Requirement: "#0369a1", Evidence: "#a16207",
  ControlAssessment: "#64748b", Person: "#475569",
};

/** The Cytoscape view, loaded only when the Graph page is opened. */
export default function GraphCanvas({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({
      container: container.current,
      elements: [
        ...nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type } })),
        ...edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, label: e.label } })),
      ],
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 9, "background-color": (n: cytoscape.NodeSingular) => COLOURS[n.data("type") as string] ?? "#6b7280", color: "#374151" } },
        { selector: "edge", style: { width: 1, "line-color": "#9ca3af", "target-arrow-shape": "triangle", "target-arrow-color": "#9ca3af", "curve-style": "bezier" } },
      ],
      layout: { name: "fcose", animate: false } as cytoscape.LayoutOptions,
    });
    return () => cy.destroy();
  }, [nodes, edges]);
  return <div ref={container} role="img" aria-label="Graph of the chosen node and its neighbours" className="mb-3 h-96 w-full rounded border border-[var(--border)]" />;
}
