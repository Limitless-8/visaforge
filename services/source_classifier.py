"""
services/source_classifier.py
-----------------------------
Deterministic source-type classification for scholarship ingestion.

Every scraped or seeded entry is classified into one of:

  * actual_scholarship       — a single funded opportunity
  * scholarship_directory    — a search/database listing many programmes
  * visa_policy_page         — visa/immigration policy content
  * generic_education_page   — generic university/study-abroad content
  * invalid_or_noise         — empty / 404-style / unscoreable

The classifier uses weighted keyword signals over title + URL + summary
+ source_name. Signals are tuned so that:
  * a single hit on a strong signal can flip the verdict
    (e.g. "visa requirements" anywhere → visa_policy_page),
  * mixed pages (a scholarship that mentions "visa fees covered") aren't
    miscategorised because scholarship signals carry their own weight,
  * empty / very short content goes to invalid_or_noise.

Pure Python, no AI, no network. Fully deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional


SourceType = Literal[
    # v0.8 originals
    "actual_scholarship",
    "scholarship_directory",
    "visa_policy_page",
    "generic_education_page",
    "invalid_or_noise",
    # v0.9 sub-pages crawled from a scholarship root
    "eligibility_page",
    "application_process_page",
    "deadline_page",
    "country_specific_page",
]

# Pages that are crawl by-products of a real scholarship root and should
# count toward user-visible scholarship records (per the v0.9 spec).
USER_VISIBLE_SOURCE_TYPES: frozenset[str] = frozenset({
    "actual_scholarship",
    "scholarship_directory",
    "eligibility_page",
    "application_process_page",
    "deadline_page",
    "country_specific_page",
})


# ---------- Signal definitions -------------------------------------------

# Each signal is a (regex, weight, target_type) tuple.
# Weights are positive floats. Stronger signals → higher weight.
# Patterns are matched case-insensitively against the combined haystack
# of (title + " " + summary + " " + source_name + " " + source_url).

@dataclass(frozen=True)
class _Signal:
    pattern: re.Pattern[str]
    weight: float
    target: SourceType
    label: str  # human label for traces


def _rx(pat: str) -> re.Pattern[str]:
    return re.compile(pat, re.IGNORECASE)


# --- visa / immigration ---------------------------------------------------

_VISA_SIGNALS: tuple[_Signal, ...] = (
    _Signal(_rx(r"\bvisa requirements?\b"),         3.0, "visa_policy_page", "title:visa requirements"),
    _Signal(_rx(r"\bentry requirements?\b"),        2.5, "visa_policy_page", "title:entry requirements"),
    _Signal(_rx(r"\bexemptions? for entry\b"),      3.0, "visa_policy_page", "title:exemptions for entry"),
    _Signal(_rx(r"\bfederal foreign office\b"),     3.0, "visa_policy_page", "publisher:foreign office"),
    _Signal(_rx(r"\bauswaertiges[- ]amt\b"),        3.0, "visa_policy_page", "domain:auswaertiges-amt"),
    _Signal(_rx(r"\bauswärtiges[- ]amt\b"),         3.0, "visa_policy_page", "domain:auswärtiges-amt"),
    _Signal(_rx(r"\bschengen\s+visa\b"),            3.0, "visa_policy_page", "kw:schengen visa"),
    _Signal(_rx(r"\bnational visa\b"),              2.5, "visa_policy_page", "kw:national visa"),
    _Signal(_rx(r"\bresidence permit\b"),           2.0, "visa_policy_page", "kw:residence permit"),
    _Signal(_rx(r"\bconsular\b"),                   1.5, "visa_policy_page", "kw:consular"),
    _Signal(_rx(r"\bembassy\b"),                    1.5, "visa_policy_page", "kw:embassy"),
    _Signal(_rx(r"\bimmigration policy\b"),         2.5, "visa_policy_page", "kw:immigration policy"),
    _Signal(_rx(r"\bvisa policy\b"),                3.0, "visa_policy_page", "kw:visa policy"),
    _Signal(_rx(r"/visa[/-]"),                      2.5, "visa_policy_page", "url:/visa/"),
    _Signal(_rx(r"/visumservice"),                  3.0, "visa_policy_page", "url:visumservice"),
    _Signal(_rx(r"/einreisebestimmungen"),          3.0, "visa_policy_page", "url:einreisebestimmungen (entry rules)"),
    # Lighter signals that nudge toward visa_policy without dominating
    _Signal(_rx(r"\bstudent visa\b"),               1.2, "visa_policy_page", "kw:student visa"),
    _Signal(_rx(r"\bstudy permit\b"),               1.2, "visa_policy_page", "kw:study permit"),
)

# --- actual scholarship ---------------------------------------------------

_SCHOLARSHIP_SIGNALS: tuple[_Signal, ...] = (
    # Title-level (very strong)
    _Signal(_rx(r"\bscholarship(s)?\b"),            2.5, "actual_scholarship", "kw:scholarship"),
    _Signal(_rx(r"\bfellowship(s)?\b"),             2.5, "actual_scholarship", "kw:fellowship"),
    _Signal(_rx(r"\bbursary|bursaries\b"),          2.5, "actual_scholarship", "kw:bursary"),
    _Signal(_rx(r"\bstudentship(s)?\b"),            2.5, "actual_scholarship", "kw:studentship"),
    _Signal(_rx(r"\bgrant(s)? for students\b"),     2.0, "actual_scholarship", "kw:grant for students"),
    _Signal(_rx(r"\bphd grant\b"),                  2.0, "actual_scholarship", "kw:phd grant"),
    _Signal(_rx(r"\bresearch grant\b"),             1.5, "actual_scholarship", "kw:research grant"),
    _Signal(_rx(r"\btuition (fee )?waiver\b"),      2.0, "actual_scholarship", "kw:tuition waiver"),
    _Signal(_rx(r"\bfully[- ]funded\b"),            2.5, "actual_scholarship", "kw:fully-funded"),
    _Signal(_rx(r"\bfully[- ]paid\b"),              1.5, "actual_scholarship", "kw:fully-paid"),
    _Signal(_rx(r"\bmonthly stipend\b"),            2.5, "actual_scholarship", "kw:monthly stipend"),
    _Signal(_rx(r"\bstipend\b"),                    1.5, "actual_scholarship", "kw:stipend"),
    _Signal(_rx(r"\bdeutschlandstipendium\b"),      3.0, "actual_scholarship", "kw:deutschlandstipendium"),
    _Signal(_rx(r"\bcommonwealth\s+(masters?|phd|scholarship)\b"),
                                                    3.0, "actual_scholarship", "kw:commonwealth scholarship"),
    _Signal(_rx(r"\bchevening\b"),                  3.0, "actual_scholarship", "kw:chevening"),
    _Signal(_rx(r"\bvanier\b"),                     3.0, "actual_scholarship", "kw:vanier"),
    _Signal(_rx(r"\bbanting\b"),                    3.0, "actual_scholarship", "kw:banting"),
    _Signal(_rx(r"\berasmus\s+mundus\b"),           3.0, "actual_scholarship", "kw:erasmus mundus"),
    _Signal(_rx(r"\bgreat\s+scholarships?\b"),      3.0, "actual_scholarship", "kw:great scholarships"),
    _Signal(_rx(r"\b(daad)\s+(study|scholarship|funding)\b"),
                                                    2.5, "actual_scholarship", "kw:daad funding"),
    # Money / award signals (moderate weight)
    _Signal(_rx(r"\b(usd|gbp|eur|cad|aud|£|\$|€)\s?\d+[\d,.]*"),
                                                    1.0, "actual_scholarship", "kw:monetary award"),
    _Signal(_rx(r"\bcovers (tuition|living|travel)\b"),
                                                    1.5, "actual_scholarship", "kw:covers tuition/living"),
    _Signal(_rx(r"\bapplication deadline\b"),       1.0, "actual_scholarship", "kw:application deadline"),
)

# --- directory ----------------------------------------------------------

_DIRECTORY_SIGNALS: tuple[_Signal, ...] = (
    _Signal(_rx(r"\bscholarship\s+database\b"),     3.0, "scholarship_directory", "kw:scholarship database"),
    _Signal(_rx(r"\bscholarship\s+directory\b"),    3.0, "scholarship_directory", "kw:scholarship directory"),
    _Signal(_rx(r"\bsearch\s+scholarships?\b"),     2.5, "scholarship_directory", "kw:search scholarships"),
    _Signal(_rx(r"\bbrowse\s+scholarships?\b"),     2.5, "scholarship_directory", "kw:browse scholarships"),
    _Signal(_rx(r"\b(funding|scholarship)\s+finder\b"),
                                                    2.5, "scholarship_directory", "kw:scholarship finder"),
    _Signal(_rx(r"/scholarship-?database"),         3.0, "scholarship_directory", "url:scholarship-database"),
    _Signal(_rx(r"\bdaad\s+scholarship\s+database\b"),
                                                    3.5, "scholarship_directory", "kw:daad scholarship database"),
    # DAAD's own scholarship database root
    _Signal(_rx(r"daad\.de.*\b(stipendium|scholarship)\b"),
                                                    1.5, "scholarship_directory", "url:daad.de scholarship root"),
    # British Council Study UK scholarships hub (a directory of GREAT etc.)
    _Signal(_rx(r"study-uk\.britishcouncil\.org/scholarships"),
                                                    2.0, "scholarship_directory", "url:bc study-uk hub"),
)

# --- generic education (lighter weights — fallback bucket) -------------

_GENERIC_SIGNALS: tuple[_Signal, ...] = (
    _Signal(_rx(r"\bstudy in (the )?(uk|canada|germany)\b"),
                                                    1.0, "generic_education_page", "kw:study in <country>"),
    _Signal(_rx(r"\babout us\b"),                   1.0, "generic_education_page", "kw:about us"),
    _Signal(_rx(r"\badmissions?\b"),                0.8, "generic_education_page", "kw:admissions"),
    _Signal(_rx(r"\bcourses?\b"),                   0.4, "generic_education_page", "kw:courses"),
    _Signal(_rx(r"\bprogrammes?\b"),                0.4, "generic_education_page", "kw:programmes"),
    _Signal(_rx(r"\buniversities? in\b"),           0.8, "generic_education_page", "kw:universities in"),
)


# --- v0.9: sub-page types (crawled FROM a scholarship root) ------------
#
# These are tighter than the top-level scholarship signals: they fire
# only when the page is *specifically* about one facet (eligibility,
# how-to-apply, deadlines, or a country page). They get visibility
# because they're produced by following links from an already-trusted
# curated source — see services/source_registry_service.py.

_ELIGIBILITY_SIGNALS: tuple[_Signal, ...] = (
    _Signal(_rx(r"\beligibility (criteria|requirements?)\b"),
                                                    3.0, "eligibility_page", "kw:eligibility criteria"),
    _Signal(_rx(r"\bwho can apply\b"),              3.0, "eligibility_page", "kw:who can apply"),
    _Signal(_rx(r"\bam i eligible\b"),              3.0, "eligibility_page", "kw:am I eligible"),
    _Signal(_rx(r"/eligibility[/-]?"),              2.0, "eligibility_page", "url:/eligibility/"),
)

_APPLICATION_SIGNALS: tuple[_Signal, ...] = (
    _Signal(_rx(r"\bhow to apply\b"),               3.0, "application_process_page", "kw:how to apply"),
    _Signal(_rx(r"\bapplication (process|guide)\b"),
                                                    2.5, "application_process_page", "kw:application process"),
    _Signal(_rx(r"\bapplication form\b"),           2.0, "application_process_page", "kw:application form"),
    _Signal(_rx(r"\bsubmit your application\b"),    2.0, "application_process_page", "kw:submit application"),
    _Signal(_rx(r"/apply[/-]?"),                    1.5, "application_process_page", "url:/apply/"),
)

_DEADLINE_SIGNALS: tuple[_Signal, ...] = (
    _Signal(_rx(r"\bapplication deadline\b"),       3.0, "deadline_page", "kw:application deadline"),
    _Signal(_rx(r"\bkey dates?\b"),                 2.5, "deadline_page", "kw:key dates"),
    _Signal(_rx(r"\bimportant dates?\b"),           2.5, "deadline_page", "kw:important dates"),
    _Signal(_rx(r"\b(timeline|timetable)\b"),       2.0, "deadline_page", "kw:timeline"),
    _Signal(_rx(r"/deadline[s]?[/-]?"),             1.5, "deadline_page", "url:/deadline/"),
)

_COUNTRY_PAGE_SIGNALS: tuple[_Signal, ...] = (
    _Signal(_rx(r"\bscholarship[s]? for pakistani\b"),
                                                    3.5, "country_specific_page", "kw:for Pakistani"),
    _Signal(_rx(r"\bpakistan country page\b"),      3.5, "country_specific_page", "kw:Pakistan country page"),
    _Signal(_rx(r"\bcandidates? from pakistan\b"),  3.0, "country_specific_page", "kw:candidates from Pakistan"),
    _Signal(_rx(r"/pakistan[/-]?"),                 1.5, "country_specific_page", "url:/pakistan/"),
)

_ALL_SIGNALS: tuple[_Signal, ...] = (
    _VISA_SIGNALS + _SCHOLARSHIP_SIGNALS
    + _DIRECTORY_SIGNALS + _GENERIC_SIGNALS
    + _ELIGIBILITY_SIGNALS + _APPLICATION_SIGNALS
    + _DEADLINE_SIGNALS + _COUNTRY_PAGE_SIGNALS
)


# ---------- Result ------------------------------------------------------

@dataclass
class ClassificationResult:
    source_type: SourceType
    confidence: float        # top-bucket score, normalised 0..1
    reasons: list[str] = field(default_factory=list)  # which signals fired
    scores: dict[str, float] = field(default_factory=dict)


# ---------- Classifier ---------------------------------------------------

# Below this top-bucket score, we don't trust the classification enough
# to call it a scholarship — fall back to generic_education_page.
_MIN_SCHOLARSHIP_SCORE: float = 2.0
_MIN_VISA_SCORE: float = 2.0


def _haystack(
    title: str, summary: str, source_url: str, source_name: str,
) -> str:
    parts = [title or "", summary or "", source_name or "", source_url or ""]
    return " \n ".join(p for p in parts if p)


def classify_source(
    *,
    title: Optional[str],
    summary: Optional[str],
    source_url: Optional[str] = None,
    source_name: Optional[str] = None,
    deadline: Optional[str] = None,
) -> ClassificationResult:
    """Classify a scholarship-candidate entry deterministically."""
    title = (title or "").strip()
    summary = (summary or "").strip()
    source_url = (source_url or "").strip()
    source_name = (source_name or "").strip()

    # ---- invalid/noise short-circuit ----
    if not title or len(title) < 3:
        return ClassificationResult(
            source_type="invalid_or_noise", confidence=1.0,
            reasons=["title missing or too short"],
        )
    # If neither summary nor URL are present and title is generic, bail
    if not summary and not source_url:
        return ClassificationResult(
            source_type="invalid_or_noise", confidence=1.0,
            reasons=["no summary and no source URL"],
        )
    if title.lower() in {
        "404", "not found", "page not found", "untitled", "home", "index",
    }:
        return ClassificationResult(
            source_type="invalid_or_noise", confidence=1.0,
            reasons=[f"title matches noise pattern: {title!r}"],
        )

    # ---- signal scoring ----
    haystack = _haystack(title, summary, source_url, source_name)
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for sig in _ALL_SIGNALS:
        if sig.pattern.search(haystack):
            scores[sig.target] = scores.get(sig.target, 0.0) + sig.weight
            reasons.setdefault(sig.target, []).append(sig.label)

    # Title-only check for the strongest scholarship keywords —
    # boosts confidence when the title alone declares scholarship status.
    title_low = title.lower()
    title_scholarship_kws = (
        "scholarship", "fellowship", "bursary", "studentship",
        "chevening", "vanier", "banting", "deutschlandstipendium",
        "commonwealth", "great scholarship", "erasmus mundus",
    )
    if any(kw in title_low for kw in title_scholarship_kws):
        scores["actual_scholarship"] = scores.get(
            "actual_scholarship", 0.0
        ) + 1.5
        reasons.setdefault("actual_scholarship", []).append(
            "title keyword boost"
        )

    # Title-only check for visa keywords — same idea on the other side.
    title_visa_kws = (
        "visa requirements", "entry requirements",
        "exemptions for entry", "schengen visa",
        "national visa", "study permit", "student visa",
        "residence permit",
    )
    if any(kw in title_low for kw in title_visa_kws):
        scores["visa_policy_page"] = scores.get(
            "visa_policy_page", 0.0
        ) + 1.5
        reasons.setdefault("visa_policy_page", []).append(
            "title keyword boost"
        )

    # ---- pick winner ----
    if not scores:
        return ClassificationResult(
            source_type="generic_education_page", confidence=0.2,
            reasons=["no scholarship/visa signals matched"],
            scores={},
        )

    # Visa override: if visa signals are very strong AND scholarship
    # signals are light, classify as visa_policy_page even if a stray
    # word like "scholarship" appears.
    visa_score = scores.get("visa_policy_page", 0.0)
    schol_score = scores.get("actual_scholarship", 0.0)
    dir_score = scores.get("scholarship_directory", 0.0)

    # v0.9 sub-page override: when a sub-page signal (eligibility,
    # application_process, deadline, country_specific) crosses its
    # threshold, prefer it over actual_scholarship/scholarship_directory.
    # Sub-pages are crawl by-products *of* a scholarship and are
    # by definition more specific than the parent. Visa always wins
    # over sub-pages, so this check sits BELOW the visa override.
    _SUB_PAGE_TYPES = (
        "eligibility_page", "application_process_page",
        "deadline_page", "country_specific_page",
    )
    _MIN_SUB_PAGE_SCORE = 2.5
    sub_page_winner: Optional[tuple[str, float]] = None
    for st in _SUB_PAGE_TYPES:
        s = scores.get(st, 0.0)
        if s >= _MIN_SUB_PAGE_SCORE:
            if sub_page_winner is None or s > sub_page_winner[1]:
                sub_page_winner = (st, s)

    # Hard short-circuit: visa-policy-page if the URL/host is clearly a
    # consular/foreign-office endpoint, regardless of stray scholarship
    # words. This catches the auswaertiges-amt.de issue precisely.
    consular_url_rx = re.compile(
        r"(auswaertiges-amt|auswärtiges-amt|/visa[/-]|/visumservice|"
        r"/einreisebestimmungen|/embassy|/consulate|gov\.uk/student-visa|"
        r"canada\.ca/.*study-permit)",
        re.IGNORECASE,
    )
    if source_url and consular_url_rx.search(source_url):
        return ClassificationResult(
            source_type="visa_policy_page",
            confidence=min(1.0, max(visa_score, 3.0) / 5.0),
            reasons=reasons.get("visa_policy_page", []) + [
                "consular/foreign-office URL pattern"
            ],
            scores=scores,
        )

    # If visa wins with a comfortable margin and meets minimum, use it.
    if visa_score >= _MIN_VISA_SCORE and visa_score > max(
        schol_score, dir_score
    ):
        return ClassificationResult(
            source_type="visa_policy_page",
            confidence=min(1.0, visa_score / 5.0),
            reasons=reasons.get("visa_policy_page", []),
            scores=scores,
        )

    # v0.9 sub-page override (applied after visa check). When a sub-page
    # signal crossed its threshold, return it — sub-pages are intended
    # to outrank the generic actual_scholarship/scholarship_directory
    # buckets when the page is specifically about eligibility, applying,
    # deadlines, or a country-specific landing page.
    if sub_page_winner is not None:
        st, s = sub_page_winner
        return ClassificationResult(
            source_type=st,  # type: ignore[arg-type]
            confidence=min(1.0, s / 5.0),
            reasons=reasons.get(st, []),
            scores=scores,
        )

    # Otherwise pick the highest scoring bucket above its threshold.
    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    if best_type == "actual_scholarship" and best_score < _MIN_SCHOLARSHIP_SCORE:
        # Not enough signal — be conservative.
        return ClassificationResult(
            source_type="generic_education_page",
            confidence=0.3,
            reasons=reasons.get("generic_education_page", []) + [
                "insufficient scholarship signal"
            ],
            scores=scores,
        )

    if best_type == "scholarship_directory" and best_score < _MIN_SCHOLARSHIP_SCORE:
        return ClassificationResult(
            source_type="generic_education_page",
            confidence=0.3,
            reasons=reasons.get("generic_education_page", []) + [
                "insufficient directory signal"
            ],
            scores=scores,
        )

    return ClassificationResult(
        source_type=best_type,  # type: ignore[arg-type]
        confidence=min(1.0, best_score / 5.0),
        reasons=reasons.get(best_type, []),
        scores=scores,
    )


# ---------- Convenience -------------------------------------------------

def is_user_visible(source_type: Optional[str]) -> bool:
    """True if a record with this source_type should be shown to users."""
    if not source_type:
        # Pre-v0.8 records without a source_type are treated as visible
        # for back-compat — admin can re-run classification.
        return True
    return source_type in USER_VISIBLE_SOURCE_TYPES


def filter_user_visible(
    items: Iterable, type_attr: str = "source_type",
) -> list:
    """Filter an iterable, keeping only user-visible source types."""
    out = []
    for item in items:
        st = (
            item.get(type_attr) if isinstance(item, dict)
            else getattr(item, type_attr, None)
        )
        if is_user_visible(st):
            out.append(item)
    return out
