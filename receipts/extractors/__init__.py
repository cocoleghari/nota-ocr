"""Mesin ekstraksi nota. Semua mesin punya antarmuka sama: extract(bytes gambar) -> Receipt."""
from __future__ import annotations

from .base import Extractor, OCRUnavailable
from .claude_vision import ClaudeVisionExtractor
from .tesseract import TesseractExtractor

ENGINES = {
    "tesseract": TesseractExtractor,
    "claude": ClaudeVisionExtractor,
}


def get_extractor(name: str, **kwargs) -> Extractor:
    try:
        return ENGINES[name](**kwargs)
    except KeyError:
        raise ValueError(f"Mesin '{name}' tidak dikenal. Pilihan: {', '.join(ENGINES)}") from None


__all__ = ["ENGINES", "Extractor", "OCRUnavailable", "get_extractor",
           "TesseractExtractor", "ClaudeVisionExtractor"]
