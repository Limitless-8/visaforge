# VisaForge v0.11.1 — Route Step Completion Logic Fix

## Bug

Some route steps with required documents still showed "Mark as
prepared" — the soft-step completion shortcut. This was wrong:
evidence-based steps must require document upload + verification
before being marked complete.

Specifically, every Pakistan preparation step (HEC attestation,
IBCC, MOFA, PCC, Passport, TB test, NADRA) was rendering the
"Mark as prepared" button. So were profile-driven visa-readiness
steps (CAS / LOA / Zulassung / Proof of funds *).

## Root cause

Two layers were misclassifying steps as soft:

1. **`_pakistan_step_specs` left `required_documents=[]`** on every
   Pakistan step. Each Pakistan process produces a verifiable
   certificate, so the step expects at minimum one document keyed by
   the process id. Leaving the list empty defeated all the
   evidence-based status logic downstream.

2. **`pages/3_Route_Plan.py` used a brittle `is_soft_task` heuristic**
   (`not step.required_documents and not step.evidence`) that
   classified any step without an explicit `required_documents` list
   as soft — including Pakistan steps and profile-driven visa
   steps.

The fix is to make the soft-vs-evidence classification a single
canonical predicate that all consumers (page, completion validator,
mark-complete service) use.

## Fix

### `models/schemas.py`

* Added `awaiting_documents` to the `RouteStepStatus` literal so the
  evidence overlay can express "evidence step, no upload yet" without
  reusing `available` (which previously caused the page to render
  "Mark as prepared" on a step that genuinely requires upload).

### `services/route_plan_service.py`

* **NEW `is_evidence_step(step) -> bool`** — canonical evidence-vs-soft
  predicate. Returns True if the step has any of:
  - non-empty `required_documents`
  - a `pakistan_process_id`
  - a key in the profile-driven evidence set
    (`cas_offer_confirmation`, `loa_offer_confirmation`,
    `zulassung_offer_confirmation`, `proof_of_funds_uk/_ca/_de`)
* **NEW `can_complete_step(profile_id, step) -> (bool, str)`** — the
  spec §3 gating predicate. Both the page UI and the service
  `mark_step_complete` route through this so they can never
  disagree.
* **`_pakistan_step_specs`** — Pakistan steps now declare
  `required_documents=[pid]`. Each step properly expects a
  certificate keyed by the process id (e.g. `hec_attestation` step
  expects a doc with `doc_type='hec_attestation'`).
* **`_apply_evidence_overlay`** — evidence steps with no upload yet
  now transition from `available` → `awaiting_documents` (per spec
  rule 4). Profile-driven evidence steps that the intrinsic-status
  pass already promoted to a meaningful status (`pending`,
  `in_progress`, etc.) are preserved. The classification predicate
  is now `is_evidence_step()` rather than the inline boolean.
* **`mark_step_complete`** — refactored to delegate validation to
  `can_complete_step`. The service-side gate is now identical to the
  page-side button-rendering gate.

### `pages/3_Route_Plan.py`

* Imports `is_evidence_step` and `can_complete_step` from the
  service.
* Status pill style map gains `awaiting_documents` (📤 with a blue
  treatment).
* Upload slots and the evidence block render only for evidence
  steps. Soft steps no longer offer upload UI.
* Completion-button rendering rewritten:
  - **Evidence step**: NEVER shows "Mark as prepared". Shows
    "✅ Mark as Complete" only when `status == ready_to_complete`
    AND `can_complete_step` allows. For other evidence statuses,
    surfaces a contextual hint instead of a button:
    - `awaiting_documents` → "Upload the required document(s)
      below to move this step forward."
    - `pending_verification` → "Document(s) uploaded — verification
      in progress."
    - `needs_attention` → warning to re-upload a corrected version.
  - **Soft step**: shows "✅ Mark as prepared" only when
    `can_complete_step` allows AND status is `available` /
    `in_progress` / `pending`.

## What did NOT change

* `services/document_service.py`, `services/document_verification_service.py`,
  `services/document_extraction_service.py` — untouched. The
  verification + extraction pipeline already produced the
  `verification_status` values the overlay reads.
* Manual status dropdowns — still absent. The fix never reintroduces
  user-set status; everything is derived.
* Dependency unlocking from v0.10.1 — preserved. The evidence overlay
  still runs before the dependency resolver (the v0.10.1 fix), so
  when an evidence step transitions to `completed` it cascades
  through dependents on the next render.
* AI explain buttons — unchanged. AI cannot mark steps complete
  (spec §7); only `mark_step_complete` (which now goes through
  `can_complete_step`) can write a `completed` status.
* Scholarship selection — unchanged.
* ORM columns / migrations — none needed. `awaiting_documents` is a
  string value in the existing VARCHAR(30) status column.

## Verification

32 individual checks pass:

* `is_evidence_step` correctly classifies:
  - 9 soft steps (essays, references, leadership, eligibility check,
    track decision, motivation letter, research proposal, submit
    application, review answers)
  - 1 explicit-document step (gather_academic_documents with
    `required_documents=["transcripts","ielts_score"]`)
  - 7 Pakistan steps (HEC, IBCC, MOFA, PCC, passport, TB, NADRA)
  - 6 profile-driven steps (CAS, LOA, Zulassung, proof of funds × 3)
* `can_complete_step` for evidence steps:
  - `awaiting_documents` → False
  - `pending_verification` → False (with a reason that, in production,
    includes the missing doc names from `step.status_reason`)
  - `needs_attention` → False
  - All required docs verified + `ready_to_complete` → True
  - Partial (1 of 2 verified) → False with names of the missing doc
  - `locked` / `blocked` → False (spec §7)
  - Already `completed` → True (idempotent)
* `can_complete_step` for soft steps:
  - `available` / `in_progress` / `pending` → True
  - `locked` / `blocked` → False
* Profile-driven CAS step:
  - `ready_to_complete` (intrinsic from strong offer) → True
  - `available` (no offer signal) → False
  - Correctly classified as evidence (no "Mark as prepared")

All 63 Python files compile; all cross-file imports resolve.

## Deployment

```powershell
cd C:\path\to\visaforge
streamlit run app.py
```

No DB migration. No data reset. Existing route plans will recompute
their statuses on next page load — Pakistan steps that had
`required_documents=[]` will now have `[<process_id>]` populated
inside the in-memory plan, and the evidence overlay will move them
to `awaiting_documents` until the user uploads.

If any existing persisted plan rows have stale "Mark as prepared"
expectations, the v0.10.1 `recompute_states_for_plan` (already
called on every Route Plan page load) brings them back into sync.

## Manual smoke test (the exact bug scenario)

1. Generate a UK Chevening route plan.
2. Scroll to **Section B — Pakistan Preparation Phase**.
3. Each Pakistan step (HEC, IBCC, etc.) should now show:
   - Status pill: 📤 `awaiting_documents`
   - "Upload the required document(s) below to move this step forward."
   - Upload controls visible
   - **No "Mark as prepared" button**
4. Upload an HEC attestation file and let verification run.
5. Once verified, the step transitions to 🟢 `ready_to_complete`
   and the **"✅ Mark as Complete"** button appears.
6. Click it — step becomes ✅ completed.
7. Compare with **Section A — Scholarship Application Phase**:
   - Soft steps (essays, references, leadership) show "Mark as
     prepared" when `available`. They have no upload controls.
   - Evidence step `gather_academic_documents` shows upload
     controls + `awaiting_documents` until docs are verified.
