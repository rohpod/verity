import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState } from "@tanstack/react-table";
import { useState } from "react";
import { ProvenanceBadge } from "@/components/ProvenanceBadge";
import { Empty } from "@/components/States";
import { Badge, Card, Note, Table, Td, Th } from "@/components/ui";
import { useIndex } from "@/data/provider";
import { findingsFor, ownersOf, severityRank } from "@/data/views";
import type { NodeOf } from "@/data/types";
import { count, words } from "@/lib/utils";
import { SYNTHETIC_NOTE } from "@/lib/wording";

interface Row {
  system: NodeOf<"AISystem">;
  owners: string;
  findings: string;
  states: string;
}

const column = createColumnHelper<Row>();

export function Registry() {
  const index = useIndex();
  const { hash } = useLocation();
  const [sorting, setSorting] = useState<SortingState>([{ id: "name", desc: false }]);
  useEffect(() => {
    if (hash === "#candidates") document.getElementById("candidates")?.scrollIntoView();
  }, [hash]);

  const rows: Row[] = index.ofType("AISystem").map((system) => ({
    system,
    owners: ownersOf(index, system.id).map((p) => p.name).join(", ") || "none recorded",
    findings: count(findingsFor(index, system.id), (f) => f.severity).map(([s, n]) => `${n} ${s}`).join(", ") || "none",
    states: count(index.snapshot.requirement_statuses.filter((r) => r.system_id === system.id), (r) => r.state).map(([s, n]) => `${n} ${words(s)}`).join(", "),
  }));

  const table = useReactTable({
    data: rows,
    columns: [
      column.accessor((r) => r.system.name, { id: "name", header: "System", cell: (c) => <Link to={`/systems/${encodeURIComponent(c.row.original.system.id)}`}>{c.getValue()}</Link> }),
      column.accessor((r) => r.system.kind, { id: "kind", header: "Kind", cell: (c) => words(c.getValue()) }),
      column.accessor((r) => r.system.source, { id: "source", header: "Source", cell: (c) => <ProvenanceBadge source={c.row.original.system.source} /> }),
      column.accessor("owners", { header: "Owner" }),
      column.accessor("findings", { header: "Findings" }),
      column.accessor("states", { header: "Requirement states" }),
    ],
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const candidates = index.ofType("Candidate");
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">AI Registry</h1>
      {rows.some((r) => r.system.source === "synthetic") ? <Note>{SYNTHETIC_NOTE}</Note> : null}
      <Table label="AI systems">
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <Th key={header.id} aria-sort={header.column.getIsSorted() === "asc" ? "ascending" : header.column.getIsSorted() === "desc" ? "descending" : "none"}>
                  <button onClick={header.column.getToggleSortingHandler()} className="font-semibold">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </button>
                </Th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>{row.getVisibleCells().map((cell) => <Td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</Td>)}</tr>
          ))}
        </tbody>
      </Table>

      <Card id="candidates" title="Candidates inbox">
        <p className="mb-2 text-sm">Resources discovery thinks may be AI but that are not in the registry. A person decides; Verity never registers one on its own.</p>
        {candidates.length === 0 ? <Empty>No candidates in this snapshot.</Empty> : null}
        <ul className="grid gap-3">
          {candidates.map((candidate) => {
            const found = findingsFor(index, candidate.id).sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
            return (
              <li key={candidate.id} className="rounded border border-[var(--border)] p-2" data-testid="candidate">
                <p className="flex flex-wrap items-center gap-2">
                  <strong>{candidate.name}</strong>
                  <Badge tone="warn">{candidate.ai_likelihood}</Badge>
                  <ProvenanceBadge source={candidate.source} />
                  {found.map((f) => <Badge key={f.code} tone={f.severity === "high" ? "bad" : "warn"}>{f.severity}: {words(f.code)}</Badge>)}
                </p>
                <p className="mt-1 text-sm">Why discovery flagged it, by the signals that fired:</p>
                <ul className="ml-5 list-disc text-sm">
                  {candidate.signals.map((signal) => <li key={signal}>{words(signal)}</li>)}
                </ul>
                {found.map((f) => <p key={f.code} className="mt-1 text-sm">{f.message}</p>)}
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
