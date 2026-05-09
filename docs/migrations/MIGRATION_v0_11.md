# VisaForge v0.11 — Phase 5 Part 1: Evidence-Centred Document Verification

This release transforms the Route Plan into an evidence-centred
workflow: each step that requires evidence has upload slots in-place,
documents are extracted (OCR + structured), verified deterministically
against the user profile, and only then can the user click
"Mark as Complete." **Part 2** (next release) ships the Documents
vault rewrite and the AI "Explain issues" path.

## What's in part 1

### New services

* **`services/document_processing_service.py`** — file capture +
  text extraction.
  - File save under `data/uploads/{profile_id}/{step_key}/` with
    safe filenames + automatic `_v2`, `_v3`, ... versioning to never
    overwrite.
  - PDF text extraction via PyMuPDF (preferred) or pdfplumber
    (fallback). Image OCR via pytesseract + Pillow.
  - **All optional dependencies degrade gracefully** — if a library
    or the Tesseract binary is missing, the user sees a clear message
    and the document is marked `extraction_failed` rather than
    crashing the page.
  - Rule-based structured extractors for 11 document types
    (passport, IELTS/TOEFL, bank statement, sponsor letter,
    transcript, degree certificate, police clearance, HEC / IBCC /
    MOFA evidence, offer letter).
  - File-type validation (PDF / PNG / JPG / JPEG only) and 10 MB
    size cap.

* **`services/document_verification_service.py`** — deterministic
  per-document verifier.
  - Returns a `VerificationResult` with `verification_status`
    (`pending` / `verified` / `rejected` / `needs_attention` /
    `extraction_failed`), matched fields, issues, warnings, and a
    `ready_for_completion` flag.
  - Cross-references extracted fields with the user's profile:
    name match, nationality match, expiry date in future, English
    score within 0.5 of profile, account holder name, statement
    age ≤ 90 days, etc.
  - Authority documents (HEC / IBCC / MOFA / police) check for the
    expected keywords AND fall back to `needs_attention` if absent.
  - **Readiness check, not legal validation** — the disclaimer is
    surfaced on the Route Plan page.

### Extended data model

* `models/orm.py` — `CaseDocument` extended with 12 new columns
  (user_id, step_key, document_type, original_filename, stored_path,
  mime_type, file_size, extracted_text, extracted_json,
  verification_status, issues_json, updated_at).
* `models/orm.py` — `RouteStep` gains `completed_at` (sticky
  user-confirmation timestamp).
* `models/schemas.py` — new `DocumentEvidenceDTO`, `VerificationResult`,
  `VerificationStatus` literal. `RouteStepStatus` literal expanded
  with 4 new states: `in_progress`, `pending_verification`,
  `needs_attention`, `ready_to_complete`. `DynamicRouteStepDTO`
  carries `evidence: list[DocumentEvidenceDTO]` and `is_evidence_task`.

### Route plan engine — two new overlay passes

* **Pass 3 (evidence overlay)** — after dependency resolution, layer
  evidence-derived statuses:
  - All required documents verified → `ready_to_complete`
  - Partial coverage → `pending_verification`
  - Any uploaded doc has issues → `needs_attention`
  - Hard gates (`locked` / `blocked` / `completed`) are NEVER
    overridden by evidence.

* **Pass 4 (user-completion overlay)** — sticky completion via
  `RouteStep.completed_at`. Once the user clicks Mark as Complete,
  the step stays completed regardless of later evidence drift.

* New writes:
  - `attach_document_to_step(...)` — persist a CaseDocument row
    keyed by step. Replaces any prior doc of the same type for the
    step (re-upload).
  - `mark_step_complete(profile_id, step_key)` — user-confirmation
    layer. Only accepts:
    - Evidence tasks at `ready_to_complete`
    - Soft tasks (no required_documents) at `available` /
      `in_progress` / `pending`
    - Returns `(ok, message)` so the UI can surface the gate reason.

### Route Plan page rewrite

`pages/3_Route_Plan.py` — every evidence-required step now shows
upload slots in-place. After upload, extracted fields and the
verification result render directly underneath. The "Mark as Complete"
button only appears when the deterministic engine has set the step to
`ready_to_complete` (or `available` for soft tasks). Inline Pakistan
policy details (requirements, steps, official source URL) appear for
Pakistan-side steps. Spec disclaimer is surfaced.

### Verification (50+ scenarios pass)

* **Document extractors** — passport / IELTS / bank / academic /
  police / HEC keywords / sponsor / offer letter all extract correctly
  from realistic-shape inputs.
* **Verifiers** — passport name match, expiry-in-future check,
  IELTS score match, bank balance + statement age, HEC keyword
  enforcement, extraction_failed short-circuit.
* **Evidence overlay** — locked stays locked, blocked stays blocked,
  partial coverage = pending_verification, full coverage =
  ready_to_complete, needs_attention propagates.
* **mark_step_complete gates** — refuses locked / unknown / no-plan
  cases; accepts soft tasks at available; soft-task path actually
  writes `completed_at`.
* **File save** — rejects .exe, empty, oversized; accepts valid
  PDF; auto-versions duplicate filenames.

## What's NOT in part 1 (coming in part 2)

These are the user-facing surfaces still on the v0.10 versions:

1. **`pages/5_Documents.py`** — Documents vault rewrite per spec §11
   (per-step grouping, evidence-vault framing, re-upload affordance)
2. **AI "Explain issues" path** — `services/ai_service.py` doesn't
   yet accept `verification_status` + `issues` blocks per spec §12.
   The Route Plan's "Explain this step" button uses the existing
   v0.10 path with `current_step` + `pakistan_process` blocks.

These don't unlock new functionality; they're surface polish on top
of what part 1 already delivers.

## Database migration

The bootstrap (`db/init_db.py → initialize()`) handles everything
automatically. All 12 new columns are nullable and additive.

You do **NOT** need to run any SQL by hand.

### If you want to run the migration manually

```powershell
# v0.11 columns on case_documents
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN user_id INTEGER;"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN step_key VARCHAR(80);"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN document_type VARCHAR(60);"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN original_filename VARCHAR(300);"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN stored_path VARCHAR(500);"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN mime_type VARCHAR(80);"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN file_size INTEGER;"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN extracted_text TEXT;"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN extracted_json TEXT;"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN verification_status VARCHAR(30);"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN issues_json TEXT;"
sqlite3 .\data\visaforge.db "ALTER TABLE case_documents ADD COLUMN updated_at DATETIME;"

# v0.11 column on route_steps
sqlite3 .\data\visaforge.db "ALTER TABLE route_steps ADD COLUMN completed_at DATETIME;"

# Verify
sqlite3 .\data\visaforge.db "PRAGMA table_info(case_documents);"
sqlite3 .\data\visaforge.db "PRAGMA table_info(route_steps);"
```

## Optional dependency setup

The new evidence-extraction libraries are listed in `requirements.txt`
but the Route Plan page falls back gracefully if any are missing.

```powershell
pip install -r requirements.txt
```

For OCR (pytesseract), you also need the **Tesseract binary**
installed on the host:

* Windows: https://github.com/UB-Mannheim/tesseract/wiki — install
  and ensure the Tesseract executable is on `PATH`.
* macOS: `brew install tesseract`
* Linux: `sudo apt-get install tesseract-ocr`

If Tesseract is missing, image uploads will surface a friendly
"OCR engine not found" message and the document will be marked
`extraction_failed`. PDFs with embedded text continue to work
without Tesseract.

## Deploy

Drop this zip's files into your existing v0.10 install:

```powershell
cd C:\path\to\visaforge
streamlit run app.py
```

The bootstrap migrates `case_documents` and `route_steps` additively.
No DB reset, no data loss.

## Smoke test

1. Sign in. Open the Route Plan.
2. Find a step with required documents (e.g. **Gather academic
   documents** in the scholarship phase, or **Passport readiness** in
   the Pakistan phase).
3. Upload a relevant PDF or image. Watch the spinner: read → extract →
   verify → status update.
4. If verified, **Mark as Complete** appears. Click it.
5. The toast "Step completed. Next step unlocked." appears, and the
   next dependent step's status is recomputed on the next render.
6. If the document has issues (e.g. expired passport, name mismatch),
   the step shows `needs_attention` with an expandable list of
   issues — and Mark as Complete does NOT appear.
