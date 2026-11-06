import { useMemo, useState } from "react";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { Empty } from "@/components/States";
import { Badge, Card, Note, Table, Td, Th } from "@/components/ui";
import { useIndex } from "@/data/provider";
import { words } from "@/lib/utils";
import { DERIVED_NOTE, ISO_NOTE, MAPPINGS_NOTE, STRENGTH_NOTE } from "@/lib/wording";

export function Crosswalk() {
  const index = useIndex();
  const rows = index.snapshot.crosswalk;
  const pairs = useMemo(() => [...new Set(rows.map((r) => `${r.from_framework}|${r.to_framework}`))].sort(), [rows]);
  const [pair, setPair] = useState(pairs[0] ?? "");
  const [from, to] = pair.split("|");
  const shown = rows.filter((r) => r.from_framework === from && r.to_framework === to);
  const direct = index.edges.filter((e) => e.type === "MAPS_TO");
  const [framework, setFramework] = useState("");
  const directShown = direct.filter((e) => !framework || index.out(e.src, "PART_OF").some((p) => p.dst === framework) || index.out(e.src, "PART_OF").some((p) => index.out(p.dst, "PART_OF").some((q) => q.dst === framework)));
  const isoShown = pair.includes("iso") || framework.includes("iso");

  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Crosswalk explorer</h1>
      <Note>{MAPPINGS_NOTE} Two requirements are related through a hub control, never treated as equal.</Note>
      <Note>{STRENGTH_NOTE}</Note>
      {isoShown ? <Note>{ISO_NOTE}</Note> : null}

      <Card title="Derived links between frameworks">
        <Note>{DERIVED_NOTE}</Note>
        {pairs.length === 0 ? <Empty>No crosswalk rows in this snapshot.</Empty> : (
          <>
            <label className="text-sm">From → to{" "}
              <select value={pair} onChange={(e) => setPair(e.target.value)} className="border border-[var(--border)] bg-transparent">
                {pairs.map((p) => { const [a, b] = p.split("|") as [string, string]; return <option key={p} value={p}>{index.label(a)} → {index.label(b)}</option>; })}
              </select>
            </label>
            <Table label="Derived crosswalk">
              <thead><tr><Th>Requirement</Th><Th>Related requirement</Th><Th>Through control</Th><Th>From STRM</Th><Th>To STRM</Th><Th>Strength</Th></tr></thead>
              <tbody>
                {shown.flatMap((row) => row.links.map((link, i) => (
                  <tr key={`${row.requirement_id}${i}`} data-testid="derived-link">
                    <Td>{index.label(row.requirement_id)} <Badge tone="info">derived</Badge> <ProvenanceBadge source={row.source} /></Td>
                    <Td>{index.label(link.target_requirement_id)}</Td>
                    <Td>{link.via_control_id}</Td>
                    <Td>{words(link.from_strm)}</Td><Td>{words(link.to_strm)}</Td>
                    <Td>{link.strength}</Td>
                  </tr>
                )))}
              </tbody>
            </Table>
          </>
        )}
      </Card>

      <Card title="Direct mappings (requirement → hub control)">
        <label className="text-sm">Framework{" "}
          <select value={framework} onChange={(e) => setFramework(e.target.value)} className="border border-[var(--border)] bg-transparent">
            <option value="">All</option>
            {index.ofType("Framework").map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>
        <Table label="Direct mappings">
          <thead><tr><Th>Requirement</Th><Th>Control</Th><Th>STRM</Th><Th>Strength</Th><Th>Sufficiency</Th><Th>Rationale</Th></tr></thead>
          <tbody>
            {directShown.map((e, i) => e.type === "MAPS_TO" && (
              <tr key={i}>
                <Td>{index.label(e.src)}</Td><Td>{e.dst}</Td><Td>{words(e.strm)}</Td><Td>{e.strength}</Td><Td>{e.sufficiency}</Td>
                <Td><span className="text-xs">{words(e.rationale_type)}: {e.rationale}</span> <ProvenanceBadge source={e.source} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
