"""
services/document_service.py
----------------------------
Document checklist + tracking.

For the MVP:
- checklist templates come from data/seeds/document_checklists.json
- uploads are not persisted to disk (file bytes handled in Streamlit only)
  — metadata and status are persisted.
- clean extension points are provided via
  services/document_extraction_service.py and services/ocr_service.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from config.settings import SEEDS_DIR
from db.database import session_scope
from models.orm import CaseDocument
from utils.helpers import safe_load_json, utcnow
from utils.logger import get_logger

log = get_logger(__name__)


def get_checklist(country: str) -> list[str]:
    data = safe_load_json(SEEDS_DIR / "document_checklists.json")
    return list(data.get("checklists", {}).get(country, []))


def ensure_documents_for_profile(profile_id: int, country: str) -> None:
    """Create CaseDocument rows for each checklist item if missing."""
    checklist = get_checklist(country)
    if not checklist:
        return
    with session_scope() as db:
        existing_types = {
            d.doc_type for d in db.scalars(
                select(CaseDocument).where(
                    (CaseDocument.profile_id == profile_id)
                    & (CaseDocument.country == country)
                )
            )
        }
        added = 0
        for doc_type in checklist:
            if doc_type in existing_types:
                continue
            db.add(
                CaseDocument(
                    profile_id=profile_id,
                    country=country,
                    doc_type=doc_type,
                    status="pending",
                )
            )
            added += 1
        if added:
            log.info("Seeded %d document rows for profile=%s country=%s",
                     added, profile_id, country)


def list_documents(profile_id: int, country: str) -> list[CaseDocument]:
    with session_scope() as db:
        rows = list(
            db.scalars(
                select(CaseDocument).where(
                    (CaseDocument.profile_id == profile_id)
                    & (CaseDocument.country == country)
                ).order_by(CaseDocument.id)
            )
        )
        for r in rows:
            db.expunge(r)
        return rows


def update_document(
    doc_id: int,
    *,
    status: Optional[str] = None,
    filename: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    allowed = {"pending", "uploaded", "verified", "rejected"}
    with session_scope() as db:
        row = db.get(CaseDocument, doc_id)
        if not row:
            return False
        if status is not None:
            if status not in allowed:
                raise ValueError(f"Invalid document status: {status}")
            row.status = status
            if status == "uploaded":
                row.uploaded_at = utcnow()
        if filename is not None:
            row.filename = filename
        if notes is not None:
            row.notes = notes
        return True


def progress(profile_id: int, country: str) -> tuple[int, int]:
    """Return (completed, total). 'completed' means status in {uploaded, verified}."""
    docs = list_documents(profile_id, country)
    total = len(docs)
    done = sum(1 for d in docs if d.status in ("uploaded", "verified"))
    return done, total


# ---------- v0.11 evidence vault reads ---------------------------------


def _evidence_to_dto(d: CaseDocument):
    """Hydrate a CaseDocument row into a DocumentEvidenceDTO.

    Imports inline to avoid a circular dependency between schemas and
    this module's eager import path."""
    import json as _json
    from models.schemas import DocumentEvidenceDTO

    def _safe_list(blob: Optional[str]) -> list[str]:
        try:
            v = _json.loads(blob or "[]")
            return [str(x) for x in v] if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []

    try:
        fields = _json.loads(d.extracted_json or "{}")
        if not isinstance(fields, dict):
            fields = {}
    except (ValueError, TypeError):
        fields = {}

    return DocumentEvidenceDTO(
        id=d.id,
        profile_id=d.profile_id,
        user_id=d.user_id,
        step_key=d.step_key,
        document_type=d.document_type or d.doc_type,
        original_filename=d.original_filename or d.filename,
        stored_path=d.stored_path,
        mime_type=d.mime_type,
        file_size=d.file_size,
        extracted_text=(d.extracted_text[:2000] if d.extracted_text else None),
        extracted_fields=fields,
        verification_status=(d.verification_status or "pending"),
        issues=_safe_list(d.issues_json),
        warnings=_safe_list(getattr(d, "warnings_json", None)),
        matched_fields=_safe_list(getattr(d, "matched_fields_json", None)),
        # v0.12 extraction-pipeline visibility
        extraction_method=getattr(d, "extraction_method", None),
        extraction_status=getattr(d, "extraction_status", None),
        extraction_errors=_safe_list(getattr(d, "extraction_errors", None)),
        # v0.17 — OCR quality signal
        ocr_quality_score=getattr(d, "ocr_quality_score", None),
        ocr_quality_label=getattr(d, "ocr_quality_label", None),
        # v0.14 confirmation path (spec §3, §4)
        confirmed_by_user=bool(getattr(d, "confirmed_by_user", False)),
        confirmed_at=getattr(d, "confirmed_at", None),
        confirmed_by_admin_id=getattr(d, "confirmed_by_admin_id", None),
        # v0.16 — confirmation note
        confirmation_note=getattr(d, "confirmation_note", None),
        uploaded_at=d.uploaded_at or d.created_at,
        updated_at=d.updated_at,
    )


def list_evidence_for_profile(profile_id: int):
    """v0.11: return all evidence-tagged documents for a profile,
    grouped by step_key. Returns list[DocumentEvidenceDTO]. Excludes
    legacy v0.5 checklist rows that have no `step_key`."""
    with session_scope() as db:
        rows = list(db.scalars(
            select(CaseDocument)
            .where(
                (CaseDocument.profile_id == profile_id)
                & (CaseDocument.step_key.is_not(None))
            )
            .order_by(CaseDocument.uploaded_at.desc())
        ))
        return [_evidence_to_dto(r) for r in rows]


def get_evidence_by_id(document_id: int):
    """v0.11: fetch one evidence row by id. Returns
    DocumentEvidenceDTO or None."""
    with session_scope() as db:
        row = db.get(CaseDocument, document_id)
        if row is None or row.step_key is None:
            return None
        return _evidence_to_dto(row)


def delete_evidence(document_id: int) -> bool:
    """v0.11: hard-delete one evidence row. The actual file on disk is
    left in place — the user can re-upload to overwrite via the
    versioned-name mechanism. Returns True if a row was removed."""
    with session_scope() as db:
        row = db.get(CaseDocument, document_id)
        if row is None or row.step_key is None:
            return False
        db.delete(row)
        return True


# ---------- v0.14 canonical document service per Phase 5.5 spec §2 ----
#
# Every page (Route Plan + Documents Vault) MUST consult these helpers
# when reading or writing per-slot evidence. Inline lookups in the page
# layer caused the v0.13 bug where uploaded docs disappeared from the
# Route Plan upload slot — the page rendered an empty file_uploader
# while the Documents Vault still showed the row.
#
# Naming: every function takes (profile_id, step_key, document_type)
# in that order so the trio can be passed through composed calls
# without re-ordering.


def get_document_for_slot(
    profile_id: int, step_key: str, document_type: str,
):
    """Spec §2: single canonical lookup for one upload slot.

    Returns the most-recently-uploaded `DocumentEvidenceDTO` for the
    (profile, step, document_type) triple, or None if no document has
    been uploaded for that slot yet.

    Both the Route Plan page (per-slot upload widgets) and the
    Documents Vault (per-step grouping) MUST use this rather than
    inlining the query.
    """
    with session_scope() as db:
        row = db.scalar(
            select(CaseDocument)
            .where(
                (CaseDocument.profile_id == profile_id)
                & (CaseDocument.step_key == step_key)
                & (CaseDocument.document_type == document_type)
            )
            .order_by(CaseDocument.uploaded_at.desc())
        )
        if row is None:
            return None
        return _evidence_to_dto(row)


def list_documents_for_step(
    profile_id: int, step_key: str,
) -> list:
    """Spec §2: return all evidence rows attached to a route step,
    ordered by upload time (newest first). Empty list if none."""
    with session_scope() as db:
        rows = list(db.scalars(
            select(CaseDocument)
            .where(
                (CaseDocument.profile_id == profile_id)
                & (CaseDocument.step_key == step_key)
            )
            .order_by(CaseDocument.uploaded_at.desc())
        ))
        return [_evidence_to_dto(r) for r in rows]


def save_uploaded_document(
    *,
    profile_id: int,
    user_id: Optional[int],
    step_key: str,
    document_type: str,
    country: str,
    original_filename: str,
    file_bytes: bytes,
    mime_type: Optional[str],
    profile,  # UserProfile-like object for verification (duck typed)
) -> dict:
    """Spec §2: end-to-end upload pipeline. The single entry point the
    Route Plan page calls when a user picks a file in a slot.

    Pipeline (each stage's outcome stored in the returned dict):
      1. process_upload  → save to disk + extract_text + extract_fields
      2. verify_document → deterministic verifier
      3. attach_document_to_step → persist CaseDocument row
                                   (replacing any prior row for the
                                   same slot)

    Returns:
      {
        "ok": bool,                     # overall success
        "save_ok": bool,
        "extraction_ok": bool,
        "extraction_status": str,
        "extraction_method": str,
        "verification_status": str,
        "document_id": Optional[int],
        "issues": list[str],
        "warnings": list[str],
        "matched_fields": list[str],
        "error": Optional[str],         # save error if save_ok is False
      }

    Side effects: the file is written under the profile's upload
    directory; one CaseDocument row is added (any prior row for the
    same slot is replaced by attach_document_to_step's dedup).
    """
    # Imports inline to break a potential cycle (process_upload →
    # document_processing_service which doesn't depend on us, but
    # attach_document_to_step lives in route_plan_service which can
    # import from us in turn).
    from services.document_processing_service import process_upload
    from services.document_verification_service import verify_document
    from services.route_plan_service import attach_document_to_step

    result = process_upload(
        profile_id=profile_id,
        step_key=step_key,
        document_type=document_type,
        original_filename=original_filename,
        file_bytes=file_bytes,
        mime_type=mime_type,
    )
    out: dict = {
        "ok": False,
        "save_ok": result.save.ok,
        "extraction_ok": False,
        "extraction_status": "pending",
        "extraction_method": "",
        "verification_status": "pending",
        "document_id": None,
        "issues": [],
        "warnings": [],
        "matched_fields": [],
        "error": None,
    }
    if not result.save.ok:
        out["error"] = result.save.error_message
        log.warning(
            "save_uploaded_document: file save failed for "
            "profile=%s step=%s type=%s: %s",
            profile_id, step_key, document_type, result.save.error_message,
        )
        return out

    out["extraction_ok"] = result.extraction.ok
    out["extraction_status"] = result.extraction.status
    out["extraction_method"] = result.extraction.method or ""

    verification = verify_document(
        document_type=document_type,
        extracted_fields=result.extracted_fields,
        profile=profile,
        extraction_failed=not result.extraction.ok,
        extraction_status=result.extraction.status,
        extraction_message=result.extraction.error_message,
    )
    out["verification_status"] = verification.verification_status
    out["issues"] = list(verification.issues)
    out["warnings"] = list(verification.warnings)
    out["matched_fields"] = list(verification.matched_fields)

    doc_id = attach_document_to_step(
        profile_id=profile_id,
        user_id=user_id,
        step_key=step_key,
        document_type=document_type,
        original_filename=original_filename,
        stored_path=str(result.save.stored_path),
        mime_type=result.save.mime_type,
        file_size=result.save.file_size,
        extracted_text=result.extraction.text,
        extracted_fields=result.extracted_fields,
        verification_status=verification.verification_status,
        issues=list(verification.issues),
        country=country,
        extraction_method=result.extraction.method or None,
        extraction_status=result.extraction.status,
        extraction_errors=list(result.extraction.errors or []),
        warnings=list(verification.warnings),
        matched_fields=list(verification.matched_fields),
        ocr_quality_score=result.extraction.ocr_quality_score,
        ocr_quality_label=result.extraction.ocr_quality_label,
    )
    out["document_id"] = doc_id
    out["ocr_quality_score"] = result.extraction.ocr_quality_score
    out["ocr_quality_label"] = result.extraction.ocr_quality_label
    out["ok"] = True
    log.info(
        "save_uploaded_document ok: profile=%s step=%s type=%s "
        "doc=%s extraction=%s verification=%s quality=%s",
        profile_id, step_key, document_type, doc_id,
        result.extraction.status, verification.verification_status,
        result.extraction.ocr_quality_label,
    )
    return out


def delete_document(document_id: int) -> bool:
    """Spec §2: thin alias around `delete_evidence` for naming
    consistency with the rest of the v0.14 canonical surface."""
    return delete_evidence(document_id)


def reprocess_document(
    document_id: int, profile,  # UserProfile-like, for verification
) -> dict:
    """Spec §2 + §10: re-run extraction + verification on a previously
    uploaded file (whose bytes are already saved on disk). Used by the
    "Reprocess OCR" button.

    The original `CaseDocument` row is updated in place — the
    `stored_path` and `original_filename` don't change. All extraction
    and verification fields (extracted_text, extracted_json,
    extraction_method, extraction_status, extraction_errors,
    verification_status, issues_json, warnings_json,
    matched_fields_json) are refreshed.

    `confirmed_by_user` is preserved — the user already confirmed,
    reprocessing OCR doesn't undo that. If the user wants to
    re-confirm after reprocessing, they can flip status back via
    delete + re-upload.

    Returns the same shape dict as `save_uploaded_document`.
    """
    import json as _json
    from pathlib import Path
    from services.document_processing_service import (
        extract_fields, extract_text,
    )
    from services.document_verification_service import verify_document

    out: dict = {
        "ok": False,
        "save_ok": True,  # not re-saving
        "extraction_ok": False,
        "extraction_status": "pending",
        "extraction_method": "",
        "verification_status": "pending",
        "document_id": document_id,
        "issues": [],
        "warnings": [],
        "matched_fields": [],
        "error": None,
    }

    with session_scope() as db:
        row = db.get(CaseDocument, document_id)
        if row is None:
            out["error"] = "Document not found."
            return out
        if not row.stored_path:
            out["error"] = "Original file path is missing."
            return out
        path = Path(row.stored_path)
        if not path.exists():
            out["error"] = (
                f"File no longer on disk at {row.stored_path}. "
                "Please delete and re-upload."
            )
            return out

        # 1) Re-extract text
        extraction = extract_text(path, mime_type=row.mime_type)
        out["extraction_ok"] = extraction.ok
        out["extraction_status"] = extraction.status
        out["extraction_method"] = extraction.method or ""

        # 2) Re-extract structured fields
        fields = (
            extract_fields(extraction.text, row.document_type or row.doc_type)
            if extraction.ok else {}
        )

        # 3) Re-run verification
        verification = verify_document(
            document_type=(row.document_type or row.doc_type),
            extracted_fields=fields,
            profile=profile,
            extraction_failed=not extraction.ok,
            extraction_status=extraction.status,
            extraction_message=extraction.error_message,
        )
        out["verification_status"] = verification.verification_status
        out["issues"] = list(verification.issues)
        out["warnings"] = list(verification.warnings)
        out["matched_fields"] = list(verification.matched_fields)

        # 4) Update the row in place
        row.extracted_text = (extraction.text or "")[:32 * 1024]
        row.extracted_json = _json.dumps(fields, default=str)
        row.extraction_method = extraction.method or None
        row.extraction_status = extraction.status
        row.extraction_errors = (
            _json.dumps(list(extraction.errors)) if extraction.errors else None
        )
        # v0.17 — persist OCR quality signal after reprocess
        try:
            row.ocr_quality_score = getattr(extraction, "ocr_quality_score", None)
            row.ocr_quality_label = getattr(extraction, "ocr_quality_label", None)
        except Exception:
            pass
        out["ocr_quality_score"] = getattr(extraction, "ocr_quality_score", None)
        out["ocr_quality_label"] = getattr(extraction, "ocr_quality_label", None)
        # v0.16 (Phase 5.7) — read confirmation flag defensively in
        # case an old DB doesn't have the column. SQLAlchemy declares
        # it on the model, but `getattr` with default keeps reprocess
        # from crashing on legacy rows where the migration never ran.
        was_confirmed = bool(getattr(row, "confirmed_by_user", False))

        # Reprocessing wipes any prior user confirmation IF the new
        # verification status disagrees. If new status is itself
        # `manual_review_required` and the user had already confirmed,
        # preserve the confirmation — they'd have to delete-and-reupload
        # to undo it.
        if (was_confirmed
                and verification.verification_status
                    == "manual_review_required"):
            # User had already confirmed; keep them in user_confirmed.
            row.verification_status = "user_confirmed"
            row.status = "user_confirmed"
            out["verification_status"] = "user_confirmed"
        else:
            row.verification_status = verification.verification_status
            row.status = verification.verification_status
            # If new status is something other than user_confirmed,
            # clear stale confirmation. Wrap in try/setattr so a DB
            # missing the column doesn't crash the reprocess flow.
            if verification.verification_status != "user_confirmed":
                try:
                    row.confirmed_by_user = False
                    row.confirmed_at = None
                except Exception:
                    pass
        row.issues_json = _json.dumps(list(verification.issues))
        row.warnings_json = _json.dumps(list(verification.warnings))
        row.matched_fields_json = _json.dumps(list(verification.matched_fields))
        row.verified_at = utcnow()
        row.updated_at = utcnow()

        out["ok"] = True
        log.info(
            "reprocess_document ok: doc=%s extraction=%s verification=%s",
            document_id, extraction.status,
            row.verification_status,
        )
    return out


def confirm_document_manually(
    document_id: int,
    *,
    by_admin_id: Optional[int] = None,
    note: Optional[str] = None,
) -> bool:
    """Record a manual confirmation on a document.

    v0.16 (Phase 5.7) — relaxed semantics:

      * Spec §8 calls this an "I reviewed this document" button. The
        user is acknowledging they have eyeballed the extracted text
        and are vouching for it. This is NOT the same as automated
        verification, and the UI must always make that clear.
      * `extraction_failed` is the only status where confirmation is
        refused — there's nothing to review if OCR couldn't read the
        file. Every other status (pending, manual_review_required,
        needs_attention, verified, user_confirmed) accepts a fresh
        confirmation. Subsequent calls are idempotent.

    If `by_admin_id` is None → user self-review. Sets
    verification_status='user_confirmed', confirmed_by_user=True,
    confirmed_at=now, confirmation_note=<note or NULL>.

    If `by_admin_id` is set → admin approval. Sets
    verification_status='admin_verified', confirmed_by_admin_id=<id>.

    Returns True on success, False if the document doesn't exist or
    is in `extraction_failed`.
    """
    with session_scope() as db:
        row = db.get(CaseDocument, document_id)
        if row is None:
            log.warning(
                "confirm_document_manually: doc=%s not found", document_id,
            )
            return False

        # The only refusal: extraction_failed. There is no extracted
        # text or fields for the user to review.
        if row.verification_status == "extraction_failed":
            log.warning(
                "confirm_document_manually: doc=%s extraction_failed "
                "— nothing to review", document_id,
            )
            return False

        if by_admin_id is None:
            row.verification_status = "user_confirmed"
            row.status = "user_confirmed"
            try:
                row.confirmed_by_user = True
            except Exception:
                # Legacy DB without the column — log + continue.
                log.warning(
                    "confirm_document_manually: doc=%s — confirmed_by_user "
                    "column missing on row; status mirror still updated.",
                    document_id,
                )
        else:
            row.verification_status = "admin_verified"
            row.status = "admin_verified"
            try:
                row.confirmed_by_admin_id = by_admin_id
            except Exception:
                log.warning(
                    "confirm_document_manually: doc=%s — "
                    "confirmed_by_admin_id column missing on row.",
                    document_id,
                )
        try:
            row.confirmed_at = utcnow()
        except Exception:
            pass
        # v0.16: record the user's optional review note.
        if note is not None:
            try:
                row.confirmation_note = note.strip() or None
            except Exception:
                pass
        row.updated_at = utcnow()
        log.info(
            "confirm_document_manually: doc=%s status=%s admin=%s "
            "note=%r",
            document_id, row.verification_status, by_admin_id,
            (note[:60] if note else None),
        )
        return True
