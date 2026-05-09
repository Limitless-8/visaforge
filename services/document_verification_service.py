"""
services/document_verification_service.py
-----------------------------------------
v0.11 evidence-verification pipeline — stage 2 (verify).

Takes the structured fields extracted by `document_processing_service`
plus the user's profile + the route step, and decides whether the
document is `verified` / `needs_attention` / `rejected` / `pending` /
`extraction_failed`. Returns a `VerificationResult` (matched fields,
issues, warnings, ready-for-completion flag).

This is a READINESS check, not legal validation. The disclaimer
language is the caller's responsibility to surface in the UI.

Determinism: every check is rule-based on profile fields, profile
status maps, and the structured extraction dict. No AI. No network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from models.orm import UserProfile
from models.schemas import VerificationResult
from services.document_processing_service import (
    DOCUMENT_TYPE_BANK,
    DOCUMENT_TYPE_DEGREE,
    DOCUMENT_TYPE_HEC,
    DOCUMENT_TYPE_IBCC,
    DOCUMENT_TYPE_IELTS,
    DOCUMENT_TYPE_MOFA,
    DOCUMENT_TYPE_NADRA,
    DOCUMENT_TYPE_OFFER_LETTER,
    DOCUMENT_TYPE_PASSPORT,
    DOCUMENT_TYPE_POLICE,
    DOCUMENT_TYPE_SPONSOR,
    DOCUMENT_TYPE_TB,
    DOCUMENT_TYPE_TOEFL,
    DOCUMENT_TYPE_TRANSCRIPT,
)
from utils.logger import get_logger
from utils.reference_data import (
    FUNDS_STATUS_STRENGTH,
    OFFER_STATUS_STRENGTH,
)

log = get_logger(__name__)


# ---------- Name fuzzy match -------------------------------------------


_PUNCT_RX = re.compile(r"[^A-Za-z\s]+")


def _normalise_name(s: Optional[str]) -> str:
    if not s:
        return ""
    cleaned = _PUNCT_RX.sub(" ", s).lower()
    # Collapse whitespace; sort tokens so "John Doe" matches "Doe John"
    # and ignore middle-name variations.
    tokens = sorted(t for t in cleaned.split() if len(t) > 1)
    return " ".join(tokens)


def _names_roughly_match(a: Optional[str], b: Optional[str]) -> bool:
    """True if at least 2 normalised tokens overlap, OR the shorter
    name is a contiguous substring of the longer (sorted) form.

    Boolean wrapper around `_classify_name_match` for legacy call
    sites that just want yes/no. Returns True for both 'matched' and
    'partial_match' classifications — i.e. don't reject on minor
    spelling or order differences (spec §7).
    """
    return _classify_name_match(a, b) in ("matched", "partial_match")


# Spec §7 four-state classifier. Available for callers that want the
# richer signal (e.g. for warnings vs hard issues). Existing call
# sites that expect a bool use the wrapper above.
NameMatchVerdict = str  # Literal["matched","partial_match","mismatch","unknown"]


def _classify_name_match(
    a: Optional[str], b: Optional[str],
) -> NameMatchVerdict:
    """Spec §7 four-state classification:
      * "unknown"       — either name is missing/empty
      * "matched"       — full token overlap or near-exact (rapidfuzz≥90)
      * "partial_match" — ≥2 tokens overlap, or single-token subset, or
                          rapidfuzz ratio ≥75
      * "mismatch"      — none of the above

    rapidfuzz is used as an additive signal when installed; absence
    does not change deterministic behavior on the cases the existing
    token logic handles.
    """
    na, nb = _normalise_name(a), _normalise_name(b)
    if not na or not nb:
        return "unknown"

    set_a, set_b = set(na.split()), set(nb.split())

    # Exact normalised match — both sides have identical sorted tokens.
    if na == nb:
        return "matched"

    # Single-token name fully contained in the other → partial.
    if len(set_a) == 1 and set_a.issubset(set_b):
        return "partial_match"
    if len(set_b) == 1 and set_b.issubset(set_a):
        return "partial_match"

    overlap = set_a & set_b
    if len(overlap) >= 2:
        # Strong overlap on multi-token names. The two sides may
        # differ by additional middle names (e.g. "Shehryar Khan" vs
        # "Shehryar Mahmood Khan") — that's a partial match, not a
        # full one. Only treat as matched when the normalised token
        # sets are identical (handled by the equality check above);
        # any size difference means partial.
        return "partial_match"

    # rapidfuzz fallback for spelling drift (e.g. transliteration
    # variants like "Shehryar" vs "Sheheryar"). Optional dependency.
    try:
        from rapidfuzz.fuzz import token_set_ratio  # type: ignore
        score = token_set_ratio(na, nb)
        if score >= 90:
            return "matched"
        if score >= 75:
            return "partial_match"
    except ImportError:
        pass

    return "mismatch"


# ---------- Date helpers ------------------------------------------------


def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _months_until(d: date) -> int:
    today = date.today()
    delta = d - today
    return int(delta.days / 30.44)


# ---------- Per-document checkers --------------------------------------


def _verify_passport(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    extracted_name = fields.get("full_name")
    if extracted_name:
        if _names_roughly_match(extracted_name, profile.full_name):
            matched.append("full_name")
        else:
            issues.append(
                f"Name on passport ('{extracted_name}') does not appear "
                f"to match your profile name ('{profile.full_name}')."
            )

    extracted_nat = fields.get("nationality")
    profile_nat = (profile.nationality or "").strip()
    if extracted_nat and profile_nat:
        if extracted_nat.lower().startswith(profile_nat.lower()) or \
           profile_nat.lower().startswith(extracted_nat.lower()):
            matched.append("nationality")
        else:
            warnings.append(
                f"Passport nationality ('{extracted_nat}') and profile "
                f"nationality ('{profile_nat}') do not match."
            )

    expiry = _parse_iso_date(fields.get("expiry_date"))
    if expiry is None:
        warnings.append(
            "Could not read passport expiry date — please verify "
            "manually before submitting."
        )
    else:
        today = date.today()
        if expiry <= today:
            issues.append(
                f"Passport has already expired ({expiry.isoformat()})."
            )
        else:
            months = _months_until(expiry)
            matched.append("expiry_date")
            if months < 6:
                warnings.append(
                    f"Passport expires in about {months} month(s). "
                    "Most destinations require 6+ months validity past "
                    "course end — consider renewing."
                )

    if not fields.get("passport_number"):
        warnings.append("Could not read passport number from the file.")
    else:
        matched.append("passport_number")

    # Spec §10 decision tree:
    # - extraction_failed → extraction_failed
    # - hard issues (expired, name mismatch) → needs_attention
    # - expiry missing → needs_review (spec §10)
    # - all key fields matched → processed
    # - some matched, soft warnings → processed_with_warnings
    if not fields:
        status = "extraction_failed"
    elif issues:
        status = "needs_attention"
    elif not fields.get("expiry_date"):
        # Spec §10: expiry missing → needs_review
        status = "needs_review"
    elif matched:
        status = "processed" if not warnings else "processed_with_warnings"
    else:
        status = "needs_review"

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=(status in ("processed", "processed_with_warnings")),
    )


def _verify_english_test(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    extracted_name = fields.get("candidate_name")
    if extracted_name:
        if _names_roughly_match(extracted_name, profile.full_name):
            matched.append("candidate_name")
        else:
            warnings.append(
                f"Name on test report ('{extracted_name}') does not "
                f"appear to match your profile name ('{profile.full_name}')."
            )

    test_type = fields.get("test_type")
    profile_test = (profile.english_test_type or "").upper()
    if test_type and profile_test:
        if test_type.upper() == profile_test:
            matched.append("test_type")
        else:
            warnings.append(
                f"Profile lists test type '{profile_test}' but document "
                f"reports '{test_type}'."
            )

    score = fields.get("overall_score")
    profile_score = profile.english_test_score
    if score is None:
        warnings.append(
            "Could not read overall band/score from the document."
        )
    else:
        matched.append("overall_score")
        if profile_score is not None:
            try:
                if abs(float(profile_score) - float(score)) > 0.5:
                    warnings.append(
                        f"Document score ({score}) differs noticeably "
                        f"from profile score ({profile_score})."
                    )
            except (TypeError, ValueError):
                pass

    # Spec §10: overall score found → processed; missing → needs_review
    if not fields:
        status = "extraction_failed"
    elif issues:
        status = "needs_attention"
    elif not fields.get("overall_score"):
        status = "needs_review"
    elif matched:
        status = "processed" if not warnings else "processed_with_warnings"
    else:
        status = "needs_review"

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=(status in ("processed", "processed_with_warnings")),
    )


def _verify_bank_statement(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    if name := fields.get("account_holder_name"):
        if _names_roughly_match(name, profile.full_name):
            matched.append("account_holder_name")
        else:
            warnings.append(
                f"Account holder ('{name}') does not appear to match "
                f"your profile name ('{profile.full_name}')."
            )

    balance = fields.get("balance")
    if balance is None:
        warnings.append(
            "Could not extract a balance amount from the statement. "
            "Confirm manually that funds meet visa requirements."
        )
    else:
        matched.append("balance")
        # Cross-reference with profile self-declaration
        funds_strength = FUNDS_STATUS_STRENGTH.get(
            profile.proof_of_funds_status or "", "none",
        )
        if funds_strength == "strong" and balance < 100:
            # 100 in any currency is a sanity floor — extraction probably
            # picked the wrong number, or the user mis-uploaded.
            warnings.append(
                f"Profile says funds are fully prepared, but the "
                f"document shows a low balance ({balance}). Verify the "
                f"correct page was uploaded."
            )

    statement_date = _parse_iso_date(fields.get("statement_date"))
    if statement_date is not None:
        age_days = (date.today() - statement_date).days
        matched.append("statement_date")
        if age_days > 90:
            warnings.append(
                f"Statement is {age_days} days old. Most visa offices "
                f"require statements from the last 30–90 days."
            )

    if fields.get("bank_name"):
        matched.append("bank_name")

    if not fields:
        status = "extraction_failed"
    elif issues:
        status = "needs_attention"
    elif matched:
        status = "processed" if not warnings else "processed_with_warnings"
    else:
        status = "needs_review"

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=(status in ("processed", "processed_with_warnings")),
    )


def _verify_academic(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    if name := fields.get("student_name"):
        if _names_roughly_match(name, profile.full_name):
            matched.append("student_name")
        else:
            warnings.append(
                f"Student name on document ('{name}') does not appear "
                f"to match your profile name ('{profile.full_name}')."
            )

    deg_title = (fields.get("degree_title") or "").lower()
    profile_field = (profile.previous_field_of_study or "").lower()
    if deg_title:
        matched.append("degree_title")
        if profile_field and not any(
            tok in deg_title for tok in profile_field.split()
        ):
            warnings.append(
                f"Document degree title ('{fields['degree_title']}') "
                f"does not obviously match profile field "
                f"('{profile.previous_field_of_study}')."
            )

    if fields.get("institution"):
        matched.append("institution")
    if fields.get("graduation_year"):
        matched.append("graduation_year")

    if not fields:
        status = "extraction_failed"
    elif issues:
        status = "needs_attention"
    elif matched:
        status = "processed" if not warnings else "processed_with_warnings"
    else:
        status = "needs_review"

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=(status in ("processed", "processed_with_warnings")),
    )


def _verify_police(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    """v0.14: Police clearance follows the same manual_review_required
    flow as the other Pakistan attestations — VisaForge checks for
    the right keywords + date freshness, but cannot prove the seal
    or signature is authentic. The user confirms via the
    "Confirm this document is correct" button.
    """
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    keyword_present = bool(fields.get("has_police_keywords"))
    if not keyword_present:
        warnings.append(
            "Document does not contain typical police-clearance "
            "keywords ('Police', 'Character Certificate', 'Clearance "
            "Certificate'). Ensure the correct file was uploaded."
        )
    else:
        matched.append("police_keywords")

    if name := fields.get("applicant_name"):
        if _names_roughly_match(name, profile.full_name):
            matched.append("applicant_name")
        else:
            warnings.append(
                f"Applicant name ('{name}') does not appear to match "
                f"your profile name ('{profile.full_name}')."
            )

    issue_date = _parse_iso_date(fields.get("issue_date"))
    if issue_date is not None:
        matched.append("issue_date")
        age_days = (date.today() - issue_date).days
        if age_days > 180:
            warnings.append(
                f"Police certificate is {age_days} days old. Most "
                f"destinations require it to be issued within 6 months."
            )

    if not fields:
        status = "extraction_failed"
    elif not keyword_present:
        status = "needs_attention"
    elif issues:
        status = "needs_attention"
    else:
        status = "manual_review_required"
        warnings.append(
            "VisaForge could read this document but cannot fully "
            "verify it automatically. Please review the extracted "
            "text and confirm whether this is the correct document."
        )

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=False,
    )


def _verify_authority(
    fields: dict[str, Any], profile: UserProfile,
    *, expected_keyword_field: str, authority_label: str,
) -> VerificationResult:
    """Generic verifier for HEC / IBCC / MOFA / Police / TB / NADRA
    documents.

    v0.14 spec §3: VisaForge cannot deterministically prove the
    authenticity of stamps, seals, signatures, or watermarks on
    Pakistan-government-issued attestations. So when keywords are
    present (the document is the right TYPE), we return
    `manual_review_required` rather than `verified` — the user is
    then prompted with "Confirm this document is correct" which
    flips it to `user_confirmed`. Both `verified` and
    `user_confirmed` count as evidence-satisfied for step
    completion (spec §6).

    Status decision tree:
      * fields empty            → extraction_failed
      * keyword absent          → needs_attention (wrong file type)
      * keyword present + name mismatch → needs_attention (warn user)
      * keyword present + clean → manual_review_required (the
        common case — let the user confirm)
    """
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    keyword_present = bool(fields.get(expected_keyword_field))
    if not keyword_present:
        warnings.append(
            f"Document does not contain typical {authority_label} "
            f"keywords. Ensure the correct file was uploaded."
        )
    else:
        matched.append(f"{authority_label.lower()}_keywords")

    if name := fields.get("applicant_name"):
        if _names_roughly_match(name, profile.full_name):
            matched.append("applicant_name")
        else:
            warnings.append(
                f"Applicant name on document ('{name}') does not "
                f"appear to match your profile name "
                f"('{profile.full_name}')."
            )

    if fields.get("issue_date"):
        matched.append("issue_date")

    if not fields:
        status = "extraction_failed"
    elif not keyword_present:
        # Wrong file type — needs the user's attention to re-upload
        # the correct document.
        status = "needs_attention"
    elif issues:
        status = "needs_attention"
    else:
        # Keyword(s) present. Even if there are warnings (e.g. name
        # mismatch), authenticity isn't something we can prove
        # deterministically — park in manual_review_required so the
        # user can confirm. The warning still surfaces in the UI.
        status = "manual_review_required"
        warnings.append(
            "VisaForge could read this document but cannot fully "
            "verify this document type automatically. Please review "
            "the extracted text and confirm whether this is the "
            "correct document."
        )

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        # ready_for_completion stays False at the document level —
        # the route plan service decides step-level readiness based
        # on the EVIDENCE_SATISFIED_STATUSES set.
        ready_for_completion=False,
    )


def _verify_nadra(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    """v0.16 spec §7 — NADRA / CNIC advisory verifier.

    VisaForge does NOT claim authenticity for Pakistani identity
    documents. The verifier looks for indicators that the uploaded
    file IS a NADRA-issued document (keywords + CNIC-shaped pattern)
    and parks the result in `manual_review_required` with the
    spec-mandated warning. The Documents page renders that as
    "Needs review" with a "I reviewed this document" button.

    Decision tree:
      * fields empty → extraction_failed
      * no keywords AND no CNIC-shape → needs_attention
        (file likely isn't a NADRA document)
      * keywords or CNIC-shape present → manual_review_required
        (the spec §7 case)

    Soft signals captured:
      * matched_fields: 'pakistan_identity_keywords', 'cnic_pattern',
        'applicant_name', 'father_name', 'date_of_birth',
        'date_of_issue', 'date_of_expiry'
      * warnings: name mismatch (if profile name differs), CNIC OCR
        repaired (if the digit translation table fixed an obvious
        OCR mis-read), expiry passed (if date_of_expiry < today)
    """
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    if not fields:
        return VerificationResult(
            verification_status="extraction_failed",
            issues=["No fields could be extracted from this document."],
            warnings=[], matched_fields=[],
            ready_for_completion=False,
        )

    keywords_present = bool(fields.get("has_nadra_keywords"))
    cnic_present = bool(fields.get("cnic_number"))

    if keywords_present:
        matched.append("pakistan_identity_keywords")
    if cnic_present:
        matched.append("cnic_pattern")

    # Spec §6 supporting fields — surface what we found.
    for key in ("applicant_name", "father_name", "date_of_birth",
                "date_of_issue", "date_of_expiry"):
        if fields.get(key):
            matched.append(key)

    # Soft warning: if we had to repair OCR digit substitutions, make
    # sure the user knows to double-check the CNIC.
    if fields.get("cnic_ocr_repaired"):
        warnings.append(
            "The CNIC number was repaired from likely OCR mis-reads "
            "(e.g. 'O' → '0', 'I' → '1'). Please verify the digits "
            "match your card before relying on this value."
        )

    # Soft warning: applicant name mismatch with profile.
    if (name := fields.get("applicant_name")) and getattr(
        profile, "full_name", None
    ):
        if not _names_roughly_match(name, profile.full_name):
            warnings.append(
                f"Name on document ('{name}') does not appear to match "
                f"your profile name ('{profile.full_name}'). If this is "
                "a family member's CNIC (e.g. for B-Form), ignore."
            )

    # Soft warning: expiry passed.
    if doe := fields.get("date_of_expiry"):
        try:
            from datetime import date
            if date.fromisoformat(str(doe)) < date.today():
                warnings.append(
                    f"This document's expiry date ({doe}) is in the "
                    "past. Renew your CNIC before relying on it for "
                    "visa applications."
                )
        except Exception:
            # Bad date format — let it slide.
            pass

    # Final status.
    if not keywords_present and not cnic_present:
        # Doesn't look like a NADRA document at all — wrong file?
        warnings.append(
            "This document doesn't contain typical NADRA / CNIC "
            "indicators. Make sure you uploaded the right file."
        )
        status = "needs_attention"
    else:
        # Spec §7 EXACT warning text.
        warnings.append(
            "Document appears to be a Pakistan identity document, but "
            "automated OCR cannot verify authenticity. Review manually."
        )
        status = "manual_review_required"

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=False,
    )


def _verify_sponsor(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    if fields.get("has_sponsor_keywords"):
        matched.append("sponsor_keywords")
    else:
        warnings.append(
            "Document does not contain typical sponsor-letter "
            "keywords ('sponsor', 'undertake', 'cover all expenses'). "
            "Ensure this is the correct file."
        )

    if fields.get("sponsor_name"):
        matched.append("sponsor_name")

    if not fields:
        status = "extraction_failed"
    elif matched:
        status = "processed" if not warnings else "processed_with_warnings"
    else:
        status = "needs_review"

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=(status in ("processed", "processed_with_warnings")),
    )


def _verify_offer_letter(
    fields: dict[str, Any], profile: UserProfile,
) -> VerificationResult:
    issues: list[str] = []
    warnings: list[str] = []
    matched: list[str] = []

    if not fields.get("has_offer_keywords"):
        warnings.append(
            "Document does not contain typical offer-letter keywords "
            "('offer of admission', 'letter of acceptance', 'CAS', "
            "'Zulassung'). Ensure the correct file was uploaded."
        )
    else:
        matched.append("offer_keywords")

    if name := fields.get("student_name"):
        if _names_roughly_match(name, profile.full_name):
            matched.append("student_name")
        else:
            warnings.append(
                f"Student name on document ('{name}') does not "
                f"appear to match your profile name."
            )

    if fields.get("institution"):
        matched.append("institution")

    if not fields:
        status = "extraction_failed"
    elif matched:
        status = "processed" if not warnings else "processed_with_warnings"
    else:
        status = "needs_review"

    return VerificationResult(
        verification_status=status,  # type: ignore[arg-type]
        issues=issues, warnings=warnings,
        matched_fields=matched,
        ready_for_completion=(status in ("processed", "processed_with_warnings")),
    )


# ---------- Public API -------------------------------------------------


_VERIFIERS = {
    DOCUMENT_TYPE_PASSPORT:     _verify_passport,
    DOCUMENT_TYPE_IELTS:        _verify_english_test,
    DOCUMENT_TYPE_TOEFL:        _verify_english_test,
    DOCUMENT_TYPE_BANK:         _verify_bank_statement,
    DOCUMENT_TYPE_TRANSCRIPT:   _verify_academic,
    DOCUMENT_TYPE_DEGREE:       _verify_academic,
    DOCUMENT_TYPE_POLICE:       _verify_police,
    DOCUMENT_TYPE_SPONSOR:      _verify_sponsor,
    DOCUMENT_TYPE_OFFER_LETTER: _verify_offer_letter,
}


def verify_document(
    *,
    document_type: str,
    extracted_fields: dict[str, Any],
    profile: UserProfile,
    extraction_failed: bool = False,
    extraction_status: Optional[str] = None,
    extraction_message: Optional[str] = None,
) -> VerificationResult:
    """Top-level dispatcher. Returns a `VerificationResult`.

    `extraction_failed=True` short-circuits to that status without
    touching the profile — the UI will surface the OCR/lib message
    rather than a verification verdict.

    v0.12: when extraction failed, the dispatcher uses
    `extraction_status` / `extraction_message` to produce a more
    specific issue list — e.g. "Tesseract OCR engine is not installed"
    rather than the generic "Could not read text from the uploaded
    file." Both arguments are optional; behavior is unchanged when
    they're omitted.
    """
    if extraction_failed:
        # Build a specific issue from the extraction status when
        # available, otherwise fall back to the generic message.
        issue: str
        if extraction_status in ("tesseract_missing", "paddleocr_missing"):
            issue = (
                "Tesseract OCR engine is not installed or not "
                "available on PATH. Install Tesseract and add it to "
                "PATH, or upload a text-based PDF instead."
            )
        elif extraction_status == "library_missing":
            issue = (
                extraction_message
                or "A required text-extraction library is not installed."
            )
        elif extraction_status == "empty":
            issue = (
                extraction_message
                or "The file opened but no readable text was found "
                "(it may be a low-quality scan)."
            )
        elif extraction_status == "unsupported_type":
            issue = (
                extraction_message
                or "The uploaded file type is not supported."
            )
        elif extraction_status == "file_not_found":
            issue = (
                "The saved file could not be located on disk. "
                "Please try uploading again."
            )
        elif extraction_message:
            issue = extraction_message
        else:
            issue = "Could not read text from the uploaded file."
        return VerificationResult(
            verification_status="extraction_failed",
            issues=[issue],
            warnings=[],
            matched_fields=[],
            ready_for_completion=False,
        )

    # v0.17 spec §7 + §10: if OCR ran but quality is weak, attach an
    # advisory warning before dispatching to the type-specific verifier.
    # The verifier still runs — it may extract partial fields — but the
    # result carries a "Try a clearer scan" hint.
    _weak_ocr_extra: list[str] = []
    if extraction_status == "weak_ocr":
        _weak_ocr_extra.append(
            "OCR quality is weak for this upload. Try uploading a "
            "clearer scan or a text-based PDF for better results."
        )

    if document_type == DOCUMENT_TYPE_HEC:
        return _verify_authority(
            extracted_fields, profile,
            expected_keyword_field="has_hec_keywords",
            authority_label="HEC",
        )
    if document_type == DOCUMENT_TYPE_IBCC:
        return _verify_authority(
            extracted_fields, profile,
            expected_keyword_field="has_ibcc_keywords",
            authority_label="IBCC",
        )
    if document_type == DOCUMENT_TYPE_MOFA:
        return _verify_authority(
            extracted_fields, profile,
            expected_keyword_field="has_mofa_keywords",
            authority_label="MOFA",
        )
    if document_type == DOCUMENT_TYPE_NADRA:
        # v0.16 spec §7: NADRA / CNIC documents get a dedicated
        # advisory verifier with the spec-mandated warning text. We
        # do NOT claim authenticity. If the OCR text contains
        # Pakistan-identity keywords or a CNIC-shaped pattern, status
        # is `manual_review_required` (UI displays "Needs review");
        # otherwise `needs_attention` so the user knows it's likely
        # the wrong file.
        return _verify_nadra(extracted_fields, profile)
    if document_type == DOCUMENT_TYPE_TB:
        # v0.14: TB clearance / IOM medical certificate.
        return _verify_authority(
            extracted_fields, profile,
            expected_keyword_field="has_tb_keywords",
            authority_label="TB / Medical",
        )

    fn = _VERIFIERS.get(document_type)
    if fn is None:
        # Unknown type — accept upload but leave the user to confirm.
        # spec §10: do NOT use "pending" as a final user-facing status.
        return VerificationResult(
            verification_status="needs_review",
            issues=[],
            warnings=_weak_ocr_extra + [
                f"No automated verifier for document type "
                f"'{document_type}'. VisaForge cannot assess this "
                "document automatically — review it manually."
            ],
            matched_fields=[],
            ready_for_completion=False,
        )
    result = fn(extracted_fields, profile)
    if _weak_ocr_extra:
        # Append the weak-OCR advisory to the verifier's warning list.
        result = VerificationResult(
            verification_status=result.verification_status,
            issues=list(result.issues),
            warnings=_weak_ocr_extra + list(result.warnings),
            matched_fields=list(result.matched_fields),
            ready_for_completion=result.ready_for_completion,
        )
    return result
