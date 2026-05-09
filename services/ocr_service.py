"""
services/ocr_service.py
-----------------------
OCR extension point. Not implemented in the MVP.

Suggested providers for future integration:
- pytesseract (local, free)
- AWS Textract
- Google Document AI
- Azure Form Recognizer
"""

from __future__ import annotations


def ocr_image(file_bytes: bytes) -> str:
    """Placeholder. Returns empty string in MVP."""
    _ = file_bytes  # silence linter
    return ""
