# VisaForge v0.12 — Phase 5.2 Document Pipeline Robustness

## What this release fixes

The previous v0.11.1 release fixed Route Step completion logic. This
release fixes the actual document reading / OCR / extraction /
verification pipeline so that uploaded documents end with one of the
five well-defined statuses — never a silent failure — and so the
Route Plan and Documents Vault surface enough diagnostic detail for
the user (and a supervisor demo) to see exactly where each stage
landed.

## Spec coverage

| Spec § | Title | Status |
|---|---|---|
| §1 | Robust pipeline (upload → save → text → fields → verify → store → show) | Done |
| §2 | PDF: PyMuPDF first, pdfplumber fallback, clear empty-text status | Done |
| §3 | Image OCR: Pillow + pytesseract, friendly Tesseract-missing message | Done |
| §4 | Store extracted_text / extracted_json / extraction_method / extraction_status / extraction_errors | Done |
| §5 | Structured field extraction for 8+ document types | Done |
| §6 | Date parsing: 5 formats + python-dateutil fallback | Done |
| §7 | Fuzzy name matching: 4-state classifier (matched / partial_match / mismatch / unknown) with optional rapidfuzz | Done |
| §8 | Verification logic returns full diagnostic shape | Done |
| §9 | Route Plan debug panel after upload | Done |
| §10 | Document Vault shows full pipeline visibility | Done |
| §11 | requirements.txt updated | Done |
| §12 | Tesseract install banner on Documents page | Done |
| §13 | DB patched additively, no destructive reset | Done |
| §14 | v0.11.1 step completion logic preserved | Done |
| §15 | Diagnostic logs at each stage | Done |

## Files changed

### `models/orm.py`
Added 6 new columns to `case_documents`, all nullable:
- `extraction_method` VARCHAR(40) — which library produced the text (`pymupdf`, `pdfplumber`, `pytesseract`, or empty)
- `extraction_status` VARCHAR(40), indexed — `ok`, `empty`, `failed`, `library_missing`, `tesseract_missing`, `unsupported_type`, `file_not_found`, `pending`
- `extraction_errors` TEXT — JSON-encoded list of diagnostic strings
- `warnings_json` TEXT — JSON-encoded list of soft warnings from verification
- `matched_fields_json` TEXT — JSON-encoded list of profile fields that matched extracted values
- `verified_at` DATETIME — when verification last ran

### `db/init_db.py`
Migration list extended with all 6 new columns. SQLite migration is
additive — no destructive reset.

### `models/schemas.py`
`DocumentEvidenceDTO` extended with `extraction_method`,
`extraction_status`, `extraction_errors`.

### `services/document_processing_service.py`
- `TextExtractionResult` dataclass extended with `status` and
  `errors` fields. Status enum implemented end-to-end.
- `_extract_pdf_text` annotates diagnostic for both PyMuPDF and
  pdfplumber paths.
- `_extract_image_text` distinguishes Pillow-missing vs
  pytesseract-missing vs Tesseract-binary-missing vs empty-output
  vs generic failure.
- `extract_text` dispatcher annotates `file_not_found` and
  `unsupported_type` with explicit status.
- `_try_parse_date` has a python-dateutil fallback for unusual
  formats (e.g. `Nov-07-2025`, `07.11.2025`, dates with surrounding
  noise like `"Date of issue: 7 Nov 2025 (Karachi)"`).
- `_GRAD_YEAR_RX` loosened to allow punctuation between the keyword
  and the year (so `Year of Graduation: 2022` is correctly
  captured).

### `services/document_verification_service.py`
- New `_classify_name_match(a, b)` 4-state classifier per spec §7
  returning `matched` / `partial_match` / `mismatch` / `unknown`.
  Uses rapidfuzz when available; pure-Python token logic otherwise.
- `_names_roughly_match` retained as a boolean wrapper.
- `verify_document` accepts `extraction_status` and
  `extraction_message` kwargs. When extraction failed, builds a
  status-specific friendly message — `tesseract_missing` gets the
  spec-required Windows-aware hint.

### `services/route_plan_service.py`
- `attach_document_to_step` accepts and persists `warnings`,
  `matched_fields`, `extraction_method`, `extraction_status`,
  `extraction_errors`.
- `_load_evidence_by_step` hydrates the new columns.

### `services/document_service.py`
- `_evidence_to_dto` reads warnings, matched_fields, and the 3
  extraction-visibility fields. Uses `getattr(d, ..., None)` for
  back-compat with v0.11 rows.

### `pages/3_Route_Plan.py`
- Upload flow passes the full verification result (issues,
  warnings, matched_fields) separately rather than concatenating.
- Debug panel after upload (auto-expanded for
  `extraction_failed` / `needs_attention` / `rejected`) shows file
  saved path + size, extraction method, extraction status,
  error_message, errors log, extracted text preview (first 1000
  chars), extracted fields JSON, verification status, issues,
  warnings, matched_fields.

### `pages/5_Documents.py`
- Full rewrite per spec §10. Each card shows: document type,
  linked route step, file name, mime, size, uploaded timestamp,
  extraction method, extraction status, verification status,
  matched-field badges, expandable extracted-fields, issues,
  warnings, extraction diagnostics, extracted text preview,
  re-upload-on-step link, delete action.
- Spec §12 top-level Tesseract install banner appears whenever any
  uploaded document has `extraction_status == 'tesseract_missing'`,
  with Windows-specific install hint.

### `requirements.txt`
- `rapidfuzz>=3.0.0` activated. Optional dependency — the
  verification service's pure-Python fallback runs when missing.

## Verification

All 63 Python files compile. All cross-file imports resolve.

The targeted v0.12 verification suite passes the following checks:

**Date parsing (9/9):**
- `2025-11-07` → `2025-11-07`
- `07/11/2025` → `2025-11-07`
- `07-11-2025` → `2025-11-07`
- `7 November 2025` → `2025-11-07`
- `November 7, 2025` → `2025-11-07`
- `Nov 7 2025` → `2025-11-07`
- `Date of issue: 7 Nov 2025 (Karachi)` → `2025-11-07` (dateutil fuzzy)
- `garbage text` → None
- `""` → None

**Field extraction (10/10):**
- Passport: passport_number, nationality, expiry_date, date_of_birth
- IELTS / English test: test_date
- Bank statement: balance, currency
- Academic: graduation_year (after the regex fix)
- HEC / IBCC / MOFA / Police: keyword detection works as expected

**Name matching (8/8):**
- Exact: `matched`
- Token reorder (Muhammad Ali Khan ↔ Ali Khan Muhammad): `matched`
- Middle initial filtered: `matched`
- Strict superset (Shehryar Khan ↔ Shehryar Mahmood Khan): `partial_match`
- Strict superset (Ali Khan ↔ Ali Khan Mahmood): `partial_match`
- Unrelated: `mismatch`
- Empty / None inputs: `unknown` (both sides)

**OCR graceful (3/3):**
- Image OCR returns cleanly even when Tesseract is missing
- Status field set correctly
- Status value is in the documented enum

**verify_document extraction-failed paths (4/4):**
- `tesseract_missing` → status=`extraction_failed`, issue mentions "Tesseract"
- `library_missing` → status=`extraction_failed`
- `empty` → status=`extraction_failed`
- All produce non-empty `issues` list

**Passport verification:**
- Future expiry + matching name + matching nationality → `verified`, full_name in matched_fields
- Expired passport → `needs_attention` or `rejected`

**HEC verification:**
- Missing keyword → `needs_attention`
- With keyword → `verified`

**Result shape contract:**
- `issues` is list, `warnings` is list, `matched_fields` is list
- `verification_status` is a string in the 5-value enum

## Deployment

```powershell
cd C:\path\to\visaforge
pip install -r requirements.txt
streamlit run app.py
```

The migration runs automatically on app start. SQLite gets the 6
new columns added via `ALTER TABLE case_documents ADD COLUMN ...`
on boot — additive, no destructive reset.

If for any reason the automatic migration doesn't run, the manual
PowerShell equivalent is:

```powershell
sqlite3 .\visaforge.db "ALTER TABLE case_documents ADD COLUMN extraction_method VARCHAR(40);"
sqlite3 .\visaforge.db "ALTER TABLE case_documents ADD COLUMN extraction_status VARCHAR(40);"
sqlite3 .\visaforge.db "ALTER TABLE case_documents ADD COLUMN extraction_errors TEXT;"
sqlite3 .\visaforge.db "ALTER TABLE case_documents ADD COLUMN warnings_json TEXT;"
sqlite3 .\visaforge.db "ALTER TABLE case_documents ADD COLUMN matched_fields_json TEXT;"
sqlite3 .\visaforge.db "ALTER TABLE case_documents ADD COLUMN verified_at DATETIME;"
```

`db/init_db.py` is idempotent — it skips a column that already
exists, so running these manually before the app boots is also safe.

## Tesseract OCR install (Windows)

The `pytesseract` Python package alone is not enough for image OCR.
The Tesseract OCR engine binary must also be installed and on PATH.

1. Download the latest Tesseract installer from
   https://github.com/UB-Mannheim/tesseract/wiki
2. Install (default path: `C:\Program Files\Tesseract-OCR`).
3. Add that directory to your `PATH`:
   ```powershell
   $env:Path += ";C:\Program Files\Tesseract-OCR"
   ```
   For a permanent fix, add it via System Properties → Environment
   Variables.
4. Verify with `tesseract --version` in a new PowerShell window.
5. Restart Streamlit and re-upload affected images.

**Or use text-based PDFs** — those don't need OCR.

## Manual smoke test

1. Open the Route Plan with a selected scholarship.
2. On `gather_academic_documents`, upload a transcript PDF.
3. Debug panel auto-expands and shows: file saved path + size,
   extraction method (`pymupdf` or `pdfplumber`), extraction status
   (`ok`), extracted text preview, extracted fields JSON,
   verification status, matched fields list.
4. Open Documents Vault — same document shows the same visibility.
5. Upload a JPG image. If Tesseract isn't installed, the debug
   panel shows extraction status = `tesseract_missing` with the
   friendly hint, and Documents Vault shows a top-level info
   banner with install instructions.
