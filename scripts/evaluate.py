"""Ukur akurasi ekstraksi pada folder nota yang punya truth.json.

Contoh: python scripts/evaluate.py data/samples --engine tesseract --psm 6
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from receipts.evaluate import aggregate, score_receipt  # noqa: E402
from receipts.extractors import OCRUnavailable, get_extractor  # noqa: E402
from receipts.models import Receipt  # noqa: E402

LABELS = [
    ("toko_pct", "Nama toko benar"), ("tanggal_pct", "Tanggal benar"), ("total_pct", "Total benar"),
    ("item_presisi_pct", "Item: presisi"), ("item_recall_pct", "Item: recall"),
    ("sempurna_pct", "Nota 100% benar"), ("ditandai_pct", "Nota ditandai 'perlu dicek'"),
    ("kesalahan_tertangkap_pct", "Nota salah yang ditandai"),
    ("tanpa_tanda_benar_pct", "Nota tanpa tanda yang benar"),
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder")
    p.add_argument("--engine", default="tesseract")
    p.add_argument("--psm", type=int, default=6, help="Mode segmentasi Tesseract")
    p.add_argument("--prep", default="auto", choices=["auto", "gray", "median", "binary"], help="Mode praproses gambar")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--show-errors", action="store_true")
    args = p.parse_args()

    folder = Path(args.folder)
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    if args.limit:
        truth = truth[: args.limit]
    kwargs = {"psm": args.psm, "prep": args.prep} if args.engine == "tesseract" else {}
    try:
        extractor = get_extractor(args.engine, **kwargs)
    except OCRUnavailable as exc:
        print(f"Mesin tidak siap: {exc}", file=sys.stderr)
        return 1

    scores = []
    for t in truth:
        try:
            pred = extractor.extract((folder / t["file"]).read_bytes())
        except Exception as exc:  # noqa: BLE001 - satu foto gagal tidak boleh menghentikan evaluasi
            pred = Receipt(warnings=[f"Gagal: {exc}"])
        s = score_receipt(pred, t)
        scores.append(s)
        if args.show_errors and not s["sempurna"]:
            print(f"- {t['file']}: toko={s['toko_ok']} tanggal={s['tanggal_ok']} total={s['total_ok']} "
                  f"item {s['item_tp']}/{s['item_truth']} (terbaca {s['item_pred']}) | "
                  f"pred total={pred.total} tgl={pred.tanggal} | {pred.warnings[:1]}")

    agg = aggregate(scores)
    print(f"\nEvaluasi {agg['jumlah_nota']} nota, mesin {args.engine}\n")
    for key, label in LABELS:
        v = agg[key]
        print(f"{label:34s} {'n/a' if v is None else f'{v:5.1f}%'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
