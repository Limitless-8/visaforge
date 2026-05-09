"""
utils/text_cleaning.py
----------------------
Deterministic helpers for cleaning scraped scholarship text and
detecting duplicates by title.

Used by:
  * services/ingestion_service.py (cleans raw text on upsert)
  * services/scholarship_service.py (defence-in-depth at display time
    and during deduplication)

Design notes:
  * Pure-Python, regex-only — no extra dependencies.
  * BeautifulSoup is optional; if present we use it for robust HTML
    stripping, otherwise we fall back to a regex pass that handles the
    common cases.
  * "Nav noise" is a curated list of phrases that appear on most
    scholarship-source homepages (cookie banners, breadcrumbs, footer
    links). The list is conservative — we'd rather leave a few of these
    in than wipe legitimate content.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional


# ---------- HTML stripping -----------------------------------------------

_HTML_TAG_RX = re.compile(r"<[^>]+>")
_HTML_ENTITY_RX = re.compile(r"&([a-zA-Z]+|#\d+);")
_HTML_ENTITIES = {
    "nbsp": " ", "amp": "&", "lt": "<", "gt": ">", "quot": '"',
    "apos": "'", "ndash": "–", "mdash": "—", "hellip": "…",
    "lsquo": "'", "rsquo": "'", "ldquo": "“", "rdquo": "”",
    "copy": "©", "reg": "®", "trade": "™", "deg": "°",
    "pound": "£", "euro": "€",
}

# Markdown link/image artifacts left behind by some scrapers.
_MD_LINK_RX = re.compile(r"\[([^\]]+)\]\(\s*[^)]*\s*\)")
_MD_IMAGE_RX = re.compile(r"!\[([^\]]*)\]\(\s*[^)]*\s*\)")


def _strip_html(text: str) -> str:
    """Remove HTML tags + decode common entities, preferring bs4 if available."""
    if not text:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
    except ImportError:
        text = _HTML_TAG_RX.sub(" ", text)

    def _decode(m: "re.Match[str]") -> str:
        ent = m.group(1)
        if ent.startswith("#"):
            try:
                return chr(int(ent[1:]))
            except ValueError:
                return ""
        return _HTML_ENTITIES.get(ent.lower(), "")
    text = _HTML_ENTITY_RX.sub(_decode, text)
    return text


# ---------- Navigation / boilerplate noise -------------------------------

# Substrings (case-insensitive) that strongly indicate menu/footer junk.
# Used as line-level filters: a line containing any of these is dropped.
_NAV_SIGNALS: tuple[str, ...] = (
    "cookie",
    "privacy policy",
    "terms of use",
    "terms and conditions",
    "back to top",
    "skip to main content",
    "skip to content",
    "main navigation",
    "site map",
    "sitemap",
    "subscribe to our newsletter",
    "follow us",
    "share this",
    "search the site",
    "menu close",
    "toggle navigation",
    "©", "©",
    "all rights reserved",
)

# Whole-line equals these (single navigation words/phrases).
_NAV_EXACT: frozenset[str] = frozenset({
    "menu", "search", "home", "about", "contact", "login", "log in",
    "register", "sign in", "sign up", "français", "english",
    "previous", "next", "back", "close", "open menu", "share",
    "facebook", "twitter", "instagram", "linkedin", "youtube",
    "more", "read more", "learn more",
})


def _is_nav_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    low = s.lower()
    if low in _NAV_EXACT:
        return True
    if any(sig in low for sig in _NAV_SIGNALS):
        return True
    # Lines made entirely of bullet/separator characters
    if re.fullmatch(r"[\s·•|·\-\u2013\u2014_=\*]+", s):
        return True
    return False


# ---------- Whitespace normalization -------------------------------------

_WS_RX = re.compile(r"[ \t]+")
_NEWLINE_RUN_RX = re.compile(r"\n{3,}")


def _normalize_whitespace(text: str) -> str:
    text = _WS_RX.sub(" ", text)
    text = _NEWLINE_RUN_RX.sub("\n\n", text)
    return text.strip()


# ---------- Public API ----------------------------------------------------

def clean_text(
    text: Optional[str],
    *,
    max_chars: int = 500,
    drop_nav: bool = True,
) -> str:
    """Clean a block of scholarship text for safe display.

    Steps:
      1. Strip HTML tags + decode entities.
      2. Strip Markdown link/image syntax (keep the visible text).
      3. NFC-normalise unicode (canonical, NOT NFKC — NFKC would
         decompose chars like '…' into '...').
      4. Drop nav/menu/footer-looking lines.
      5. Collapse whitespace; keep paragraph breaks.
      6. Truncate to `max_chars` at a word boundary, with an ellipsis.

    `max_chars=0` disables truncation.
    """
    if not text:
        return ""
    text = _strip_html(text)
    text = _MD_IMAGE_RX.sub("", text)
    text = _MD_LINK_RX.sub(r"\1", text)
    text = unicodedata.normalize("NFC", text)

    if drop_nav:
        kept_lines: list[str] = []
        for line in text.splitlines():
            if not _is_nav_line(line):
                kept_lines.append(line)
        text = "\n".join(kept_lines)

    text = _normalize_whitespace(text)

    if max_chars and len(text) > max_chars:
        truncated = text[:max_chars]
        cut = truncated.rfind(" ")
        if cut > max_chars * 0.7:
            truncated = truncated[:cut]
        text = truncated.rstrip(",;:- ").rstrip() + "…"
    return text


# ---------- Title normalization for dedupe -------------------------------

_TITLE_TOKEN_RX = re.compile(r"[a-z0-9]+")
_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "of", "for", "and", "in", "to", "on",
    "at", "by", "with", "from", "is", "as", "or",
})


def _stem(token: str) -> str:
    """Light singular/plural normalisation. Not a full stemmer — just
    enough to merge 'scholarship' / 'scholarships', 'fellowship' /
    'fellowships', etc. without over-collapsing.

    Rules (applied in order, first match wins):
      * tokens of 3 or fewer chars are returned unchanged
        (avoids 'is' → 'i', 'us' → 'u', '2026' → '2026' etc.)
      * 'ies' → 'y'           (companies → company)
      * 'sses' → 'ss'         (classes → class)
      * 'shes'/'ches' → strip 'es'  (watches → watch)
      * trailing 's' (not 'ss') → strip
      * else unchanged
    """
    if len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith(("shes", "ches")):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _title_tokens(title: str) -> set[str]:
    if not title:
        return set()
    low = title.lower()
    toks = _TITLE_TOKEN_RX.findall(low)
    return {
        _stem(t) for t in toks
        if t not in _STOPWORDS and len(t) > 1
    }


def title_similarity(a: str, b: str) -> float:
    """Jaccard similarity of significant title tokens, in [0.0, 1.0]."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    return len(inter) / len(union) if union else 0.0


def is_likely_duplicate(
    a_title: str, a_url: str,
    b_title: str, b_url: str,
    *,
    similarity_threshold: float = 0.85,
) -> bool:
    """Two entries look like duplicates if they share a source_url OR
    their normalised titles are highly similar."""
    if a_url and b_url and a_url.strip() == b_url.strip():
        return True
    if title_similarity(a_title, b_title) >= similarity_threshold:
        return True
    return False


def deduplicate(
    items: Iterable[object],
    *,
    title_attr: str = "title",
    url_attr: str = "source_url",
    similarity_threshold: float = 0.85,
) -> list[object]:
    """De-duplicate a list of items in-order, preferring the first occurrence.

    Uses URL exact match for the fast path; falls back to title-similarity
    Jaccard. Works with any object exposing the named attributes (DTOs,
    ORM rows, dicts via getattr fallback).
    """
    out: list[object] = []
    seen_urls: set[str] = set()
    seen_token_sets: list[set[str]] = []

    def _get(item: object, attr: str) -> str:
        if isinstance(item, dict):
            return str(item.get(attr) or "")
        return str(getattr(item, attr, "") or "")

    for item in items:
        url = _get(item, url_attr).strip()
        title = _get(item, title_attr)
        if url and url in seen_urls:
            continue
        toks = _title_tokens(title)
        is_dup = False
        for prev in seen_token_sets:
            if not toks or not prev:
                continue
            inter = toks & prev
            union = toks | prev
            if union and len(inter) / len(union) >= similarity_threshold:
                is_dup = True
                break
        if is_dup:
            continue
        out.append(item)
        if url:
            seen_urls.add(url)
        if toks:
            seen_token_sets.append(toks)
    return out


# ======================================================================
# OCR text cleaning  (Phase 5.8 — separate from scholarship cleaning)
# ======================================================================
#
# These functions are called by services/document_extraction_service.py
# to clean raw OCR output before field extraction.  Unlike the
# scholarship-text utilities above, they are conservative: we prefer
# leaving noise intact over destroying valid data (especially for
# identity documents where every character matters).

import re as _re  # already imported at top; alias avoids shadowing

_MULTI_SPACE_RX = _re.compile(r"[ \t]{2,}")
_CRLF_RX = _re.compile(r"\r\n?")

# Horizontal rules often produced by table-edge detection
_RULE_RX = _re.compile(r"^[\-=_*]{4,}\s*$", _re.MULTILINE)

# Characters Tesseract/PaddleOCR commonly substitute for each other in
# *numeric* contexts.  We apply these ONLY when the target character is
# surrounded by other digits (so we don't mangle names).
_DIGIT_CONTEXT_RX = _re.compile(
    r"(?<=\d)([OoQlISBZ])(?=\d)"
    r"|(?<=\d)([OoQlISBZ])$"
    r"|^([OoQlISBZ])(?=\d)"
)
_OCR_CHAR_FIXES = {
    "O": "0", "o": "0", "Q": "0",
    "l": "1", "I": "1",
    "S": "5", "s": "5",
    "B": "8", "b": "8",
    "Z": "2",
}

# CNIC canonical pattern after cleaning
_CNIC_LOOSE_RX = _re.compile(
    r"(\d[\dOoQlISBZ]{4})"    # group 1 — 5 digits
    r"[\-\s.]+"
    r"(\d[\dOoQlISBZ]{6})"    # group 2 — 7 digits
    r"[\-\s.]+"
    r"([\dOoQlISBZ])"          # group 3 — 1 digit
)


def normalize_ocr_text(text: str) -> str:
    """Lightweight OCR output normalisation.

    * CRLF → LF
    * Collapse inline whitespace (multi-spaces → single)
    * Remove pure horizontal-rule lines
    * Collapse 3+ consecutive blank lines to 2
    """
    if not text:
        return ""
    text = _CRLF_RX.sub("\n", text)
    text = _MULTI_SPACE_RX.sub(" ", text)
    text = _RULE_RX.sub("", text)
    # Collapse run of blank lines
    text = _re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fix_common_ocr_confusions(text: str) -> str:
    """Fix digit/letter substitutions that Tesseract and PaddleOCR
    make in numeric contexts.

    Conservative: only corrects a letter when it appears between, or
    immediately adjacent to, actual digits (e.g. 4210l → 42101, but
    'Pakistan' is left untouched because 'l' in names is intentional).
    """
    if not text:
        return ""

    def _fix(m: "re.Match[str]") -> str:
        # Only one of the three groups will match at a time.
        ch = m.group(1) or m.group(2) or m.group(3)
        return _OCR_CHAR_FIXES.get(ch, ch)

    return _DIGIT_CONTEXT_RX.sub(_fix, text)


def extract_cnic(text: str) -> Optional[str]:
    """Extract and normalise a CNIC number from OCR text.

    Returns the canonical "XXXXX-XXXXXXX-X" form, or None if not found.
    Accepts OCR variants (spaces, dots, stray OCR-confused characters).

    Strategy:
      1. Try the strict digit-only regex on the raw text first (fast path
         for good-quality OCR where Tesseract got it right).
      2. If that fails, create a fully-repaired copy of the text where
         ALL visually-confusable characters are replaced with their digit
         equivalents, then apply the strict regex. This handles cases like
         "42IOl-1234567-l" → "42101-1234567-1" where multiple chars in
         the CNIC field are misread as letters.
    """
    if not text:
        return None

    def _normalise_candidate(raw: str) -> Optional[str]:
        digits = _re.sub(r"[^\d]", "", raw)
        if len(digits) == 13:
            return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"
        return None

    # Step 1: strict match on raw text
    m = _CNIC_LOOSE_RX.search(text)
    if m:
        result = _normalise_candidate(
            m.group(1) + m.group(2) + m.group(3)
        )
        if result:
            return result

    # Step 2: repair ALL confusable chars then retry
    _ALL_OCR_FIXES = str.maketrans({
        "O": "0", "o": "0", "Q": "0", "q": "0",
        "I": "1", "i": "1", "l": "1", "|": "1",
        "B": "8", "b": "8",
        "S": "5", "s": "5",
        "Z": "2", "z": "2",
        "G": "6", "g": "9",
    })
    repaired = text.translate(_ALL_OCR_FIXES)
    m = _CNIC_LOOSE_RX.search(repaired)
    if m:
        result = _normalise_candidate(
            m.group(1) + m.group(2) + m.group(3)
        )
        if result:
            return result

    return None


def normalize_spaces(text: str) -> str:
    """Collapse all Unicode whitespace spans to a single ASCII space
    and strip leading/trailing whitespace."""
    return _re.sub(r"\s+", " ", text).strip() if text else ""


def fuzzy_find_label_value(
    text: str,
    labels: "Iterable[str]",
    *,
    max_gap: int = 40,
) -> Optional[str]:
    """Find the value after the first matching label in OCR text.

    Searches for any label (case-insensitive) followed by an optional
    colon/dash and captures up to `max_gap` non-newline characters.
    Returns the captured value stripped of leading/trailing whitespace,
    or None if not found.

    Useful for label: value patterns on forms and identity documents
    where line layout may be imperfect.
    """
    pat = (
        r"(?i)(?:"
        + "|".join(_re.escape(lbl) for lbl in labels)
        + r")\s*[:\-]?\s*(.{1," + str(max_gap) + r"}?)(?=\n|$)"
    )
    m = _re.search(pat, text)
    if m:
        return m.group(1).strip() or None
    return None
