import { Card } from "@/components/ui";
import { useIndex } from "@/data/provider";
import { MAPPINGS_NOTE, NOT_LEGAL_ADVICE } from "@/lib/wording";

export function About() {
  const { header } = useIndex().snapshot;
  return (
    <div className="grid gap-3">
      <h1 className="text-xl font-semibold">About</h1>
      <Card>
        <p>{NOT_LEGAL_ADVICE} {MAPPINGS_NOTE}</p>
        <p className="mt-2 text-sm">ISO standards are referenced by clause ID with original summaries only. No ISO text is reproduced. Bedrock and OpenAI are mock-only.</p>
        <p className="mt-2 text-sm">Verity’s dashboard reads one file, <code>snapshot.json</code>, and computes no governance result of its own. Snapshot schema version {header.schema_version}, data source: {header.data_source}.</p>
      </Card>
    </div>
  );
}
