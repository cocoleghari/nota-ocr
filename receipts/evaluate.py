"""Mengukur akurasi ekstraksi terhadap kunci jawaban (ground truth)."""
from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher

from .models import Receipt


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def similar(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def score_receipt(pred: Receipt, truth: dict) -> dict:
    """Bandingkan satu hasil ekstraksi dengan kunci jawabannya."""
    toko_ok = similar(pred.toko, truth["toko"]) >= 0.8
    tanggal_ok = pred.tanggal == date.fromisoformat(truth["tanggal"])
    total_ok = pred.total == truth["total"]

    used: set[int] = set()
    tp = 0
    for t in truth["items"]:
        for j, p in enumerate(pred.items):
            if j not in used and p.subtotal == t["subtotal"] and similar(p.nama, t["nama"]) >= 0.7:
                used.add(j)
                tp += 1
                break
    n_truth, n_pred = len(truth["items"]), len(pred.items)
    return {
        "file": truth.get("file", ""),
        "toko_ok": toko_ok, "tanggal_ok": tanggal_ok, "total_ok": total_ok,
        "item_tp": tp, "item_pred": n_pred, "item_truth": n_truth,
        "sempurna": toko_ok and tanggal_ok and total_ok and tp == n_truth == n_pred,
        "ditandai": bool(pred.warnings),
    }


def _pct(num: float, den: float) -> float | None:
    return None if den == 0 else num / den * 100


def aggregate(scores: list[dict]) -> dict:
    n = len(scores)
    salah = [s for s in scores if not s["sempurna"]]
    aman = [s for s in scores if not s["ditandai"]]
    return {
        "jumlah_nota": n,
        "toko_pct": _pct(sum(s["toko_ok"] for s in scores), n),
        "tanggal_pct": _pct(sum(s["tanggal_ok"] for s in scores), n),
        "total_pct": _pct(sum(s["total_ok"] for s in scores), n),
        "item_presisi_pct": _pct(sum(s["item_tp"] for s in scores), sum(s["item_pred"] for s in scores)),
        "item_recall_pct": _pct(sum(s["item_tp"] for s in scores), sum(s["item_truth"] for s in scores)),
        "sempurna_pct": _pct(len(scores) - len(salah), n),
        "ditandai_pct": _pct(sum(s["ditandai"] for s in scores), n),
        # dari nota yang salah, berapa persen sudah ditandai "perlu dicek"
        "kesalahan_tertangkap_pct": _pct(sum(s["ditandai"] for s in salah), len(salah)),
        # dari nota yang TIDAK ditandai, berapa persen memang benar semua
        "tanpa_tanda_benar_pct": _pct(sum(s["sempurna"] for s in aman), len(aman)),
    }
