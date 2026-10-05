from __future__ import annotations

from typing import Protocol

from ..models import Receipt


class OCRUnavailable(RuntimeError):
    """Mesin OCR belum siap dipakai (belum terpasang, kunci API kosong, dan sebagainya)."""


class Extractor(Protocol):
    name: str

    def extract(self, image_bytes: bytes) -> Receipt: ...
