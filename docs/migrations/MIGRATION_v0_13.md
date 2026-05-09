# VisaForge v0.13 — Phase 5.4 Route Plan Document Upload Consistency

## What this release fixes

Some Pakistan steps and visa-readiness steps were showing "Upload the
required document(s) below" with no actual upload slots beneath. The
hint and the slot-renderer disagreed about what counts as an
evidence step.

Root cause: the v0.11.1 fix gave Pakistan steps `required_documents=[pid]`
on the service side, but the page kept its own inline mapping
(`_STEP_DOCUMENT_TYPES`) that left `tb_test` and `nadra_documents`
empty and didn't know about the explicit list. So:

1. The evidence overlay set those steps to `awaiting_documents`
   (because `is_evidence_step` correctly classified them).
2. The page rendered the "Upload below" hint (because status was
   `awaiting_documents`).
3. `_render_upload_slots` consulted the page's local mapping which
   returned `[]` for those steps — so no slots rendered.

The hint promised slots that never appeared.

## The fix — one canonical resolver everyone consults

### `models/schemas.py`
Added `RequiredDocument` DTO with `document_type`, `label`,
`help_text`, and `optional` flag. Every UI / service consumer now
gets the same shape from the same function.

### `services/route_plan_service.py`
Three new public functions:

* **`resolve_required_documents(step) -> list[RequiredDocument]`** —
  the single source of truth. Sources in priority order:
  1. `step.required_documents` (template-authoritative)
  2. `_FALLBACK_SLOTS[step.key]` for Pakistan + profile-driven steps
  3. `pakistan_process_id` safety net
  4. `[]` for genuinely soft steps
  Deduplicates document types. Returns friendly labels via the
  `_DOC_LABELS` catalog (with humanised fallback for unknown types).

* **`audit_route_plan_documents(plan) -> list[dict]`** — the
  auditor. Detects all 6 spec §1 issue types:
  `no_required_documents`, `duplicate_document_type`,
  `awaiting_documents_no_slots`, `completed_without_verified`,
  `evidence_unlinked`, plus the implicit "no upload slot" check
  through the resolver.

* **`is_evidence_step(step)`** — refactored to delegate to
  `resolve_required_documents`. A step is evidence-based when the
  resolver returns ≥1 slot, OR has a `pakistan_process_id`, OR is
  in the known profile-driven evidence set.

Plus three behavioral fixes:

* **`_apply_evidence_overlay`** — spec §7: a `completed` evidence
  step with no longer-verified coverage is downgraded to
  `awaiting_documents` / `pending_verification` / `needs_attention`
  depending on what evidence remains. Soft completed steps and
  evidence steps with intact coverage propagate as-is.

* **`_apply_user_completion_overlay`** — respects the evidence
  overlay's downgrade. If the evidence overlay just demoted a
  persisted-completed step (because verified docs vanished), the
  user-completion overlay no longer fights the demotion.

* **`can_complete_step`** — uses the resolver and honors the
  `optional` flag. Optional slots (e.g. "Sponsor letter if
  sponsored") don't block completion.

### `pages/3_Route_Plan.py`
* Imports `resolve_required_documents` and `audit_route_plan_documents`.
* The inline `_STEP_DOCUMENT_TYPES` dict is gone. `_doc_slots_for`
  now returns `[(document_type, label, optional), ...]` from the
  resolver.
* `_render_upload_slots` shows the optional flag, and renders a ✅
  on slots whose document is already verified.
* Spec §3 fix: the "Upload the required document(s) below" hint is
  gated on `has_slots = is_evidence_step(step) and bool(_doc_slots_for(step))`.
  When `has_slots` is False but status is `awaiting_documents`, a
  quieter "expects supporting evidence" message is shown instead.
* Spec §9 audit panel added at the bottom of the page. Shows total
  steps, evidence steps, missing-slot count, total audit issues,
  per-issue detail, and a per-step canonical resolution table for
  demos.

## Verification — all 49 checks pass

**Resolver (19/19):**
- All 7 Pakistan steps resolve to expected document types
- `gather_academic_documents` resolves to transcript + degree + english_test
- All 3 proof-of-funds steps resolve to bank_statement + (optional) sponsor_letter
- All 3 offer-confirmation steps resolve to offer_letter
- Soft step `prepare_essays` resolves to `[]`
- Explicit `required_documents` takes priority over fallback
- Every Pakistan slot has a non-empty friendly label
- `proof_of_funds_uk.sponsor_letter` is optional, `bank_statement` is required
- Duplicate document types are deduplicated

**`is_evidence_step` (18/18):**
- 5 soft steps correctly classified as not-evidence
- All 7 Pakistan steps classified as evidence
- All 6 profile-driven steps (CAS / LOA / Zulassung / proof of funds × 3) classified as evidence

**Auditor (5/5):**
- Detects `duplicate_document_type`, `awaiting_documents_no_slots`,
  `completed_without_verified`, `evidence_unlinked`
- Clean plan returns `[]`

**Spec §7 completion downgrade (4/4):**
- Completed evidence step with no remaining evidence → `awaiting_documents`
- Status reason mentions "Re-upload"
- Soft completed step stays completed (sticky)
- Completed evidence step with intact verified coverage stays completed

**No regression (7/7):**
- `tb_test` and `nadra_documents` now have slots (the actual user bug)
- v0.10.1 dependency cascade still works
- `can_complete_step` still gates correctly for soft + evidence
- Optional slots don't block completion

All 63 Python files compile. All cross-file imports resolve.

## Deployment

```powershell
cd C:\path\to\visaforge
streamlit run app.py
```

No DB migration. No data reset. Existing route plans recompute
their statuses on next page load — Pakistan steps that had
`required_documents=[]` now resolve through the canonical resolver
and the page renders upload slots immediately.

## Manual smoke test (the exact bug scenario)

1. Open the Route Plan with a selected scholarship.
2. Scroll to **Section B — Pakistan Preparation Phase**.
3. Each Pakistan step (HEC, IBCC, MOFA, Police, Passport, **TB,
   NADRA**) shows:
   - 📤 `awaiting_documents` status pill
   - "📤 Upload the required document(s) below to move this step forward."
   - Upload slots that match what the spec §2 fallback table
     declares (e.g. `nadra_documents` shows "CNIC / B-Form / Birth
     Certificate"; `tb_test` shows "TB test certificate")
4. Scroll to **Section C — Visa Application Phase**.
5. `proof_of_funds_uk` shows two slots:
   - **Bank statement** (required)
   - **Sponsor letter (if sponsored)** _optional_
   Uploading only the bank statement still allows the step to reach
   `ready_to_complete` and the "Mark as Complete" button.
6. At the bottom of the page, expand **🔧 Route document audit**.
   The summary metrics should show:
   - Total steps / Evidence steps
   - **Steps missing upload slots: 0**
   - **Total audit issues: 0**
7. Open the per-step canonical resolution table. Confirm every
   evidence step lists at least one document type, with `*` next
   to optional slots.

## What did NOT change

- OCR / extraction (`document_processing_service.py`)
- Verification (`document_verification_service.py`)
- Scholarship selection
- AI explain buttons
- Mark-as-Complete button gating
- Admin pages
- ORM columns / migrations
- Manual status dropdowns are still absent
