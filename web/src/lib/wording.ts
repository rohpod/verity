/** Wording that is a duty, not decoration (ADR 0031 "UI duties"). Tests assert these strings, so
 *  a change here must be a decision. Do not soften them. */

/** ADR 0018: ISO requirements never show as satisfied. */
export const ISO_NOTE =
  "ISO requirements show only a clause ID and an original summary. Verity has not read the standard's text, so a mapping to an ISO clause claims only an overlap and an ISO requirement can never show as satisfied. This is intended.";

/** ADR 0029, decision 6. */
export const REDACTED_NOTE =
  "Redacted: the hash covers the published content, not the stored original, so it cannot be checked against the live table.";

/** ADR 0028, decision 5. Replaces the wording in ADR 0025. */
export const BOUNDARY_NOTE =
  "IAM's policy simulator shows the permissions boundary denies this call. No live call was tried.";

/** ADR 0017. */
export const STRENGTH_NOTE =
  "Strength is a Verity convention taken from the Secure Controls Framework, not from NIST.";

/** ADR 0004 and 0010: a derived link is not a STRM relationship. */
export const DERIVED_NOTE =
  "Derived link: it has no STRM type of its own. It goes through a hub control, and the two requirements are related, never equal.";

/** D11. */
export const SIMULATED_SIGNOFF = "simulated sign-off";

/** ADR 0005. */
export const NO_SCORE_NOTE =
  "Verity shows no single compliance score. Each requirement and control keeps its own status, assurance level and freshness.";

/** README. */
export const NOT_LEGAL_ADVICE = "Verity is a learning project, not legal advice.";
export const MAPPINGS_NOTE = "Framework mappings are the author's own interpretation.";

/** ADR 0029, decision 10: `H#` history is not published. */
export const HISTORY_LIMIT =
  "Node history (H#) is not published in the snapshot. This tab shows the change events and discovery runs that are.";

/** Architecture §L. */
export const INHERITED_ORG = "inherited from the organisation";

export const SYNTHETIC_NOTE = "Synthetic: invented organisation data, not a real company or person.";

export const ASSURANCE_LEVELS = [
  { level: 0, name: "L0 Inferred", meaning: "No evidence: Verity infers the state." },
  { level: 1, name: "L1 Declared", meaning: "Someone stated it." },
  { level: 2, name: "L2 Evidenced", meaning: "Evidence collected from the system." },
  { level: 3, name: "L3 Tested", meaning: "An automated test ran." },
  { level: 4, name: "L4 Verified", meaning: "A person verified it. Organisational and legal controls need this." },
] as const;
