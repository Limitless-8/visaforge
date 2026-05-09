# VisaForge v0.15 — Phase 5.6 Architectural Pivot

This is a **design pivot**, not a patch. The previous Phase 5.5 work
tightly coupled Route Plan with document verification — uploads,
OCR, extraction, manual confirmation, and verification status all
drove route step status. That coupling was the wrong abstraction. It
made the system fragile and hard to demo.

v0.15 separates concerns:

* **Route Plan** = guidance + execution tracking
* **Documents** = upload + OCR + extraction + document intelligence
* **AI** = explanation layer

The user marks steps complete with one click. Documents are an
independent workspace. The AI explains things on demand.

## What this release changes

| Concern | v0.11–v0.14 (before) | v0.15 (after) |
|---|---|---|
| Mark a step complete | Required documents had to be uploaded AND verified (or user-confirmed) | Click "Mark as Complete" — done |
| Step status enum | 11 states including `awaiting_documents`, `pending_verification`, `pending_user_confirmation`, `needs_attention`, `ready_to_complete` | Just 4: `locked`, `available`, `completed`, `blocked` |
| Upload widgets | Inline on every Route Plan step | Removed from Route Plan; live on Documents page only |
| Verification | Gating signal for completion | Optional insight; never blocks progress |
| Documents page | Vault / overview | Central workspace — uploads, OCR, fields, AI explanations |
| AI integration | "Explain step" / "Explain issues" | Adds "Ask AI about this document" with focused prompt |

## Files changed

### `models/schemas.py`
`RouteStepStatus` literal narrowed:
- v0.15 statuses: `locked`, `available`, `completed`, `blocked`
- Legacy values (`pending`, `in_progress`, `awaiting_documents`,
  `pending_verification`, `pending_user_confirmation`,
  `needs_attention`, `ready_to_complete`) retained ONLY as aliases
  for back-compat with persisted RouteStep rows from v0.11–v0.14.
  The pipeline never produces these; on read it upgrades them.

### `services/route_plan_service.py`
- Removed broken `EVIDENCE_SATISFIED_STATUSES` import (was never
  exported from schemas — the file did not load before this fix).
  Defined as a module-private frozenset for the legacy helpers that
  still reference it.
- `_intrinsic_status`: profile-driven completion (CAS / LOA /
  Zulassung from `offer_letter_status` strong; proof_of_funds_*
  from `proof_of_funds_status` strong) preserved. Document-driven
  completion (Pakistan step → completed if doc uploaded;
  required_documents → completed if all uploaded) **removed** —
  documents no longer drive completion. Pakistan and document-list
  steps default to `available`.
- `generate_plan` pipeline order changed:
  1. intrinsic status (profile + eligibility)
  2. user-completion overlay (force `completed` from persisted
     `RouteStep.completed_at IS NOT NULL`)
  3. dependency resolver (cascade locks + unlocks)
  4. legacy-status upgrade pass (any persisted v0.11–v0.14 status
     not in the v0.15 set is rewritten to `available`)
  Pass 2 in v0.14 was `_apply_evidence_overlay` — that overlay
  is **no longer called by the live pipeline**. The function is
  retained as a private helper for future use; the v0.13 audit
  panel still imports it indirectly.
- `can_complete_step` simplified: only `locked` and `blocked`
  refuse. `completed` returns idempotent True. Everything else
  returns True. No document checks.
- `mark_step_complete` unchanged — it already delegated to
  `can_complete_step`, so it inherits the simplification.
- v0.10.1 dependency cascade preserved.
- v0.13 `resolve_required_documents` and `audit_route_plan_documents`
  preserved — used by the Documents page (suggested types when
  arriving from a Route Plan handoff) and the audit panel.

### `pages/3_Route_Plan.py`
Full rewrite (1043 → ~370 lines).
- No upload widgets, no extraction display, no verification debug
  panels, no `awaiting_documents` machinery.
- Each step shows: title, description, status pill (4 v0.15 statuses
  + defensive legacy fallbacks), priority, dependencies, Pakistan
  inline help, **required documents as REFERENCE LIST only** (label
  + document_type + optional flag, no upload UI), and three action
  buttons: **Mark as Complete** / **📎 Upload related document** /
  **🤖 Ask AI about this step**.
- "Upload related document" stashes
  `st.session_state["doc_step_context"] = {step_key, step_title,
  suggested_document_types}` then `st.switch_page("pages/5_Documents.py")`.
- "Ask AI" stashes `RouteStepContext(profile_id, step_key,
  kind="explain")` and switches to AI Assistant.
- Top-of-page "Continue current step" CTA via
  `get_next_actionable_step`.

### `pages/5_Documents.py`
Already largely in v0.15 shape from prior work. Updated:
- "Ask AI" button on each document card now uses
  `RouteStepContext(kind="document", document_id=ev.id)` so the AI
  assistant gets a focused document-content prompt instead of the
  generic "explain step" prompt.

### `services/ai_service.py`
- `RouteStepContext.step_key` now optional (default ""). Allows
  free-form "Ask AI about this document" handoffs from the
  Documents page where there's no related step.
- New `kind="document"`: composes a prompt that asks the AI to
  explain the document content, highlight missing info, and
  describe how it relates to the visa process. The prompt
  explicitly tells the AI **not** to claim authenticity / validity
  (spec §7).

### `services/document_service.py`
Unchanged at the API level — the v0.14 canonical functions
(`get_document_for_slot`, `list_documents_for_step`,
`save_uploaded_document`, `delete_document`, `reprocess_document`,
`confirm_document_manually`) are still exported and now used by
the Documents page (not Route Plan).

### `services/document_processing_service.py` and
### `services/document_verification_service.py`
**Unchanged.** OCR, extraction, and verification still work. Per
spec §6, verification still runs on upload but is informational
only — it adds warnings to a document card; it does not gate any
route step.

## Verification — 26 / 26 checks pass

**Spec §2 — `can_complete_step` minimal gate (8/8):**
- `available` → completable
- evidence step + no docs → completable
- evidence step + pending docs → completable
- `locked` → refused
- `blocked` → refused
- `completed` → idempotent True
- legacy `awaiting_documents` → still allowed
- legacy `needs_attention` → still allowed

**Spec §6 — `_intrinsic_status` no longer doc-driven (6/6):**
- Pakistan step + uploaded doc → `available` (not `completed`)
- Doc-driven step + all uploaded → `available` (not `completed`)
- Profile offer=strong → `completed` (preserved)
- Profile funds=strong → `completed` (preserved)
- NOT_ELIGIBLE on visa → `blocked`
- NOT_ELIGIBLE on scholarship → NOT blocked

**v0.10.1 cascade preserved (1/1):**
- step2 unlocks when step1 completes

**v0.13 resolver preserved (7/7):**
- All 7 Pakistan steps resolve to expected document types with
  friendly labels (HEC + degree_certificate + transcript;
  TB → tb_test; NADRA → nadra_documents; passport → passport;
  IBCC, MOFA, police each return their own type)

**v0.13 audit panel preserved (1/1):**
- Clean plan returns `[]`

**v0.15 `get_next_actionable_step` (2/2):**
- Picks `available` over `locked`
- All completed → returns None

**`is_evidence_step` preserved (1/1):**
- Pakistan step IS evidence; soft step is NOT

**Plus:** all 63 Python files compile, all cross-file imports resolve,
zero forbidden patterns (`file_uploader`, `process_upload`,
`verify_document`, `attach_document_to_step`, `extracted_text`,
`extraction_status`, `verification_status`) in `pages/3_Route_Plan.py`.

## What did NOT change

- Authentication
- Profile system
- Eligibility engine
- Scholarship matching
- Admin approval system
- Source ingestion
- AI assistant page itself
- ORM / database schema (no new columns; v0.14 `confirmed_by_user`
  / `confirmed_at` / `confirmed_by_admin_id` are retained but
  unused by the route plan)

## Deployment

```powershell
cd C:\path\to\visaforge
streamlit run app.py
```

**No DB migration needed.** No data reset. Existing persisted
`RouteStep` rows with legacy statuses (`awaiting_documents`,
`pending_verification`, etc.) are rewritten to `available` by the
route service's upgrade pass on next plan load.

## Manual smoke test

1. Open the Route Plan with a selected scholarship.
2. Pick any non-completed step (say `hec_attestation` in Section B).
3. Confirm:
   - Status pill is `available` (not `awaiting_documents`)
   - Required documents appear as a **reference list** (label +
     document_type + optional flag), no upload widget anywhere
   - Three buttons: Mark as Complete / Upload related document /
     Ask AI about this step
4. Click **📎 Upload related document**. Page switches to Documents.
   - Top of Documents page shows: "📎 Suggested for **HEC
     attestation**: HEC attestation evidence, Degree certificate,
     Transcript"
   - Document type dropdown is pre-selected with the first
     non-optional suggested type
5. Upload any PDF or image. OCR + extraction runs. Verification
   may add warnings — but no blocking, no gating, no required
   confirmation.
6. Click **🤖 Ask AI** on a document card. AI Assistant opens with
   a focused prompt explaining the document content (not claiming
   authenticity).
7. Go back to Route Plan, click **✅ Mark as Complete** on the
   `hec_attestation` step. It moves to `completed` immediately —
   no document gating, no verification blocking.
8. Step's dependents (if any) unlock via the v0.10.1 cascade.
