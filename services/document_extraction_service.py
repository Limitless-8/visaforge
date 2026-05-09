"""services/document_extraction_service.py
------------------------------------------
v0.17 (Phase 5.8) — Structured extraction layer.

Consumes raw OCR text and produces a dict of typed fields for a given
document type. All extraction is deterministic (regex/heuristic).

Design notes:
* Never invent values — missing fields are returned as None / absent.
* All date parsing is routed through _try_parse_date which returns an
  ISO-8601 string (YYYY-MM-DD) or None.
* CNIC parsing uses the robust extract_cnic helper from text_cleaning.
* This module is called by document_processing_service.process_upload
  and reprocess_document; it is NOT called by verification, which reads
  the already-stored extracted_fields JSON.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from utils.logger import get_logger
from utils.text_cleaning import (
    extract_cnic,
    fix_common_ocr_confusions,
    fuzzy_find_label_value,
    normalize_ocr_text,
    normalize_spaces,
)

log = get_logger(__name__)


# ---------- Date parsing --------------------------------------------------

_DATE_PATTERNS: list[re.Pattern[str]] = [
    # ISO 8601: 2025-11-07
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    # DD/MM/YYYY or DD-MM-YYYY (Pakistani / European format)
    re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b"),
    # DD Month YYYY or Month DD YYYY
    re.compile(
        r"\b(\d{1,2})\s+"
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May"
        r"|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?"
        r"|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May"
        r"|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?"
        r"|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})[,\s]+(\d{4})\b",
        re.IGNORECASE,
    ),
]

_MONTH_ABBR: dict[str, str] = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    "january": "01", "february": "02", "march": "03", "april": "04",
    "june": "06", "july": "07", "august": "08", "september": "09",
    "october": "10", "november": "11", "december": "12",
}


def _try_parse_date(raw: str) -> Optional[str]:
    """Parse a date string into ISO 8601 (YYYY-MM-DD).

    Tries multiple patterns, then falls back to python-dateutil.
    Returns None if parsing fails.
    """
    if not raw:
        return None
    raw = raw.strip()

    # Pattern 1: already ISO
    m = _DATE_PATTERNS[0].search(raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

    # Pattern 2: DD/MM/YYYY or DD-MM-YYYY
    m = _DATE_PATTERNS[1].search(raw)
    if m:
        d, mo, y = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        # Heuristic: if month > 12, swap day/month
        if int(mo) > 12 and int(d) <= 12:
            d, mo = mo, d
        return f"{y}-{mo}-{d}"

    # Pattern 3: DD Month YYYY
    m = _DATE_PATTERNS[2].search(raw)
    if m:
        d = m.group(1).zfill(2)
        mo = _MONTH_ABBR.get(m.group(2).lower()[:3])
        y = m.group(3)
        if mo:
            return f"{y}-{mo}-{d}"

    # Pattern 4: Month DD YYYY
    m = _DATE_PATTERNS[3].search(raw)
    if m:
        mo = _MONTH_ABBR.get(m.group(1).lower()[:3])
        d = m.group(2).zfill(2)
        y = m.group(3)
        if mo:
            return f"{y}-{mo}-{d}"

    # Fallback: python-dateutil (accepts messy formats and surrounding noise)
    try:
        from dateutil import parser as _duparser
        dt = _duparser.parse(raw, dayfirst=True, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


# ---------- Shared helpers -----------------------------------------------

def _flat(text: str) -> str:
    """Lower-cased, normalised version of text for keyword searching."""
    return normalize_ocr_text(text).lower()


_NAME_AFTER_LABEL_RX = re.compile(
    r"(?:(?:applicant|candidate|holder|bearer|student)(?:'s)?\s*name"
    r"|name\s+of\s+(?:applicant|holder|bearer|student))\s*[:\-]?\s*"
    r"([A-Z][A-Za-z .'\-]{2,60})",
    re.IGNORECASE,
)
_BARE_NAME_RX = re.compile(
    r"(?im)^\s*name\s*[:\-]?\s*(?P<v>[A-Z][A-Za-z .'\-]{2,60})\s*$"
)
_FATHER_NAME_RX = re.compile(
    r"(?:father(?:'s)?\s*name|f/name|s/o|d/o)\s*[:\-]?\s*"
    r"([A-Z][A-Za-z .'\-]{2,60})",
    re.IGNORECASE,
)


def _extract_name(text: str) -> Optional[str]:
    """Extract an applicant/holder name from OCR text."""
    if m := _BARE_NAME_RX.search(text):
        return m.group("v").strip().title()
    if m := _NAME_AFTER_LABEL_RX.search(text):
        return m.group(1).strip().title()
    return None


def _extract_father_name(text: str) -> Optional[str]:
    if m := _FATHER_NAME_RX.search(text):
        return m.group(1).strip().title()
    return None


# ---------- A) NADRA / CNIC / B-Form / Birth Certificate ----------------

_NADRA_KEYWORDS = (
    "nadra", "national database and registration authority",
    "national identity card", "cnic", "b-form", "child registration",
    "crc", "birth certificate", "computerized national identity card",
    "identity number",
)
_PAK_KEYWORDS = (
    "islamic republic of pakistan", "pakistan",
    "government of pakistan",
)
_DOB_RX = re.compile(
    r"(?:date\s+of\s+birth|d\.?o\.?b\.?)\s*[:\-]?\s*([0-9.\-/A-Za-z ,]{6,30})",
    re.IGNORECASE,
)
_DOI_RX = re.compile(
    r"(?:date\s+of\s+issue|issue\s+date|d\.?o\.?i\.?)\s*[:\-]?\s*"
    r"([0-9.\-/A-Za-z ,]{6,30})",
    re.IGNORECASE,
)
_DOE_RX = re.compile(
    r"(?:date\s+of\s+expir(?:y|ation)|expiry\s+date|d\.?o\.?e\.?|valid\s+until)"
    r"\s*[:\-]?\s*([0-9.\-/A-Za-z ,]{6,30})",
    re.IGNORECASE,
)
_NATIONALITY_RX = re.compile(
    r"(?:nationality|citizenship)\s*[:\-]?\s*([A-Za-z]{4,30})",
    re.IGNORECASE,
)


def extract_nadra(text: str) -> dict[str, Any]:
    """Spec §8 A — NADRA / CNIC / B-Form / Birth Certificate."""
    clean = normalize_ocr_text(fix_common_ocr_confusions(text))
    flat = clean.lower()

    out: dict[str, Any] = {}
    out["has_nadra_keywords"] = any(k in flat for k in _NADRA_KEYWORDS)
    out["has_pakistan_keywords"] = any(k in flat for k in _PAK_KEYWORDS)

    cnic = extract_cnic(clean)
    if cnic:
        out["cnic_number"] = cnic

    out["full_name"] = _extract_name(clean)
    out["father_name"] = _extract_father_name(clean)

    if m := _DOB_RX.search(clean):
        out["date_of_birth"] = _try_parse_date(m.group(1))
    if m := _DOI_RX.search(clean):
        out["date_of_issue"] = _try_parse_date(m.group(1))
    if m := _DOE_RX.search(clean):
        out["date_of_expiry"] = _try_parse_date(m.group(1))
    if m := _NATIONALITY_RX.search(clean):
        val = m.group(1).strip()
        if len(val) > 3:
            out["nationality"] = val.title()

    # Confidence signal: 0.0–1.0 based on how many key fields were found
    filled = sum(1 for k in (
        "cnic_number", "full_name", "father_name",
        "date_of_birth", "date_of_issue", "date_of_expiry",
    ) if out.get(k))
    out["confidence"] = round(filled / 6.0, 2)
    return out


# ---------- B) Passport --------------------------------------------------

_PASSPORT_NO_RX = re.compile(r"\b([A-Z]{1,2}\d{7}|[A-Z]\d{8})\b")
_PASSPORT_KEYWORDS = (
    "passport", "republic of pakistan", "travel document",
    "nationality", "place of birth",
)


def extract_passport(text: str) -> dict[str, Any]:
    """Spec §8 B — Passport."""
    clean = normalize_ocr_text(fix_common_ocr_confusions(text))
    flat = clean.lower()

    out: dict[str, Any] = {}
    out["passport_keywords_found"] = any(k in flat for k in _PASSPORT_KEYWORDS)

    if m := _PASSPORT_NO_RX.search(clean):
        out["passport_number"] = m.group(1)

    out["full_name"] = _extract_name(clean)

    if m := _NATIONALITY_RX.search(clean):
        val = m.group(1).strip()
        if len(val) > 3:
            out["nationality"] = val.title()

    if m := _DOB_RX.search(clean):
        out["date_of_birth"] = _try_parse_date(m.group(1))

    expiry_pat = re.search(
        r"(?:expir(?:y|ation)|valid\s+until|date\s+of\s+expir(?:y|ation))"
        r"\s*[:\-/]?\s*([0-9.\-/A-Za-z ,]{6,30})",
        clean, re.IGNORECASE,
    )
    if expiry_pat:
        out["expiry_date"] = _try_parse_date(expiry_pat.group(1))

    issue_pat = re.search(
        r"(?:date\s+of\s+issue|issue\s+date|issued\s+on)\s*[:\-/]?\s*"
        r"([0-9.\-/A-Za-z ,]{6,30})",
        clean, re.IGNORECASE,
    )
    if issue_pat:
        out["issue_date"] = _try_parse_date(issue_pat.group(1))

    return out


# ---------- C) IELTS / English test --------------------------------------

_SCORE_RX = re.compile(r"\b([4-9]\.?[05]|[4-9])\b")
_IELTS_KEYWORDS = (
    "ielts", "toefl", "pte", "duolingo",
    "cambridge", "english language",
    "overall band", "overall score",
)
_BAND_LABELS = (
    ("listening", r"listening\s*[:\-]?\s*([4-9]\.?\d?)"),
    ("reading", r"reading\s*[:\-]?\s*([4-9]\.?\d?)"),
    ("writing", r"writing\s*[:\-]?\s*([4-9]\.?\d?)"),
    ("speaking", r"speaking\s*[:\-]?\s*([4-9]\.?\d?)"),
)


def extract_english_test(text: str) -> dict[str, Any]:
    """Spec §8 C — IELTS / English test."""
    clean = normalize_ocr_text(text)
    flat = clean.lower()

    out: dict[str, Any] = {}

    # Detect test type
    for kw in ("ielts", "toefl", "pte", "duolingo"):
        if kw in flat:
            out["test_type"] = kw.upper()
            break

    out["candidate_name"] = _extract_name(clean)

    # Overall score
    overall_m = re.search(
        r"(?:overall\s+band\s+score|overall\s+score|band\s+score)"
        r"\s*[:\-]?\s*([4-9]\.?\d?)",
        clean, re.IGNORECASE,
    )
    if overall_m:
        out["overall_score"] = overall_m.group(1)

    # Sub-scores
    for label, pattern in _BAND_LABELS:
        m = re.search(pattern, clean, re.IGNORECASE)
        if m:
            out[label] = m.group(1)

    # Test date
    test_date_m = re.search(
        r"(?:test\s+date|date\s+of\s+test|date\s+taken)\s*[:\-]?\s*"
        r"([0-9.\-/A-Za-z ,]{6,30})",
        clean, re.IGNORECASE,
    )
    if test_date_m:
        out["test_date"] = _try_parse_date(test_date_m.group(1))

    return out


# ---------- D) Bank Statement / Proof of Funds --------------------------

_BALANCE_RX = re.compile(
    r"(?:balance|total\s+balance|available\s+balance|closing\s+balance)"
    r"\s*[:\-]?\s*([A-Z]{0,3}\s?[\d,]+\.?\d*)",
    re.IGNORECASE,
)
_CURRENCY_RX = re.compile(r"\b(PKR|GBP|USD|EUR|CAD|AED|SAR|AUD|CHF)\b")
_BANK_NAME_RX = re.compile(
    r"(?:bank|financial\s+institution)\s*[:\-]?\s*([A-Z][A-Za-z &,\.]{3,60})",
    re.IGNORECASE,
)


def extract_bank_statement(text: str) -> dict[str, Any]:
    """Spec §8 D — Bank Statement / Proof of Funds."""
    clean = normalize_ocr_text(text)
    out: dict[str, Any] = {}

    out["account_holder_name"] = _extract_name(clean)

    if m := _BANK_NAME_RX.search(clean):
        out["bank_name"] = m.group(1).strip()

    if m := _BALANCE_RX.search(clean):
        raw = m.group(1).strip()
        out["balance"] = raw.replace(",", "")

    if m := _CURRENCY_RX.search(clean):
        out["currency"] = m.group(1)

    stmt_m = re.search(
        r"(?:statement\s+date|as\s+at|as\s+of|dated?)\s*[:\-]?\s*"
        r"([0-9.\-/A-Za-z ,]{6,30})",
        clean, re.IGNORECASE,
    )
    if stmt_m:
        out["statement_date"] = _try_parse_date(stmt_m.group(1))

    return out


# ---------- E) Academic documents ----------------------------------------

_TRANSCRIPT_KW = (
    "transcript", "grade sheet", "mark sheet", "marksheet",
    "academic record", "result card",
)
_DEGREE_KW = (
    "bachelor", "master", "b.sc", "m.sc", "b.e", "m.e", "b.tech",
    "m.tech", "phd", "doctor", "diploma", "degree", "certificate of",
)
_GRAD_YEAR_RX = re.compile(
    r"(?:graduation|completion|award)\s*(?:year|date)?\s*[:\-]?\s*(\d{4})",
    re.IGNORECASE,
)
_INSTITUTION_RX = re.compile(
    r"(?:university|college|institute|institution|school)\s+(?:of\s+)?([A-Z][A-Za-z &,\.]{3,60})",
    re.IGNORECASE,
)


def extract_academic(text: str) -> dict[str, Any]:
    """Spec §8 E — Academic documents (transcript / degree)."""
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}

    out["student_name"] = _extract_name(clean)

    out["transcript_keywords_found"] = any(k in flat for k in _TRANSCRIPT_KW)
    out["degree_keywords_found"] = any(k in flat for k in _DEGREE_KW)

    # Degree title — look for the degree-keyword line
    for kw in _DEGREE_KW:
        if kw in flat:
            idx = flat.index(kw)
            raw_line = clean[max(0, idx - 5): idx + 60]
            out["degree_title"] = normalize_spaces(raw_line)
            break

    if m := _INSTITUTION_RX.search(clean):
        out["institution"] = m.group(0).strip()

    if m := _GRAD_YEAR_RX.search(clean):
        out["graduation_year"] = m.group(1)
    else:
        # Fallback: any 4-digit year in 1980–2030
        year_m = re.search(r"\b(19[89]\d|20[0-2]\d|2030)\b", clean)
        if year_m:
            out["graduation_year"] = year_m.group(1)

    return out


# ---------- F) HEC Attestation -------------------------------------------

_HEC_KEYWORDS = (
    "higher education commission", "hec", "attestation",
    "degree attestation", "verification",
)


def extract_hec(text: str) -> dict[str, Any]:
    """Spec §8 F — HEC Attestation."""
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}

    out["has_hec_keywords"] = any(k in flat for k in _HEC_KEYWORDS)
    out["attestation_keywords_found"] = "attestation" in flat

    out["applicant_name"] = _extract_name(clean)
    if m := _DOI_RX.search(clean):
        out["issue_date"] = _try_parse_date(m.group(1))

    return out


# ---------- G) IBCC Attestation / Equivalence ----------------------------

_IBCC_KEYWORDS = (
    "inter board committee of chairmen", "ibcc",
    "equivalence", "equivalency", "attestation", "matric",
    "intermediate",
)


def extract_ibcc(text: str) -> dict[str, Any]:
    """Spec §8 G — IBCC Attestation / Equivalence."""
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}

    out["has_ibcc_keywords"] = any(k in flat for k in _IBCC_KEYWORDS)
    out["equivalence_keywords_found"] = (
        "equivalence" in flat or "equivalency" in flat
    )
    out["applicant_name"] = _extract_name(clean)
    if m := _DOI_RX.search(clean):
        out["issue_date"] = _try_parse_date(m.group(1))

    return out


# ---------- H) MOFA Attestation ------------------------------------------

_MOFA_KEYWORDS = (
    "ministry of foreign affairs", "mofa",
    "attestation", "apostille", "authentication",
)


def extract_mofa(text: str) -> dict[str, Any]:
    """Spec §8 H — MOFA Attestation."""
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}

    out["has_mofa_keywords"] = any(k in flat for k in _MOFA_KEYWORDS)
    out["attestation_keywords_found"] = (
        "attestation" in flat or "apostille" in flat
    )
    out["applicant_name"] = _extract_name(clean)
    if m := _DOI_RX.search(clean):
        out["issue_date"] = _try_parse_date(m.group(1))

    return out


# ---------- I) Police Clearance ------------------------------------------

_POLICE_KEYWORDS = (
    "police", "character certificate", "clearance certificate",
    "no criminal record", "criminal record", "police report",
)


def extract_police(text: str) -> dict[str, Any]:
    """Spec §8 I — Police Clearance."""
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}

    out["has_police_keywords"] = any(k in flat for k in _POLICE_KEYWORDS)
    out["clearance_keywords_found"] = (
        "clearance" in flat or "no criminal record" in flat
    )
    out["applicant_name"] = _extract_name(clean)
    if m := _DOI_RX.search(clean):
        out["issue_date"] = _try_parse_date(m.group(1))

    return out


# ---------- J) TB Certificate --------------------------------------------

_TB_KEYWORDS = (
    "tuberculosis", "tb", "iom",
    "international organization for migration",
    "international organisation for migration",
    "chest x-ray", "chest xray", "medical certificate",
    "panel physician", "panel hospital", "medical examination",
    "no evidence of tb", "no active tb",
)


def extract_tb(text: str) -> dict[str, Any]:
    """Spec §8 J — TB Certificate."""
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}

    out["has_tb_keywords"] = any(k in flat for k in _TB_KEYWORDS)
    out["clinic_or_iom_keywords_found"] = (
        "iom" in flat
        or "international organization for migration" in flat
        or "international organisation for migration" in flat
        or "panel physician" in flat
        or "panel hospital" in flat
    )
    out["applicant_name"] = _extract_name(clean)
    if m := _DOI_RX.search(clean):
        out["issue_date"] = _try_parse_date(m.group(1))

    return out


# ---------- Sponsor letter / Offer letter (supporting) -------------------

def extract_sponsor(text: str) -> dict[str, Any]:
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}
    out["has_sponsor_keywords"] = any(
        k in flat for k in (
            "sponsor", "financial guarantee", "undertaking",
            "financially responsible", "will bear",
        )
    )
    out["applicant_name"] = _extract_name(clean)
    return out


def extract_offer_letter(text: str) -> dict[str, Any]:
    clean = normalize_ocr_text(text)
    flat = clean.lower()
    out: dict[str, Any] = {}
    out["has_offer_keywords"] = any(
        k in flat for k in (
            "offer of admission", "letter of acceptance",
            "cas", "unconditional offer", "conditional offer",
            "zulassung", "loa",
        )
    )
    out["applicant_name"] = _extract_name(clean)
    return out


# ---------- Dispatcher ---------------------------------------------------

# Map document_type strings → extractor functions
_EXTRACTORS: dict[str, Any] = {
    "nadra_documents": extract_nadra,
    "passport":        extract_passport,
    "passport_issuance": extract_passport,
    "ielts":           extract_english_test,
    "toefl":           extract_english_test,
    "english_test":    extract_english_test,
    "bank_statement":  extract_bank_statement,
    "transcript":      extract_academic,
    "degree_certificate": extract_academic,
    "academic_document": extract_academic,
    "hec_attestation": extract_hec,
    "ibcc_equivalence": extract_ibcc,
    "mofa_attestation": extract_mofa,
    "police_clearance": extract_police,
    "tb_test":         extract_tb,
    "sponsor_letter":  extract_sponsor,
    "offer_letter":    extract_offer_letter,
    "cas_letter":      extract_offer_letter,
    "loa_letter":      extract_offer_letter,
}


def extract_fields(text: str, document_type: str) -> dict[str, Any]:
    """Main entry point. Dispatch OCR text to the appropriate extractor.

    Returns a dict of typed extracted fields. Returns an empty dict (not
    an error) when the document type has no registered extractor.
    """
    if not text or not document_type:
        return {}
    fn = _EXTRACTORS.get(document_type.lower())
    if fn is None:
        log.debug(
            "extract_fields: no extractor for document_type=%r",
            document_type,
        )
        return {"note": f"No structured extractor for type '{document_type}'."}
    try:
        return fn(text) or {}
    except Exception:
        log.exception(
            "extract_fields: extractor raised for document_type=%r",
            document_type,
        )
        return {}
