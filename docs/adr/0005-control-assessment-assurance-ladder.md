# 0005 — ControlAssessment node + assurance ladder
- **Status:** Accepted (2026-11-05)

## Context
Most GRC dashboards show a single green tick that blends three different claims:
- a requirement is *mapped* to a control,
- the control is *implemented*,
- its implementation is *demonstrated*.

The project brief also forbids an AWS configuration check from establishing compliance with broad organisational or legal requirements.

## Decision
- Implementation status lives on a **ControlAssessment** node (control × scope, where scope is a system, the organisation or a provider), not on the Control itself.
- Organisation-scoped controls are *inherited* by systems.
- Each assessment also carries an **assurance level**: L0 Inferred → L1 Declared → L2 Evidenced → L3 Tested → L4 Verified (by a named person, recorded with an `ASSESSED` edge).
- Automated checks can only raise controls marked `automatable: true`. Organisational and legal controls cap at *Partially implemented / L2* until an L4 verification exists.

## Consequences
- More nodes in the graph, but honest semantics.
- The UI can show "Implemented, L3 Tested, evidence fresh" instead of a bare tick, which is a core differentiator.
