/** The two answers that follow edges are compared with Python's (ADR 0031, decisions 1 and 12).
 *  `uv run python scripts/write_ui_fixtures.py` writes the expected files. */
import { existsSync } from "node:fs";
import { compareText, compareTime } from "@/data/time";
import { auditTrail, staleAssessmentIds, staleByChange } from "@/data/trail";
import { EXPECTED_FILE, MINI_AUDIT_FILE, PARITY_FILE, fixture, mini, readJson } from "./helpers";

interface ExpectedLink {
  controlId: string | null; mapping: { strm: string; strength: number; sufficiency: string } | null;
  resolution: string; providerId: string | null; assessmentId: string | null; status: string | null;
  assuranceLevel: number | null; assessmentSource: string | null; assessedBy: string | null;
  signoffSource: string | null;
  evidence: { evidenceId: string; kind: string; collector: string; collectedAt: string; validUntil: string; sha256: string; source: string }[];
}
interface ExpectedTrail { requirement: string; scope: string; links: ExpectedLink[] }

describe("audit trail parity with Python", () => {
  it("has Python's answer to compare with", () => {
    expect(existsSync(PARITY_FILE), "run `npm run parity` first").toBe(true);
  });

  it("matches Python for every requirement and scope, through the redaction's ID map", () => {
    const index = fixture();
    const expected = readJson<ExpectedTrail[]>(PARITY_FILE);
    expect(expected.length).toBeGreaterThan(1000);
    let withEvidence = 0;
    for (const row of expected) {
      const got = auditTrail(index, row.requirement, row.scope);
      expect(got.links.length, `${row.requirement} ${row.scope}`).toBe(row.links.length);
      row.links.forEach((want, i) => {
        const have = got.links[i]!;
        const where = `${row.requirement} @ ${row.scope} link ${i}`;
        expect({ c: have.controlId, r: have.resolution, p: have.providerId, a: have.assessmentId }, where).toEqual({ c: want.controlId, r: want.resolution, p: want.providerId, a: want.assessmentId });
        expect({ s: have.status, l: have.assuranceLevel, as: have.assessmentSource, by: have.assessedBy, so: have.signoffSource }, where).toEqual({ s: want.status, l: want.assuranceLevel, as: want.assessmentSource, by: want.assessedBy, so: want.signoffSource });
        expect(have.mapping && { strm: have.mapping.strm, strength: have.mapping.strength, sufficiency: have.mapping.sufficiency }, where).toEqual(want.mapping);
        // Python orders equal timestamps by the stored ID, the snapshot by the published one,
        // so compare the sets, and check the order is by time.
        const byId = (a: { evidenceId: string }, b: { evidenceId: string }) => compareText(a.evidenceId, b.evidenceId);
        expect([...have.evidence].sort(byId), where).toEqual([...want.evidence].sort(byId));
        for (let k = 1; k < have.evidence.length; k++) {
          expect(compareTime(have.evidence[k - 1]!.collectedAt, have.evidence[k]!.collectedAt), where).toBeLessThanOrEqual(0);
        }
        withEvidence += want.evidence.length ? 1 : 0;
      });
    }
    expect(withEvidence).toBeGreaterThan(10);
  });

  // The recorded fixture's audit paths hold no redacted Evidence, so the ID map is proved on the
  // mini snapshot, whose supporting config Evidence is rebuilt by redaction (the trap in the plan).
  it("matches Python where the path crosses redacted Evidence", () => {
    const index = mini();
    const expected = readJson<ExpectedTrail[]>(MINI_AUDIT_FILE);
    let redacted = 0;
    for (const row of expected) {
      const got = auditTrail(index, row.requirement, row.scope);
      expect(got.links.length).toBe(row.links.length);
      row.links.forEach((want, i) => {
        const have = got.links[i]!;
        expect({ c: have.controlId, r: have.resolution, a: have.assessmentId, s: have.status }, row.scope).toEqual({ c: want.controlId, r: want.resolution, a: want.assessmentId, s: want.status });
        expect(have.evidence.map((e) => e.evidenceId).sort()).toEqual(want.evidence.map((e) => e.evidenceId).sort());
        expect(have.evidence.map((e) => e.sha256).sort()).toEqual(want.evidence.map((e) => e.sha256).sort());
        redacted += have.evidence.filter((e) => index.nodeOf(e.evidenceId, "Evidence")?.redacted).length;
      });
    }
    expect(redacted).toBeGreaterThan(0);
  });
});

describe("stale_by_change parity with Python, on the mini snapshot", () => {
  const expected = () => readJson<{ change_id: string; evidence: { evidenceId: string; resourceId: string; assessmentIds: string[] }[]; assessment_ids: string[] }>(EXPECTED_FILE);

  it("finds the same evidence and assessments", () => {
    const want = expected();
    const got = staleByChange(mini(), want.change_id);
    expect(got.evidence).toEqual(want.evidence);
    expect(staleAssessmentIds(got)).toEqual(want.assessment_ids);
  });

  it("treats only evidence collected before the change as stale", () => {
    const index = mini();
    const change = index.ofType("ChangeEvent")[0]!;
    const staleIds = new Set(staleByChange(index, change.id).evidence.map((e) => e.evidenceId));
    const fromResource = index.ofType("Evidence").filter((e) => e.kind === "config_snapshot");
    expect(fromResource.length).toBe(2);
    for (const e of fromResource) expect(staleIds.has(e.id)).toBe(compareTime(e.collected_at, change.detected_at) < 0);
    expect(staleIds.size).toBe(1);
  });

  it("never touches evidence that was not collected from the resource", () => {
    const index = mini();
    const attestation = index.ofType("Evidence").find((e) => e.kind === "attestation")!;
    const change = index.ofType("ChangeEvent")[0]!;
    expect(staleByChange(index, change.id).evidence.map((e) => e.evidenceId)).not.toContain(attestation.id);
  });

  it("refuses an ID that is not a change event", () => {
    expect(() => staleByChange(mini(), "sys:mini-bot")).toThrow();
  });
});
