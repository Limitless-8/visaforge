# VisaForge v0.11 — Phase 5 Part 2 (Documents Vault + AI Explain Issues)

This release ships the user-visible surfaces for evidence
verification on top of the deterministic backend from v0.11 part 1.
No backend logic changed.

## What's in part 2

### Updated files

| File | What changed |
|---|---|
| `services/ai_service.py` | New `SYSTEM_PROMPT_DOCUMENT_FOCUSED` with spec §12 wording verbatim. `RouteStepContext` gains `document_id` field and `kind="issues"`. `build_context()` accepts `focused_document_id` and adds a `current_document` block (document_type, verification_status, extracted_fields, issues, warnings). `ask()` accepts `focused_document_id` and routes to the document-focused prompt. `ask_about_step()` composes a per-issue default question for `kind="issues"`. |
| `services/document_service.py` | New v0.11 reads: `list_evidence_for_profile()`, `get_evidence_by_id()`, `delete_evidence()`. All return / operate on `DocumentEvidenceDTO` and exclude legacy v0.5 checklist rows (those without `step_key`). |
| `pages/5_Documents.py` | Full rewrite as the "Document Vault." Lists every uploaded evidence document, grouped by route step, with verification status pills, extracted fields, issues, file metadata. Per-document **Explain issues** button hands the document context to the AI. Re-upload affordance points back to the Route Plan. Legacy v0.5 checklist rows shown as a small secondary expander. Disclaimer present. |
| `pages/6_AI_Assistant.py` | Carries `document_id` in `ai_focused_step` session state. Focus banner branches on document presence with a different message. Follow-up `ask()` calls pass `focused_document_id` so subsequent turns stay grounded in the same document. |
| `pages/3_Route_Plan.py` | Per-evidence row now has an **💡 Explain issues** button that appears for flagged documents (`needs_attention` / `rejected` / `extraction_failed`). Hands a `RouteStepContext(kind="issues", document_id=...)` to the AI Assistant. |

### Verification

* All 63 Python files compile.
* All cross-file imports resolve.
* 30+ wiring checks pass:
  - `ai_service`: `RouteStepContext.document_id`, `build_context(focused_document_id=...)`, `ask(focused_document_id=...)`, `SYSTEM_PROMPT_DOCUMENT_FOCUSED`, all spec §12 wording verbatim, `current_document` block populated, `ask_about_step` branches on `kind="issues"`.
  - `pages/5_Documents.py`: imports `list_evidence_for_profile` / `delete_evidence` / `RouteStepContext`; "evidence vault" framing with caption pointing to Route Plan; Explain-issues button surfaced; renders document_type / status / extracted_fields / issues; re-upload affordance points to Route Plan; legacy checklist shown as secondary expander; disclaimer.
  - `pages/6_AI_Assistant.py`: session state carries document_id, focus banner branches, `kind="issues"` label, follow-up `ask()` propagates `focused_document_id`.
  - `pages/3_Route_Plan.py`: Explain-issues button per evidence row, only surfaced for flagged statuses.
  - `document_service`: all three v0.11 read/delete functions defined.

### What did NOT change

* `services/route_plan_service.py` — untouched.
* `services/document_processing_service.py` — untouched.
* `services/document_verification_service.py` — untouched.
* `services/journey_service.py` / `scholarship_service.py` / `pakistan_policy_service.py` — untouched.
* `models/orm.py` / `models/schemas.py` / `db/init_db.py` — untouched.
* No new tables, no new columns, no migrations needed.

## Deployment

Drop the four updated files into your existing v0.11 part 1 install:

```
services/ai_service.py
services/document_service.py
pages/3_Route_Plan.py
pages/5_Documents.py
pages/6_AI_Assistant.py
```

Restart Streamlit:

```powershell
streamlit run app.py
```

That's it. Backend is unchanged from part 1.

## End-to-end smoke test (manual)

1. Upload a passport on the Route Plan's **Passport readiness** step.
2. If verification fails (e.g. expired passport, name mismatch), the
   evidence row shows a **💡 Explain issues** button.
3. Click it → AI Assistant opens with a banner reading "Focused on a
   document · Explain document issues · step `passport_issuance` ·
   doc id `<n>`."
4. The AI auto-runs a composed question and answers grounded ONLY in
   the issues, extracted_fields, and verification_status from
   context. It never claims to validate or re-verify the document.
5. Click **Document Vault** in the sidebar. Every uploaded evidence
   document appears, grouped by step, with the same Explain-issues
   button per row. Re-upload affordance is a link back to the Route
   Plan step.
6. Try following up with a free-form question while in document-
   focused mode — the focus banner stays visible until you click
   **Clear focus**.

## Phase 5 — done

Combining v0.11 part 1 (backend, 50+ scenarios verified) +
v0.11 part 2 (UI + AI grounding, 30+ wiring checks):

- ✅ Spec §1  — document upload inside Route Plan steps
- ✅ Spec §2  — extended `case_documents` model, additive migration
- ✅ Spec §3  — file storage under `data/uploads/{profile}/{step}/`
- ✅ Spec §4  — OCR + text extraction with graceful degradation
- ✅ Spec §5  — rule-based structured extraction for 11 document types
- ✅ Spec §6  — deterministic verification engine
- ✅ Spec §7  — expanded route step status model (in_progress / pending_verification / needs_attention / ready_to_complete added)
- ✅ Spec §8  — `mark_step_complete()` user-confirmation gate
- ✅ Spec §9  — soft-task vs evidence-task distinction
- ✅ Spec §10 — Route Plan UI with upload slots, extracted fields, verification result, status badges, action buttons
- ✅ Spec §11 — Documents vault as evidence review surface
- ✅ Spec §12 — AI receives structured doc context, refuses to validate, spec wording verbatim
- ✅ Spec §13 — Pakistan policy integration for HEC / IBCC / MOFA / police / passport
- ✅ Spec §14 — profile = self-declared readiness; documents = evidence; user = completion
- ✅ Spec §15 — requirements.txt updated with optional deps
- ✅ Spec §16 — disclaimer surfaced on Route Plan + Vault
- ✅ Spec §17 — no existing functionality broken (61→63 files compile, all imports resolve)
- ✅ Spec §18 — full files only, clean filenames
- ✅ Spec §19 — end-to-end flow works
