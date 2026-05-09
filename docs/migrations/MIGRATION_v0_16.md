# VisaForge v0.16 — Phase 5.7 Post-Pivot Document Workflow Cleanup

This is a workflow cleanup release on top of the v0.15 architectural
pivot. It fixes four concrete bugs reported after v0.15 and adds CNIC
OCR support that was missing.

## Issues fixed

| # | Issue | Fix |
|---|---|---|
| 1 | Dashboard journey was stuck on "Upload documents" | Removed document upload as a journey gate (spec §1) |
| 2 | Documents showed raw "pending" / "manual_review_required" labels | Friendly status display layer maps the enum to "Processed" / "Needs review" / "Couldn't read" (spec §2) |
| 3 | CNIC OCR text was messy | Image preprocessing (grayscale + 2x upscale + autocontrast + sharpen + `--psm 6`) plus expanded NADRA field extractor with OCR-mistake-tolerant CNIC pattern (spec §5, §6) |
| 4 | `Reprocess OCR` crashed on `'CaseDocument' object has no attribute 'confirmed_by_user'` | Defensive `getattr` reads + try/except writes; new `confirmation_note` column added with safe SQLite migration (spec §3, §4) |

Plus: NADRA advisory verifier with the spec §7 mandated warning text,
and an "I reviewed this document" self-review button (spec §8).

## Files changed

### `models/orm.py`
Added `confirmation_note` (Text, nullable) to `CaseDocument`. The user
can attach a free-text note when they click "I reviewed this document",
e.g. "translated copy" or "original on file at home".

### `db/init_db.py`
- Added `confirmation_note` to the additive migration list.
- Relaxed `confirmed_by_user` from `BOOLEAN DEFAULT 0 NOT NULL` to
  `BOOLEAN DEFAULT 0`. SQLite happily accepts the default for existing
  rows when the column is added, but if a partial v0.14 deployment
  ever inserted NULL into this column, retroactive NOT NULL would
  fail. The SQLAlchemy mapping still declares NOT NULL, so new writes
  are guarded.

### `services/journey_service.py`
- `JourneyStatus.stage_flags()` no longer includes "Upload documents".
  Five gates remain: profile, destination, eligibility, scholarship,
  route plan.
- `JourneyStatus.current_step()` no longer chains to
  `pages/5_Documents.py` after the route plan. Once all five gates are
  met, the user is sent to the route plan to continue working on
  individual steps.

### `pages/7_Dashboard.py`
- "Continue with documents" card copy updated — no more "your route
  plan unlocks more steps as documents are verified" (that was the
  v0.11–v0.14 model and is no longer how the system works).
- New "📄 Optional: Documents" tile rendered once the route plan is
  generated. Frames documents as a supporting workspace, never a
  gate.

### `services/document_service.py`
- `reprocess_document` reads `row.confirmed_by_user` via `getattr`
  with a `False` default, and wraps writes to `confirmed_by_user` /
  `confirmed_at` in `try/except` so a legacy DB without the column
  no longer crashes the reprocess flow.
- `confirm_document_manually` accepts an optional `note` parameter and
  refuses ONLY on `extraction_failed` status (was previously refusing
  on `verified` / `rejected` / `needs_attention` too — spec §8 wants
  the "I reviewed" button to work for any non-extraction-failed
  document).
- Hydrator `_evidence_to_dto` exposes `confirmation_note`.

### `services/document_processing_service.py`
- New `_preprocess_image_for_ocr(image)` helper:
  * Convert to grayscale
  * Upscale 2x if either dimension is below 1500 px (mobile snaps of
    CNICs are typically 800–1200 px wide)
  * `ImageOps.autocontrast(cutoff=2)` then `ImageFilter.SHARPEN`
  * Falls back to the input image on any failure
- `_extract_image_text` invokes the preprocessor and uses
  `pytesseract --psm 6` (uniform block of text) with PSM 3 fallback
  if PSM 6 returns nothing. Documents like CNICs and certificates
  parse much better at PSM 6.
- `_extract_nadra` expanded per spec §6:
  * `applicant_name` via a new NADRA-specific regex (matches a bare
    `Name:` line; the existing `_APPLICANT_NAME_RX` only matched
    "Applicant name" / "Holder" / "Bearer")
  * `father_name` via `Father Name` / `S/O` / `D/O` line
  * `date_of_birth`, `date_of_issue`, `date_of_expiry` via
    DOB / DOI / DOE regexes (all routed through `_try_parse_date`)
  * OCR-mistake-tolerant CNIC variant: a relaxed `_CNIC_OCR_VARIANTS_RX`
    accepts O/I/B/S/Z/Q/l in any digit position, then a translation
    table repairs them to digits. If the result has 13 digits, the
    repaired CNIC is stored and `cnic_ocr_repaired=True` is flagged.

### `services/document_verification_service.py`
- New `_verify_nadra` advisory verifier per spec §7:
  * Status: `manual_review_required` when keywords or CNIC pattern
    present; `needs_attention` when neither found; `extraction_failed`
    on empty fields.
  * Emits the spec §7 EXACT warning: "Document appears to be a
    Pakistan identity document, but automated OCR cannot verify
    authenticity. Review manually."
  * Soft warnings: name mismatch with profile; expired CNIC; OCR
    digits repaired (so the user re-checks the number).
  * Matched fields surfaced: `pakistan_identity_keywords`,
    `cnic_pattern`, `applicant_name`, `father_name`, `date_of_birth`,
    `date_of_issue`, `date_of_expiry`.

### `models/schemas.py`
- `DocumentEvidenceDTO.confirmation_note` (Optional[str]) added.

### `services/route_plan_service.py`
- Hydrator passes `confirmation_note` to the DTO.

### `pages/5_Documents.py`
- Per-document status pill now uses a friendly display map (spec §2):
  * `verified` / `user_confirmed` / `admin_verified` → **Processed**
  * `manual_review_required` / `needs_attention` / `pending` →
    **Needs review**
  * `extraction_failed` / `rejected` → **Couldn't read**
- Upload-success flash uses the friendly label instead of the raw
  enum.
- New "I reviewed this document" expander on each card (spec §8):
  * Available for any non-extraction-failed document
  * Optional free-text note
  * On submit → `confirm_document_manually` flips status to
    `user_confirmed`, sets `confirmed_by_user=True`,
    `confirmed_at=now`, persists the note
  * Already-reviewed documents show a passive blue acknowledgement
    with the disclaimer "VisaForge has not independently verified it"

## Verification — 36 / 36 checks pass

**§7 NADRA advisory verifier (11/11):**
- Happy path → `manual_review_required` with the spec-§7 EXACT
  warning text
- Pakistan-identity / CNIC-pattern / name / father / DOB matched
- No markers → `needs_attention`
- OCR-repaired CNIC → soft warning emitted
- Name mismatch → soft warning
- Expired CNIC → soft warning
- Empty fields → `extraction_failed`

**§6 NADRA extractor (9/9):**
- All seven CNIC fields extracted from a clean OCR text
- OCR-repaired CNIC: `42IO1-1234567-l` → `42101-1234567-1`
- `cnic_ocr_repaired` flag set when (and only when) repair happened

**§5 image preprocessing (4/4):**
- Non-PIL input returns unchanged (no crash)
- Small image upscaled 2x
- Image converted to grayscale
- Large image kept at original size

**Source-level cross-checks (12/12):**
- Journey service has no "Upload documents" left
- ORM declares `confirmation_note`; migration adds it
- Migration relaxed retroactive `NOT NULL`
- `reprocess_document` uses `getattr` defensive read
- `confirm_document_manually` accepts `note` kwarg
- Documents page imports `confirm_document_manually`
- Documents page shows "Processed" / "Needs review" / "Couldn't read"
- Documents page renders the "I reviewed this document" panel
- Dashboard frames documents as optional, gated on
  `route_plan_generated`

**Plus:** all 63 Python files compile, all cross-file imports resolve.

## Deployment

```powershell
cd C:\path\to\visaforge
streamlit run app.py
```

The migration runs automatically on app start. SQLite gets the new
`confirmation_note` column added via additive `ALTER TABLE`. No
destructive reset.

If for some reason the automatic migration doesn't run, the manual
PowerShell equivalent is:

```powershell
sqlite3 .\visaforge.db "ALTER TABLE case_documents ADD COLUMN confirmation_note TEXT;"
```

`db/init_db.py` is idempotent — running this manually before the app
boots is also safe.

## Manual smoke test

1. Open the Dashboard. The journey progress shows **5** stage tiles
   (no longer 6). "Upload documents" is gone.
2. Once you've generated a route plan, the dashboard's main next-
   action card is "Continue working through your route plan", and a
   secondary "📄 Optional: Documents" tile appears below it.
3. Open the Documents page. Upload a CNIC scan or photo:
   - Image is preprocessed (grayscale + upscale + sharpen) before OCR
   - Field extraction now pulls `cnic_number`, `applicant_name`,
     `father_name`, `date_of_birth`, `date_of_issue`,
     `date_of_expiry`
   - If Tesseract misread some digits, you'll see a yellow warning
     about repaired digits — verify the CNIC against your card
   - Status pill reads **🟡 Needs review** (not "manual_review_required")
   - The exact spec §7 warning is shown: "Document appears to be a
     Pakistan identity document, but automated OCR cannot verify
     authenticity. Review manually."
4. Click **🔧 Reprocess OCR**. No more crash on `confirmed_by_user`.
   Re-extraction runs and the status updates.
5. Expand **👤 I reviewed this document**. Type an optional note like
   "verified against my physical CNIC". Click Confirm.
   - Status pill becomes **👤 Processed (you reviewed)**
   - A blue acknowledgement reads: "You reviewed this document.
     VisaForge has not independently verified it."
   - Your note is shown below.

## What did NOT change

- OCR for non-image documents (PDF text extraction)
- Route Plan / step completion logic (still the v0.15 four-state
  pipeline)
- AI assistant
- Authentication / profile / eligibility / scholarship / admin
- Source ingestion
