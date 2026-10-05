"""OCR lokal dengan Tesseract: gratis dan data tidak keluar dari komputer."""
from __future__ import annotations

import os

from ..parser import parse_receipt
from ..preprocess import preprocess
from .base import OCRUnavailable


class TesseractExtractor:
    name = "tesseract"

    def __init__(self, lang: str | None = None, psm: int = 6, cmd: str | None = None, prep: str = "auto"):
        try:
            import pytesseract
        except ImportError as exc:  # pragma: no cover
            raise OCRUnavailable("Paket pytesseract belum terpasang (pip install pytesseract).") from exc
        self._pt = pytesseract
        cmd = cmd or os.getenv("TESSERACT_CMD")
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        try:
            installed = set(pytesseract.get_languages(config=""))
        except pytesseract.TesseractNotFoundError as exc:
            raise OCRUnavailable(
                "Program Tesseract tidak ditemukan. Pasang dari "
                "github.com/UB-Mannheim/tesseract/wiki (Windows), atau set TESSERACT_CMD."
            ) from exc
        if lang is None:  # pakai model Indonesia bila ada, jatuh ke Inggris bila tidak
            lang = "ind+eng" if "ind" in installed else "eng"
        missing = [x for x in lang.split("+") if x not in installed]
        if missing:
            raise OCRUnavailable(f"Model bahasa Tesseract belum terpasang: {', '.join(missing)}.")
        self.lang, self.psm, self.prep = lang, psm, prep

    def read_text(self, image_bytes: bytes) -> str:
        img = preprocess(image_bytes, self.prep)
        return self._pt.image_to_string(img, lang=self.lang, config=f"--oem 3 --psm {self.psm}")

    def extract(self, image_bytes: bytes):
        return parse_receipt(self.read_text(image_bytes), engine=f"tesseract ({self.lang})")
