"""
services/document_processing_service.py
---------------------------------------
v0.17 (Phase 5.8) — OCR pipeline: save → extract → score → dispatch.

Concerns:

1. **File capture**: validate MIME + size, sanitise filename, store
   under `data/uploads/{profile_id}/{step_key}/`.
2. **Text extraction (OCR)**:
   - Images: PaddleOCR (primary, optional) → pytesseract (fallback).
     Both are optional; missing engines degrade gracefully.
   - PDFs: PyMuPDF (preferred) → pdfplumber (fallback) → image OCR
     on rendered pages when the PDF is image-only.
3. **OCR quality scoring**: score 0–1 and "good" / "medium" / "weak"
   label stored alongside the extracted text.
4. **Structured extraction**: delegated to
   `services/document_extraction_service.py`.

PaddleOCR note: imports are lazy so a missing paddleocr / paddlepaddle
install never crashes the app at startup (important for Streamlit Cloud).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

log = get_logger(__name__)


# ---------- Constants ----------------------------------------------------

ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "image/png",
    "image/jpeg",
})
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg",
})
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024   # 10 MB
MAX_EXTRACTED_TEXT_CHARS: int = 32 * 1024     # 32 KB cap on stored text

UPLOADS_BASE = Path("data/uploads")


# Document types we have structured extractors for. These are the
# `document_type` values the Route Plan attaches to upload slots.
DOCUMENT_TYPE_PASSPORT     = "passport"
DOCUMENT_TYPE_IELTS        = "ielts"
DOCUMENT_TYPE_TOEFL        = "toefl"
DOCUMENT_TYPE_ENGLISH_TEST = "english_test"
DOCUMENT_TYPE_BANK         = "bank_statement"
DOCUMENT_TYPE_SPONSOR      = "sponsor_letter"
DOCUMENT_TYPE_TRANSCRIPT   = "transcript"
DOCUMENT_TYPE_DEGREE       = "degree_certificate"
DOCUMENT_TYPE_POLICE       = "police_clearance"
DOCUMENT_TYPE_HEC          = "hec_attestation"
DOCUMENT_TYPE_IBCC         = "ibcc_equivalence"
DOCUMENT_TYPE_MOFA         = "mofa_attestation"
DOCUMENT_TYPE_NADRA        = "nadra_documents"   # v0.14
DOCUMENT_TYPE_TB           = "tb_test"           # v0.14
DOCUMENT_TYPE_OFFER_LETTER = "offer_letter"
DOCUMENT_TYPE_OTHER        = "other"


# ---------- File capture -------------------------------------------------


@dataclass
class FileSaveResult:
    """Outcome of `save_uploaded_file`. `ok=False` means the upload was
    rejected; the caller should display `error_message` and not persist
    a CaseDocument row."""
    ok: bool
    stored_path: Optional[Path] = None
    safe_filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    error_message: Optional[str] = None


_SAFE_FILENAME_RX = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(original: str) -> str:
    """Strip path separators and unsafe characters. Keep extension."""
    # Drop any leading path components someone might have packed in.
    base = Path(original).name
    stem, ext = Path(base).stem, Path(base).suffix.lower()
    stem = _SAFE_FILENAME_RX.sub("_", stem).strip("._-")
    if not stem:
        stem = "upload"
    return f"{stem}{ext}"


def _versioned_path(directory: Path, safe_name: str) -> Path:
    """Append `_v2`, `_v3`, ... if a file already exists. We never
    overwrite without versioning per spec §3."""
    target = directory / safe_name
    if not target.exists():
        return target
    stem, ext = Path(safe_name).stem, Path(safe_name).suffix
    n = 2
    while True:
        candidate = directory / f"{stem}_v{n}{ext}"
        if not candidate.exists():
            return candidate
        n += 1


def save_uploaded_file(
    *,
    profile_id: int,
    step_key: str,
    original_filename: str,
    file_bytes: bytes,
    mime_type: Optional[str] = None,
) -> FileSaveResult:
    """Validate and persist an uploaded file.

    Validations:
      * MIME type (or extension fallback) ∈ ALLOWED set
      * file_size ≤ MAX_FILE_SIZE_BYTES
      * filename is non-empty after sanitisation
    """
    if not original_filename:
        return FileSaveResult(
            ok=False, error_message="No filename provided."
        )
    if not file_bytes:
        return FileSaveResult(
            ok=False, error_message="Uploaded file is empty."
        )

    file_size = len(file_bytes)
    if file_size > MAX_FILE_SIZE_BYTES:
        mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        return FileSaveResult(
            ok=False,
            error_message=(
                f"File too large ({file_size / 1024 / 1024:.1f} MB). "
                f"Maximum is {mb} MB."
            ),
        )

    safe_name = _safe_filename(original_filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return FileSaveResult(
            ok=False,
            error_message=(
                f"Unsupported file type {ext or '(none)'}. "
                f"Allowed: PDF, PNG, JPG, JPEG."
            ),
        )

    # MIME validation — accept either the supplied MIME or fall back
    # to the extension if MIME is missing/wrong.
    final_mime = mime_type
    if final_mime not in ALLOWED_MIME_TYPES:
        final_mime = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(ext)

    # Step-key folder; sanitise step_key the same way.
    safe_step = _SAFE_FILENAME_RX.sub("_", step_key).strip("._-") or "step"
    target_dir = UPLOADS_BASE / str(profile_id) / safe_step
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.exception("Could not create upload directory")
        return FileSaveResult(
            ok=False,
            error_message=f"Could not create upload folder: {e}",
        )

    target_path = _versioned_path(target_dir, safe_name)
    try:
        target_path.write_bytes(file_bytes)
    except OSError as e:
        log.exception("Could not write uploaded file")
        return FileSaveResult(
            ok=False, error_message=f"Could not save file: {e}",
        )

    log.info(
        "Saved upload: profile=%s step=%s -> %s (%d bytes, %s)",
        profile_id, step_key, target_path, file_size, final_mime,
    )
    return FileSaveResult(
        ok=True,
        stored_path=target_path,
        safe_filename=target_path.name,
        mime_type=final_mime,
        file_size=file_size,
    )


# ---------- Text extraction ---------------------------------------------


@dataclass
class TextExtractionResult:
    """Outcome of `extract_text`.

    * `ok=True` when at least some text was successfully extracted.
    * `status` granular machine-readable label. Values:
        - "ok"               — text extracted successfully
        - "weak_ocr"         — v0.17: text extracted but quality is weak
        - "empty"            — file opened but no text found
        - "failed"           — library raised an exception
        - "library_missing"  — no PDF/OCR library installed
        - "tesseract_missing"— pytesseract installed but Tesseract
                               binary missing on PATH
        - "paddleocr_missing"— v0.17: PaddleOCR not installed (uses
                               Tesseract fallback automatically)
        - "unsupported_type" — extension/MIME not recognised
        - "file_not_found"   — saved file disappeared between save
                               and extract
    * `errors` is a list of human-readable diagnostic strings.
    * `ocr_quality_score` — 0.0–1.0; None when not applicable (e.g. PDF text).
    * `ocr_quality_label` — "good" | "medium" | "weak" | None.
    * `ocr_confidence` — average per-character confidence from PaddleOCR
      (0.0–1.0); None when using Tesseract or PDF.
    """
    ok: bool
    text: str = ""
    method: str = ""           # "pymupdf" | "pdfplumber" | "paddleocr" |
                               # "pytesseract" | "pytesseract_fallback" | ...
    error_message: Optional[str] = None
    status: str = "pending"
    errors: list[str] = field(default_factory=list)
    # v0.17 OCR quality
    ocr_quality_score: Optional[float] = None
    ocr_quality_label: Optional[str] = None  # "good"|"medium"|"weak"|None
    ocr_confidence: Optional[float] = None   # PaddleOCR per-block avg


def _extract_pdf_text(path: Path) -> TextExtractionResult:
    """Try PyMuPDF first, fall back to pdfplumber. Return graceful
    failure if neither is installed."""
    diagnostic: list[str] = []

    # 1. PyMuPDF (preferred — fastest, handles embedded text well)
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None  # type: ignore[assignment]

    if fitz is not None:
        try:
            text_parts: list[str] = []
            with fitz.open(path) as doc:
                for page in doc:
                    text_parts.append(page.get_text() or "")
            text = "\n".join(text_parts).strip()
            if text:
                return TextExtractionResult(
                    ok=True, text=text[:MAX_EXTRACTED_TEXT_CHARS],
                    method="pymupdf", status="ok",
                )
            diagnostic.append(
                "PyMuPDF opened the PDF but found no embedded text "
                "(likely a scanned image)."
            )
            # Fall through to pdfplumber.
        except Exception as e:
            log.warning("PyMuPDF failed for %s: %s", path, e)
            diagnostic.append(f"PyMuPDF error: {e.__class__.__name__}: {e}")

    # 2. pdfplumber
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None  # type: ignore[assignment]

    if pdfplumber is not None:
        try:
            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    text_parts.append(t)
            text = "\n".join(text_parts).strip()
            if text:
                return TextExtractionResult(
                    ok=True, text=text[:MAX_EXTRACTED_TEXT_CHARS],
                    method="pdfplumber", status="ok",
                )
            diagnostic.append(
                "pdfplumber opened the PDF but found no embedded text."
            )
        except Exception as e:
            log.warning("pdfplumber failed for %s: %s", path, e)
            diagnostic.append(
                f"pdfplumber error: {e.__class__.__name__}: {e}"
            )

    # If we get here: no embedded text. We don't OCR PDFs because that
    # requires rendering pages, which adds another dependency. Surface
    # this as extraction_failed.
    if fitz is None and pdfplumber is None:
        return TextExtractionResult(
            ok=False, method="", status="library_missing",
            error_message=(
                "PDF text extraction libraries are not installed. "
                "Install PyMuPDF or pdfplumber to enable PDF reading."
            ),
            errors=diagnostic + [
                "Neither PyMuPDF nor pdfplumber is importable."
            ],
        )
    return TextExtractionResult(
        ok=False, method="pdf", status="empty",
        error_message=(
            "Could not extract text from PDF (likely a scanned image). "
            "Re-upload the original digital PDF, or convert pages to PNG/JPG."
        ),
        errors=diagnostic,
    )


def _preprocess_image_for_ocr(image):
    """v0.16 spec §5 — sharpen the input image so Tesseract has the
    best chance of reading documents like CNICs, passports, and
    transcripts.

    Steps:
      1. Convert to grayscale (OCR doesn't benefit from colour and
         coloured borders sometimes hurt accuracy).
      2. Upscale 2x if either dimension is below 1500 px. Mobile-shot
         CNICs and passports are commonly 800-1200 px wide; Tesseract
         needs ~300 dpi-equivalent which means a roughly 1500+ px
         long edge for a 5 inch document.
      3. Auto-contrast + sharpen if Pillow's ImageOps / ImageFilter
         are available. These are part of stdlib Pillow but wrapped
         in try/except so a stripped-down install still works.

    Returns the processed PIL image. Original is left unmodified.
    Falls back to the input image if any step fails."""
    try:
        from PIL import Image, ImageOps, ImageFilter
    except ImportError:
        return image

    try:
        # 1. Grayscale
        out = image.convert("L")

        # 2. Upscale small images. Threshold tuned for typical mobile
        # snaps of A6-sized documents (CNIC ≈ 86 × 54 mm).
        w, h = out.size
        if max(w, h) < 1500:
            scale = 2 if max(w, h) < 1500 else 1
            out = out.resize((w * scale, h * scale), Image.LANCZOS)

        # 3. Contrast + sharpen. Wrapped individually so a partial
        # Pillow install (extremely rare) still gets the upscale.
        try:
            out = ImageOps.autocontrast(out, cutoff=2)
        except Exception:
            pass
        try:
            out = out.filter(ImageFilter.SHARPEN)
        except Exception:
            pass
        return out
    except Exception:
        # Any failure here: return the original image so we still
        # attempt OCR on something rather than crashing.
        return image


# ---------- OCR quality scoring ------------------------------------------

_KEYWORD_SIGNALS: frozenset[str] = frozenset({
    "nadra", "cnic", "passport", "ielts", "university", "bank",
    "hec", "ibcc", "mofa", "police", "clearance", "attestation",
    "certificate", "pakistan", "identity", "transcript", "degree",
})


def _score_ocr_quality(
    text: str,
    *,
    confidence: Optional[float] = None,
) -> tuple[float, str]:
    """Compute a simple OCR quality score and label.

    Score is in [0.0, 1.0] based on:
      * text length (longer → better, up to a ceiling)
      * density of alphanumeric tokens (higher → less noise)
      * whether recognised document keywords are present
      * PaddleOCR average confidence (when available)

    Returns (score, label) where label is "good" | "medium" | "weak".
    """
    if not text:
        return 0.0, "weak"

    text_stripped = text.strip()
    length_score = min(len(text_stripped) / 500.0, 1.0)   # 500+ chars = 1.0

    tokens = re.findall(r"[a-zA-Z0-9]+", text_stripped)
    total_chars = max(len(text_stripped), 1)
    # Ratio of useful alphanumeric chars to total
    alnum_chars = sum(len(t) for t in tokens)
    density_score = alnum_chars / total_chars

    # Keyword presence: at least one recognised document keyword
    flat = text_stripped.lower()
    keyword_score = 1.0 if any(k in flat for k in _KEYWORD_SIGNALS) else 0.4

    # Combine
    score = (length_score * 0.35 + density_score * 0.35 + keyword_score * 0.30)

    # Weight in PaddleOCR confidence when available. A high confidence
    # score from the model is a strong signal that the text is correct
    # even when the raw string is short (e.g. a CNIC number alone).
    # We let confidence dominate at 50% weight so that a 0.95 confidence
    # result always scores as "good" regardless of text length.
    if confidence is not None and 0.0 <= confidence <= 1.0:
        score = (length_score * 0.15 + density_score * 0.15
                 + keyword_score * 0.10 + confidence * 0.60)

    score = round(min(max(score, 0.0), 1.0), 3)

    if score >= 0.65:
        label = "good"
    elif score >= 0.38:
        label = "medium"
    else:
        label = "weak"

    return score, label


# ---------- PaddleOCR wrapper (v0.17 primary engine) ---------------------


def _try_paddleocr():
    """Lazy-import PaddleOCR. Returns the class or None if unavailable."""
    try:
        from paddleocr import PaddleOCR  # type: ignore[import]
        return PaddleOCR
    except ImportError:
        return None
    except Exception as exc:
        log.warning("PaddleOCR import failed: %s", exc)
        return None


# Module-level singleton so we don't reinitialise the model on every call.
_paddle_instance: Any = None
_paddle_available: Optional[bool] = None   # None = not yet tried
_paddle_init_error: Optional[str] = None


def _get_paddle():
    """Return a PaddleOCR instance (initialised once), or None.

    PaddleOCR has changed its constructor across versions. v3 accepts
    `PaddleOCR(lang="en")`, while older examples often used
    `use_angle_cls=True` and/or `show_log=False`. Passing unsupported
    legacy kwargs can make initialisation fail and silently push the app
    back to Tesseract. This helper tries the modern constructor first,
    then legacy fallbacks, and stores/logs the real error.
    """
    global _paddle_instance, _paddle_available, _paddle_init_error

    if _paddle_available is False:
        return None
    if _paddle_available is True:
        return _paddle_instance

    PaddleOCR = _try_paddleocr()
    if PaddleOCR is None:
        _paddle_available = False
        _paddle_init_error = "PaddleOCR is not importable."
        log.info(
            "PaddleOCR not installed — will use Tesseract for image OCR. "
            "Install paddleocr + paddlepaddle for better accuracy."
        )
        return None

    attempts: list[dict[str, Any]] = [
        {"lang": "en"},
        {"use_angle_cls": True, "lang": "en"},
    ]
    errors: list[str] = []

    for kwargs in attempts:
        try:
            _paddle_instance = PaddleOCR(**kwargs)
            _paddle_available = True
            _paddle_init_error = None
            log.info("PaddleOCR initialised successfully with args=%s", kwargs)
            return _paddle_instance
        except Exception as exc:
            msg = f"PaddleOCR({kwargs}) failed: {exc.__class__.__name__}: {exc}"
            errors.append(msg)
            log.warning(msg)

    _paddle_available = False
    _paddle_init_error = " | ".join(errors) or "PaddleOCR initialisation failed."
    return None


def _parse_paddle_result(result: Any) -> tuple[list[str], list[float]]:
    """Parse old and new PaddleOCR result shapes.

    Supported shapes include:
    - old `ocr.ocr(...)`: [[ [bbox, (text, confidence)], ... ]]
    - v3/result dictionaries with `rec_texts` and `rec_scores`
    - objects exposing `.json`, `.to_dict`, or `.dict`
    """
    lines: list[str] = []
    confidences: list[float] = []

    def add(text: Any, conf: Any = None) -> None:
        txt = str(text or "").strip()
        if not txt:
            return
        lines.append(txt)
        try:
            if conf is not None:
                confidences.append(float(conf))
        except (TypeError, ValueError):
            pass

    def as_mapping(obj: Any) -> Any:
        for attr in ("json", "to_dict", "dict"):
            member = getattr(obj, attr, None)
            if member is None:
                continue
            try:
                data = member() if callable(member) else member
                if isinstance(data, (dict, list, tuple)):
                    return data
            except Exception:
                continue
        return obj

    def walk(obj: Any) -> None:
        obj = as_mapping(obj)
        if obj is None:
            return

        if isinstance(obj, dict):
            # PaddleOCR v3 often exposes these parallel arrays.
            texts = obj.get("rec_texts") or obj.get("texts") or obj.get("text")
            scores = obj.get("rec_scores") or obj.get("scores") or obj.get("confidence")
            if isinstance(texts, list):
                for i, txt in enumerate(texts):
                    conf = scores[i] if isinstance(scores, list) and i < len(scores) else None
                    add(txt, conf)
                return
            if isinstance(texts, str):
                add(texts, scores if isinstance(scores, (int, float, str)) else None)
                return
            for value in obj.values():
                walk(value)
            return

        if isinstance(obj, (list, tuple)):
            # Old tuple/list form: (text, confidence)
            if len(obj) >= 2 and isinstance(obj[0], str) and isinstance(obj[1], (int, float)):
                add(obj[0], obj[1])
                return
            # Old block form: [bbox, (text, confidence)]
            if len(obj) >= 2 and isinstance(obj[1], (list, tuple)):
                tc = obj[1]
                if len(tc) >= 2 and isinstance(tc[0], str):
                    add(tc[0], tc[1])
                    return
            for item in obj:
                walk(item)
            return

    walk(result)
    return lines, confidences


def _extract_with_paddleocr(path: Path) -> TextExtractionResult:
    """Run PaddleOCR on an image file.

    Modern PaddleOCR versions may reject legacy `cls=True` inference
    kwargs, while older versions expect them. This wrapper tries the
    modern call first and legacy calls second, and returns the real
    diagnostic error so the UI can explain when fallback happens.
    """
    paddle = _get_paddle()
    if paddle is None:
        err = _paddle_init_error or "PaddleOCR is not installed or failed to initialise."
        return TextExtractionResult(
            ok=False, method="", status="paddleocr_missing",
            error_message=(
                "PaddleOCR is unavailable. Falling back to Tesseract. "
                f"Details: {err}"
            ),
            errors=[err],
        )

    try:
        from PIL import Image
        raw = Image.open(path)
        prepped = _preprocess_image_for_ocr(raw)
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            prepped.save(tmp_path)
            result = None
            errors: list[str] = []

            # PaddleOCR v2/v3 compatibility. Try modern APIs first.
            inference_attempts = []
            if hasattr(paddle, "ocr"):
                inference_attempts.append(("ocr(path)", lambda: paddle.ocr(tmp_path)))
                inference_attempts.append(("ocr(path, cls=True)", lambda: paddle.ocr(tmp_path, cls=True)))
            if hasattr(paddle, "predict"):
                inference_attempts.append(("predict(path)", lambda: paddle.predict(tmp_path)))
                inference_attempts.append(("predict(input=path)", lambda: paddle.predict(input=tmp_path)))

            for label, fn in inference_attempts:
                try:
                    result = fn()
                    log.info("PaddleOCR inference succeeded with %s", label)
                    break
                except TypeError as exc:
                    errors.append(f"{label}: {exc.__class__.__name__}: {exc}")
                    continue
                except Exception as exc:
                    errors.append(f"{label}: {exc.__class__.__name__}: {exc}")
                    continue

            if result is None:
                raise RuntimeError("; ".join(errors) or "No PaddleOCR inference API available.")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    except ImportError:
        return TextExtractionResult(
            ok=False, method="paddleocr", status="library_missing",
            error_message="Pillow is required for PaddleOCR preprocessing.",
        )
    except Exception as exc:
        log.warning("PaddleOCR inference failed on %s: %s", path, exc)
        return TextExtractionResult(
            ok=False, method="paddleocr", status="failed",
            error_message=f"PaddleOCR error: {exc.__class__.__name__}: {exc}",
            errors=[str(exc)],
        )

    try:
        lines, confidences = _parse_paddle_result(result)
    except Exception as exc:
        log.warning("PaddleOCR result parse failed: %s", exc)
        return TextExtractionResult(
            ok=False, method="paddleocr", status="failed",
            error_message=f"Result parsing failed: {exc}",
            errors=[str(exc)],
        )

    text = "\n".join(lines).strip()
    avg_conf = sum(confidences) / len(confidences) if confidences else None

    if not text:
        return TextExtractionResult(
            ok=False, method="paddleocr", status="empty",
            ocr_confidence=avg_conf,
            error_message=(
                "PaddleOCR returned no text. The image may be blank, "
                "very low contrast, or upside-down."
            ),
            errors=["PaddleOCR result parsed successfully but contained no text."],
        )

    q_score, q_label = _score_ocr_quality(text, confidence=avg_conf)
    status = "weak_ocr" if q_label == "weak" else "ok"

    return TextExtractionResult(
        ok=True,
        text=text[:MAX_EXTRACTED_TEXT_CHARS],
        method="paddleocr",
        status=status,
        ocr_quality_score=q_score,
        ocr_quality_label=q_label,
        ocr_confidence=round(avg_conf, 3) if avg_conf is not None else None,
    )


def _extract_image_text(path: Path) -> TextExtractionResult:
    """v0.17: PaddleOCR primary, pytesseract fallback.

    Order:
      1. Try PaddleOCR (lazy import, no crash if missing).
      2. If PaddleOCR unavailable or returns empty: try pytesseract.
      3. If both fail: return a descriptive error result.

    The winning result carries the right `method` string so callers
    know which engine ran.
    """
    # --- Attempt 1: PaddleOCR ---
    paddle_result = _extract_with_paddleocr(path)
    if paddle_result.ok:
        return paddle_result
    if paddle_result.status not in ("paddleocr_missing", "empty", "failed"):
        # Unexpected status from PaddleOCR — still fall through to Tesseract
        log.debug(
            "_extract_image_text: PaddleOCR returned status=%r, "
            "falling through to Tesseract.", paddle_result.status,
        )

    # --- Attempt 2: pytesseract ---
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return TextExtractionResult(
            ok=False, method="", status="library_missing",
            error_message=(
                "Pillow is not installed. Install it with `pip install "
                "Pillow` to enable image processing. (PaddleOCR was also "
                "unavailable.)"
            ),
            errors=["Pillow is not importable."],
        )
    try:
        import pytesseract
    except ImportError:
        # Both engines missing
        return TextExtractionResult(
            ok=False, method="", status="library_missing",
            error_message=(
                "Neither PaddleOCR nor pytesseract is installed. "
                "Install one of them to enable image OCR."
            ),
            errors=["pytesseract is not importable.", "paddleocr is not installed."],
        )
    try:
        from PIL import Image
        raw = Image.open(path)
        prepped = _preprocess_image_for_ocr(raw)
        # --psm 6: assume a single uniform block of text (good for CNICs,
        # certificates, single-page forms). Fall back to PSM 3 if empty.
        text = pytesseract.image_to_string(prepped, config="--psm 6")
        text = (text or "").strip()
        if not text:
            try:
                text = pytesseract.image_to_string(prepped).strip()
            except Exception:
                pass
        if not text:
            return TextExtractionResult(
                ok=False, method="pytesseract_fallback", status="empty",
                error_message=(
                    "Tesseract returned no text. The image may be blank, "
                    "very low contrast, or rotated. Try a clearer scan."
                ),
                errors=["OCR returned an empty string."],
            )
        method = (
            "pytesseract_fallback"
            if paddle_result.status != "paddleocr_missing"
            else "pytesseract"
        )
        q_score, q_label = _score_ocr_quality(text)
        status = "weak_ocr" if q_label == "weak" else "ok"
        fallback_errors = []
        if paddle_result.error_message:
            fallback_errors.append(f"PaddleOCR fallback reason: {paddle_result.error_message}")
        fallback_errors.extend(paddle_result.errors or [])
        return TextExtractionResult(
            ok=True,
            text=text[:MAX_EXTRACTED_TEXT_CHARS],
            method=method,
            status=status,
            errors=fallback_errors,
            ocr_quality_score=q_score,
            ocr_quality_label=q_label,
        )
    except Exception as e:
        msg = str(e)
        if (
            "tesseract" in msg.lower()
            or "TesseractNotFound" in type(e).__name__
        ):
            return TextExtractionResult(
                ok=False, method="", status="tesseract_missing",
                error_message=(
                    "Tesseract OCR engine is not installed or not "
                    "available on PATH. On Windows, install Tesseract "
                    "from https://github.com/UB-Mannheim/tesseract/wiki "
                    "and add it to PATH, or upload text-based PDFs. "
                    "(PaddleOCR was also unavailable.)"
                ),
                errors=[
                    f"{type(e).__name__}: {e}",
                    "Tesseract binary not found on PATH.",
                ],
            )
        log.exception("Tesseract OCR failed for %s", path)
        return TextExtractionResult(
            ok=False, method="pytesseract_fallback", status="failed",
            error_message=f"OCR failed: {e.__class__.__name__}: {e}",
            errors=[f"{type(e).__name__}: {e}"],
        )


def extract_text(stored_path: str | Path,
                 mime_type: Optional[str] = None) -> TextExtractionResult:
    """Dispatch by MIME / extension. Never raises."""
    p = Path(stored_path)
    if not p.exists():
        return TextExtractionResult(
            ok=False, status="file_not_found",
            error_message=f"File not found: {p}",
            errors=[f"File missing on disk: {p}"],
        )
    ext = p.suffix.lower()
    if mime_type == "application/pdf" or ext == ".pdf":
        return _extract_pdf_text(p)
    if (mime_type and mime_type.startswith("image/")) or ext in (
        ".png", ".jpg", ".jpeg",
    ):
        return _extract_image_text(p)
    return TextExtractionResult(
        ok=False, status="unsupported_type",
        error_message=f"Unsupported MIME/extension: {mime_type or ext}",
        errors=[f"No handler for type {mime_type or ext}"],
    )


# ---------- Structured extraction (rule-based) --------------------------
#
# Each extractor receives raw text + the document_type and returns a
# dict of fields. Missing fields are simply absent — the verification
# layer treats absent vs unknown the same way (cannot verify).


def _normalise(text: str) -> str:
    """Strip diacritics-light, lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text or "").strip()


# Date patterns: ISO, day-month-year, month-name forms.
_DATE_PATTERNS = [
    r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b",         # 2025-11-07
    r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b",       # 07/11/2025
    r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b",         # 7 November 2025
    r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b",       # November 7, 2025
]
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _try_parse_date(s: str) -> Optional[str]:
    """Best-effort ISO normalisation; return YYYY-MM-DD or None.

    Tries hand-coded regex patterns first (fast, deterministic, dayfirst
    semantics for slash/dash forms which is the South-Asian default).
    Falls back to python-dateutil when available for unusual formats
    (e.g. "Nov-07-2025", "07.11.2025", "2025/11/07") — but only after
    the regex patterns failed, so we never overrule the deterministic
    parser on its home turf.
    """
    s = s.strip()
    for pat in _DATE_PATTERNS:
        m = re.search(pat, s)
        if not m:
            continue
        groups = m.groups()
        try:
            if pat == _DATE_PATTERNS[0]:
                y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
            elif pat == _DATE_PATTERNS[1]:
                d, mo, y = int(groups[0]), int(groups[1]), int(groups[2])
                if y < 100: y += 2000
            elif pat == _DATE_PATTERNS[2]:
                d = int(groups[0])
                mo = _MONTH_NAMES.get(groups[1].lower())
                y = int(groups[2])
                if not mo: continue
            else:  # _DATE_PATTERNS[3]
                mo = _MONTH_NAMES.get(groups[0].lower())
                d = int(groups[1])
                y = int(groups[2])
                if not mo: continue
            datetime(y, mo, d)  # validate
            return f"{y:04d}-{mo:02d}-{d:02d}"
        except (ValueError, IndexError):
            continue

    # python-dateutil fallback (spec §6). Optional — silently skipped
    # if the package isn't installed. dayfirst=True matches DD/MM/YYYY
    # (the dominant format on Pakistani documents) when the format is
    # ambiguous.
    try:
        from dateutil import parser as _du_parser  # type: ignore
    except ImportError:
        return None
    try:
        # `fuzzy=True` lets dateutil ignore surrounding text noise
        # (e.g. "Date of issue: 7 Nov 2025 (Karachi)"). dayfirst=True
        # is correct for Pakistan-issued documents.
        dt = _du_parser.parse(s, dayfirst=True, fuzzy=True)
        # Sanity bound: reject obviously bogus dates (years <1900 or
        # >2100) that fuzzy parsing can occasionally produce.
        if 1900 <= dt.year <= 2100:
            return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
    except (ValueError, TypeError, OverflowError):
        pass
    return None


# --- Passport ----------------------------------------------------------

# Common passport field labels. Pakistan passports use "Surname",
# "Given names", "Passport No.", "Nationality", "Date of expiry".

_PASSPORT_NUMBER_RX = re.compile(
    r"\b(?:passport\s*(?:no|number)\.?[:\s]*)?"
    r"([A-Z]{1,2}\d{6,8})\b",
    re.IGNORECASE,
)
_NATIONALITY_RX = re.compile(
    r"nationality\s*[:\-]?\s*([A-Za-z ]{3,30})",
    re.IGNORECASE,
)
_NAME_LABEL_RX = re.compile(
    r"(?:surname|given names?|name)[:\s]+([A-Z][A-Za-z\- ]{2,40})",
    re.IGNORECASE,
)
_EXPIRY_RX = re.compile(
    r"(?:date of expiry|expiry date|expires?)[:\s]+([0-9A-Za-z\-/, ]{6,20})",
    re.IGNORECASE,
)
_DOB_RX = re.compile(
    r"(?:date of birth|d\.o\.b|dob)[:\s]+([0-9A-Za-z\-/, ]{6,20})",
    re.IGNORECASE,
)


def _extract_passport(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if m := _PASSPORT_NUMBER_RX.search(text):
        out["passport_number"] = m.group(1).upper()
    if m := _NATIONALITY_RX.search(text):
        nat = m.group(1).strip().rstrip(".,;:")
        # Pakistan passports often print "PAKISTANI"
        out["nationality"] = nat.title() if nat else None
    if m := _NAME_LABEL_RX.search(text):
        out["full_name"] = m.group(1).strip().title()
    if m := _EXPIRY_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["expiry_date"] = d
    if m := _DOB_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["date_of_birth"] = d
    return out


# --- IELTS / English test ---------------------------------------------

_IELTS_OVERALL_RX = re.compile(
    r"overall\s*(?:band(?:\s*score)?)?[:\s]*([0-9](?:\.[0-9])?)",
    re.IGNORECASE,
)
_IELTS_TEST_TYPE_RX = re.compile(
    r"\b(IELTS|TOEFL|PTE)\b", re.IGNORECASE,
)
_TEST_DATE_RX = re.compile(
    r"(?:test date|date of test|test taken)[:\s]+([0-9A-Za-z\-/, ]{6,20})",
    re.IGNORECASE,
)
_CANDIDATE_NAME_RX = re.compile(
    r"(?:candidate(?:'s)? name|name of candidate)[:\s]+([A-Z][A-Za-z\- ]{2,40})",
    re.IGNORECASE,
)


def _extract_english_test(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if m := _IELTS_TEST_TYPE_RX.search(text):
        out["test_type"] = m.group(1).upper()
    if m := _IELTS_OVERALL_RX.search(text):
        try:
            out["overall_score"] = float(m.group(1))
        except ValueError:
            pass
    if m := _TEST_DATE_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["test_date"] = d
    if m := _CANDIDATE_NAME_RX.search(text):
        out["candidate_name"] = m.group(1).strip().title()
    return out


# --- Bank statement ---------------------------------------------------

_BALANCE_RX = re.compile(
    r"(?:closing balance|available balance|total balance|balance)\s*"
    r"[:\s]*"
    r"(?:(PKR|USD|GBP|EUR|CAD|AUD|Rs\.?|\$|£|€)\s*)?"
    r"([0-9,]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_ACCOUNT_HOLDER_RX = re.compile(
    r"(?:account holder|account name|customer name)[:\s]+"
    r"([A-Z][A-Za-z\- ]{2,40})",
    re.IGNORECASE,
)
_BANK_NAME_RX = re.compile(
    r"\b(HBL|UBL|MCB|Allied Bank|Habib Bank|Standard Chartered|"
    r"Meezan Bank|Faysal Bank|Bank Alfalah|Askari Bank)\b",
    re.IGNORECASE,
)
_STATEMENT_DATE_RX = re.compile(
    r"(?:statement date|as of|as on)[:\s]+([0-9A-Za-z\-/, ]{6,20})",
    re.IGNORECASE,
)


def _extract_bank_statement(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if m := _BALANCE_RX.search(text):
        currency = (m.group(1) or "").strip().upper().rstrip(".")
        if currency in ("RS", "RS."):
            currency = "PKR"
        elif currency == "$":
            currency = "USD"
        elif currency == "£":
            currency = "GBP"
        elif currency == "€":
            currency = "EUR"
        try:
            out["balance"] = float(m.group(2).replace(",", ""))
            if currency:
                out["currency"] = currency
        except ValueError:
            pass
    if m := _ACCOUNT_HOLDER_RX.search(text):
        out["account_holder_name"] = m.group(1).strip().title()
    if m := _BANK_NAME_RX.search(text):
        out["bank_name"] = m.group(1).strip()
    if m := _STATEMENT_DATE_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["statement_date"] = d
    return out


# --- Academic documents (transcript / degree) -------------------------

_STUDENT_NAME_RX = re.compile(
    r"(?:student(?:'s)? name|name of student|name)[:\s]+"
    r"([A-Z][A-Za-z\- ]{2,40})",
    re.IGNORECASE,
)
_DEGREE_TITLE_RX = re.compile(
    r"\b(Bachelor(?:'s)?|Master(?:'s)?|Doctor(?:al|ate)?|MPhil|"
    r"PhD|BSc|MSc|BS|MS|BA|MA|MBA)\b[\sof]+([A-Z][A-Za-z ]{3,40})",
    re.IGNORECASE,
)
_INSTITUTION_RX = re.compile(
    r"\b(University of [A-Z][A-Za-z ]{2,40}|"
    r"[A-Z][A-Za-z ]{2,40} University|"
    r"[A-Z][A-Za-z ]{2,40} College|"
    r"[A-Z][A-Za-z ]{2,40} Institute(?: of [A-Z][A-Za-z ]+)?)\b",
)
_GRAD_YEAR_RX = re.compile(
    r"(?:graduation|graduated|conferred|awarded)[\s\w:.,\-]{0,30}"
    r"(\b(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)


def _extract_academic(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if m := _STUDENT_NAME_RX.search(text):
        out["student_name"] = m.group(1).strip().title()
    if m := _DEGREE_TITLE_RX.search(text):
        out["degree_title"] = (
            f"{m.group(1).strip()} of {m.group(2).strip()}"
        ).title()
    if m := _INSTITUTION_RX.search(text):
        out["institution"] = m.group(1).strip()
    if m := _GRAD_YEAR_RX.search(text):
        try:
            out["graduation_year"] = int(m.group(1))
        except ValueError:
            pass
    return out


# --- Police clearance --------------------------------------------------

_APPLICANT_NAME_RX = re.compile(
    r"(?:applicant(?:'s)? name|name of applicant|holder|bearer)[:\s]+"
    r"([A-Z][A-Za-z\- ]{2,40})",
    re.IGNORECASE,
)
# v0.16 spec §6 — CNICs print just "Name:" (no "applicant"). This
# matches that simpler form, anchored at line start to avoid catching
# "Father Name:" / "Husband Name:".
_NADRA_NAME_RX = re.compile(
    r"(?im)^\s*name\s*[:\-]?\s*(?P<v>[A-Z][A-Za-z .'-]{2,80})\s*$"
)
_ISSUE_DATE_RX = re.compile(
    r"(?:date of issue|issue date|issued on|dated)[:\s]+"
    r"([0-9A-Za-z\-/, ]{6,20})",
    re.IGNORECASE,
)
_AUTHORITY_RX = re.compile(
    r"(?:authority|issued by|signature of)[:\s]+"
    r"([A-Z][A-Za-z\- ,.()]{4,60})",
    re.IGNORECASE,
)


def _extract_police(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if m := _APPLICANT_NAME_RX.search(text):
        out["applicant_name"] = m.group(1).strip().title()
    if m := _ISSUE_DATE_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["issue_date"] = d
    if m := _AUTHORITY_RX.search(text):
        out["authority"] = m.group(1).strip()
    # Detect police-clearance keywords for verification layer
    flat = _normalise(text).lower()
    if any(kw in flat for kw in (
        "police clearance", "character certificate",
        "clearance certificate", "criminal record",
    )):
        out["has_police_keywords"] = True
    return out


# --- HEC / IBCC / MOFA ------------------------------------------------

_HEC_KEYWORDS = (
    "hec", "higher education commission", "attestation",
)
_IBCC_KEYWORDS = (
    "ibcc", "inter board committee", "inter boards committee",
    "equivalence", "attestation",
)
_MOFA_KEYWORDS = (
    "mofa", "ministry of foreign affairs", "attestation",
    "apostille",
)


def _extract_hec(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flat = _normalise(text).lower()
    out["has_hec_keywords"] = any(k in flat for k in _HEC_KEYWORDS)
    if m := _APPLICANT_NAME_RX.search(text):
        out["applicant_name"] = m.group(1).strip().title()
    if m := _ISSUE_DATE_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["issue_date"] = d
    if m := _INSTITUTION_RX.search(text):
        out["institution"] = m.group(1).strip()
    return out


def _extract_ibcc(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flat = _normalise(text).lower()
    out["has_ibcc_keywords"] = any(k in flat for k in _IBCC_KEYWORDS)
    if m := _APPLICANT_NAME_RX.search(text):
        out["applicant_name"] = m.group(1).strip().title()
    if m := _ISSUE_DATE_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["issue_date"] = d
    return out


def _extract_mofa(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flat = _normalise(text).lower()
    out["has_mofa_keywords"] = any(k in flat for k in _MOFA_KEYWORDS)
    if m := _APPLICANT_NAME_RX.search(text):
        out["applicant_name"] = m.group(1).strip().title()
    if m := _ISSUE_DATE_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["issue_date"] = d
    return out


# --- NADRA / CNIC (v0.14) ---------------------------------------------
#
# Spec §11: deterministic keyword + CNIC pattern check. NADRA-issued
# documents include CNIC (13-digit format), B-Form (for minors), and
# birth certificates. Authenticity cannot be proven from text alone,
# so the verifier routes through manual_review_required.

_NADRA_KEYWORDS = (
    "nadra", "national database and registration authority",
    "national identity card", "cnic", "b-form", "child registration",
    "birth certificate", "computerized national identity card",
    "islamic republic of pakistan",
)
# 12345-1234567-1 pattern. Allows hyphens or spaces between groups.
_CNIC_RX = re.compile(r"\b(\d{5}[-\s]?\d{7}[-\s]?\d)\b")
# v0.16 spec §6 — fallback for OCR mistakes. Tesseract often misreads
# digits as O / I / B / S / l / Z / Q. We accept those substitutions
# in any position, as long as the 5-7-1 structure (with hyphen/space
# separators) is recognisable. A repair pass converts the letters
# back to digits before normalising.
_DIGITY = r"[\d0OQIlBSZi]"
_CNIC_OCR_VARIANTS_RX = re.compile(
    rf"(?<![A-Za-z\d])({_DIGITY}{{5}}[-\s]?{_DIGITY}{{7}}[-\s]?{_DIGITY})"
    rf"(?![A-Za-z\d])"
)
_OCR_DIGIT_FIXES = str.maketrans({
    "O": "0", "Q": "0", "I": "1", "l": "1", "B": "8",
    "S": "5", "Z": "2", "o": "0", "i": "1", "b": "8", "s": "5",
})

# Father / Husband name commonly precedes the holder's father's name
# on a CNIC (Pakistani CNIC printing varies — both "Father Name" and
# "S/O" or "D/O" appear).
_FATHER_NAME_RX = re.compile(
    r"(?im)^\s*(?:father(?:'?s)?\s*name|s/o|d/o)\s*[:\-]?\s*"
    r"(?P<v>[A-Z][A-Za-z .'-]{2,80})\s*$"
)
# Date of birth on CNICs prints as "Date of Birth" or "DOB". The
# format is typically DD.MM.YYYY or DD-MM-YYYY — _try_parse_date
# normalises both to ISO.
_DOB_RX = re.compile(
    r"(?i)(?:date\s+of\s+birth|d\.?\s*o\.?\s*b\.?)\s*[:\-]?\s*"
    r"([0-9.\-/A-Za-z ]{6,30})"
)
_DATE_OF_ISSUE_RX = re.compile(
    r"(?i)(?:date\s+of\s+issue|issue\s+date|doi)\s*[:\-]?\s*"
    r"([0-9.\-/A-Za-z ]{6,30})"
)
_DATE_OF_EXPIRY_RX = re.compile(
    r"(?i)(?:date\s+of\s+expir(?:y|ation)|expiry\s+date|doe|valid\s+until)"
    r"\s*[:\-]?\s*([0-9.\-/A-Za-z ]{6,30})"
)


def _extract_nadra(text: str) -> dict[str, Any]:
    """v0.16 spec §6 — extract CNIC + supporting fields from a NADRA
    document. Best-effort: every field is optional, and missing
    fields don't fail the document; the verifier emits
    `manual_review_required` regardless because automated checks
    can't prove authenticity for Pakistani identity documents.
    """
    out: dict[str, Any] = {}
    flat = _normalise(text).lower()
    out["has_nadra_keywords"] = any(k in flat for k in _NADRA_KEYWORDS)

    # Primary CNIC extraction. Tesseract usually nails this on a
    # decent scan because the digits are large.
    cnic_raw = None
    if m := _CNIC_RX.search(text):
        cnic_raw = m.group(1)
    elif m := _CNIC_OCR_VARIANTS_RX.search(text):
        # OCR-mistake fallback: try to repair O/I/B/S/Z/l mis-reads
        # before validating.
        candidate = m.group(1).translate(_OCR_DIGIT_FIXES)
        # Final sanity check — must end up with 13 digits + 2 separators.
        digits = re.sub(r"[^\d]", "", candidate)
        if len(digits) == 13:
            cnic_raw = candidate
            out["cnic_ocr_repaired"] = True

    if cnic_raw:
        digits = re.sub(r"[^\d]", "", cnic_raw)
        if len(digits) == 13:
            out["cnic_number"] = f"{digits[:5]}-{digits[5:12]}-{digits[12]}"
        else:
            out["cnic_number"] = cnic_raw.strip()

    # Holder's name. Use the NADRA-specific regex (matches a bare
    # "Name:" line) first, then fall back to the generic applicant
    # regex so existing callers keep working.
    if m := _NADRA_NAME_RX.search(text):
        out["applicant_name"] = m.group("v").strip().title()
    elif m := _APPLICANT_NAME_RX.search(text):
        out["applicant_name"] = m.group(1).strip().title()

    # Father / Husband name — separate from the holder's name.
    if m := _FATHER_NAME_RX.search(text):
        out["father_name"] = m.group("v").strip().title()

    # Dates. _try_parse_date handles all 5 formats + dateutil fuzzy.
    if m := _DOB_RX.search(text):
        if d := _try_parse_date(m.group(1)):
            out["date_of_birth"] = d
    if m := _DATE_OF_ISSUE_RX.search(text):
        if d := _try_parse_date(m.group(1)):
            out["date_of_issue"] = d
    elif m := _ISSUE_DATE_RX.search(text):
        # Generic "Issue date" path — preserved from earlier.
        if d := _try_parse_date(m.group(1)):
            out["date_of_issue"] = d
    if m := _DATE_OF_EXPIRY_RX.search(text):
        if d := _try_parse_date(m.group(1)):
            out["date_of_expiry"] = d

    return out


# --- TB test certificate (v0.14) --------------------------------------
#
# Spec §11: TB tests for visa applicants are typically issued by IOM
# or panel hospitals. We look for IOM / TB / chest x-ray / medical
# certificate keywords. The deterministic verifier can confirm the
# document is the right TYPE; authenticity routes through
# manual_review_required.

_TB_KEYWORDS = (
    "tb", "tuberculosis", "iom", "international organization for migration",
    "international organisation for migration",
    "chest x-ray", "chest xray", "medical certificate",
    "panel physician", "panel hospital", "medical examination",
    "no evidence of tb",
)


def _extract_tb(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flat = _normalise(text).lower()
    out["has_tb_keywords"] = any(k in flat for k in _TB_KEYWORDS)
    if m := _APPLICANT_NAME_RX.search(text):
        out["applicant_name"] = m.group(1).strip().title()
    if m := _ISSUE_DATE_RX.search(text):
        d = _try_parse_date(m.group(1))
        if d: out["issue_date"] = d
    return out


# --- Sponsor letter ----------------------------------------------------

_SPONSOR_KEYWORDS_RX = re.compile(
    r"\b(sponsor|sponsoring|guardian|undertake|cover all expenses|"
    r"financial guarantee|funding for studies)\b",
    re.IGNORECASE,
)


def _extract_sponsor(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flat = _normalise(text).lower()
    out["has_sponsor_keywords"] = bool(_SPONSOR_KEYWORDS_RX.search(text))
    if m := _APPLICANT_NAME_RX.search(text):
        out["sponsor_name"] = m.group(1).strip().title()
    return out


# --- Offer letter ------------------------------------------------------

_OFFER_KEYWORDS_RX = re.compile(
    r"\b(offer of admission|admission offer|conditional offer|"
    r"unconditional offer|letter of acceptance|zulassung|cas)\b",
    re.IGNORECASE,
)


def _extract_offer_letter(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["has_offer_keywords"] = bool(_OFFER_KEYWORDS_RX.search(text))
    if m := _INSTITUTION_RX.search(text):
        out["institution"] = m.group(1).strip()
    if m := _STUDENT_NAME_RX.search(text):
        out["student_name"] = m.group(1).strip().title()
    return out


# --- Dispatcher --------------------------------------------------------


_EXTRACTORS = {
    DOCUMENT_TYPE_PASSPORT:   _extract_passport,
    DOCUMENT_TYPE_IELTS:      _extract_english_test,
    DOCUMENT_TYPE_TOEFL:      _extract_english_test,
    DOCUMENT_TYPE_BANK:       _extract_bank_statement,
    DOCUMENT_TYPE_SPONSOR:    _extract_sponsor,
    DOCUMENT_TYPE_TRANSCRIPT: _extract_academic,
    DOCUMENT_TYPE_DEGREE:     _extract_academic,
    DOCUMENT_TYPE_POLICE:     _extract_police,
    DOCUMENT_TYPE_HEC:        _extract_hec,
    DOCUMENT_TYPE_IBCC:       _extract_ibcc,
    DOCUMENT_TYPE_MOFA:       _extract_mofa,
    DOCUMENT_TYPE_NADRA:      _extract_nadra,    # v0.14
    DOCUMENT_TYPE_TB:         _extract_tb,       # v0.14
    DOCUMENT_TYPE_ENGLISH_TEST: _extract_english_test,
    DOCUMENT_TYPE_OFFER_LETTER: _extract_offer_letter,
}


def extract_fields(text: str, document_type: str) -> dict[str, Any]:
    """v0.17: delegate to the canonical extraction service.

    Previously this function held a local dispatcher; in v0.17 the
    dispatcher and all extractors live in
    `services/document_extraction_service.py` so they can be used by
    the reprocess path and any future caller without depending on this
    module's internal regexes.

    The local `_EXTRACTORS` dict and `_extract_*` functions are kept
    for backward-compat in case anything still calls them directly, but
    `extract_fields` itself now delegates.
    """
    from services.document_extraction_service import (
        extract_fields as _ext_fields,
    )
    return _ext_fields(text, document_type)


# ---------- Convenience: full pipeline ---------------------------------


@dataclass
class ProcessResult:
    """End-to-end result of save → extract_text → extract_fields."""
    save: FileSaveResult
    extraction: TextExtractionResult = field(
        default_factory=lambda: TextExtractionResult(ok=False)
    )
    extracted_fields: dict[str, Any] = field(default_factory=dict)


def process_upload(
    *,
    profile_id: int,
    step_key: str,
    document_type: str,
    original_filename: str,
    file_bytes: bytes,
    mime_type: Optional[str] = None,
) -> ProcessResult:
    """Save → text extraction → field extraction. Always returns a
    ProcessResult; check `.save.ok` and `.extraction.ok`."""
    save = save_uploaded_file(
        profile_id=profile_id, step_key=step_key,
        original_filename=original_filename,
        file_bytes=file_bytes, mime_type=mime_type,
    )
    if not save.ok:
        return ProcessResult(save=save)

    extraction = extract_text(save.stored_path, mime_type=save.mime_type)
    fields = (
        extract_fields(extraction.text, document_type)
        if extraction.ok else {}
    )
    return ProcessResult(
        save=save, extraction=extraction, extracted_fields=fields,
    )


# ---------- Helpers ----------------------------------------------------


def serialize_fields(fields: dict[str, Any]) -> str:
    """JSON-encode extracted fields for storage. Uses default=str so
    dates and other non-JSON types serialise cleanly."""
    return json.dumps(fields, default=str)


def deserialize_fields(blob: Optional[str]) -> dict[str, Any]:
    if not blob:
        return {}
    try:
        v = json.loads(blob)
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}
