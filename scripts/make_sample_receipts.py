"""Buat nota sintetis (gambar mirip foto) beserta kunci jawabannya untuk menguji OCR.

Contoh: python scripts/make_sample_receipts.py --n 30 --difficulty normal --out data/samples
Tingkat kesulitan: easy (lurus, bersih), normal (miring sedikit, buram tipis), hard (miring,
buram, berbintik, terkompresi).
"""
import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf", "/System/Library/Fonts/Menlo.ttc",
]
STORES = ["WARUNG MAKAN SEDERHANA", "KAFE SENJA", "TOKO BERKAH JAYA", "MINIMARKET SEJAHTERA",
          "RM PADANG SALERO", "BAKSO PAK KUMIS", "APOTEK SEHAT", "TOKO ROTI MANIS",
          "SATE KHAS SENAYAN", "WARKOP KAWAN LAMA", "SUPERMARKET MAKMUR", "AYAM GEPREK JUARA"]
MENU = [("Nasi Goreng Spesial", 25000), ("Es Teh Manis", 5000), ("Ayam Bakar", 35000), ("Mie Ayam Bakso", 18000),
        ("Kopi Susu", 18000), ("Croissant", 22000), ("Beras Premium 5kg", 68000), ("Minyak Goreng 2L", 38000),
        ("Telur Ayam 1kg", 29000), ("Gula Pasir 1kg", 17500), ("Air Mineral 600ml", 4000), ("Roti Tawar", 15500),
        ("Sate Ayam 10 tusuk", 28000), ("Soto Betawi", 32000), ("Jus Alpukat", 16000), ("Teh Tarik", 12000),
        ("Indomie Goreng", 3500), ("Susu UHT 1L", 19500), ("Sabun Mandi", 6500), ("Paracetamol Strip", 9000),
        ("Nasi Putih", 6000), ("Tempe Goreng", 8000), ("Es Jeruk", 8000), ("Kerupuk Udang", 12000)]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
WIDTH = 36  # lebar kolom karakter


def rp(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_date(d: date, style: int) -> str:
    return [f"{d:%d/%m/%Y}", f"{d:%d-%m-%y}", f"{d.day} {MONTHS[d.month - 1]} {d.year}", f"{d:%Y-%m-%d}"][style]


def row(left: str, right: str) -> str:
    left = left[: WIDTH - len(right) - 1]
    return left + " " * (WIDTH - len(left) - len(right)) + right


def build_receipt(rng: random.Random, idx: int) -> tuple[list[str], dict]:
    n_items = rng.randint(2, 7)
    chosen = rng.sample(MENU, n_items)
    style = rng.choice(["two_line", "inline", "qty_first"])
    d = date(2026, 1, 1) + timedelta(days=rng.randint(0, 270))
    toko = rng.choice(STORES)

    lines = [toko.center(WIDTH), "Jl. Kaliurang Km 5 No 123".center(WIDTH),
             f"Telp 0274-{rng.randint(100000, 999999)}".center(WIDTH), "-" * WIDTH,
             f"{fmt_date(d, rng.randint(0, 3))}  {rng.randint(8, 21):02d}:{rng.randint(0, 59):02d}",
             f"Kasir: {rng.choice(['Budi', 'Sari', 'Andi', 'Rina'])}", "-" * WIDTH]
    items, subtotal = [], 0
    for nama, harga in chosen:
        qty = rng.choice([1, 1, 1, 2, 2, 3])
        sub = qty * harga
        subtotal += sub
        items.append({"nama": nama, "qty": qty, "subtotal": sub})
        if qty == 1 and style != "two_line" and rng.random() < 0.6:
            lines.append(row(nama, rp(sub)))
        elif style == "two_line":
            lines += [nama, row(f"  {qty} x {rp(harga)}", rp(sub))]
        elif style == "inline":
            lines.append(row(f"{nama} {qty}x{rp(harga)}", rp(sub)) if len(nama) + len(rp(harga)) + 8 < WIDTH - 8
                         else row(nama, rp(sub)))
        else:
            lines.append(row(f"{qty} {nama}", rp(sub)))

    diskon = rng.choice([0, 0, 0, 5000, 10000])
    ppn = round(subtotal * 0.11) if rng.random() < 0.5 else 0
    total = subtotal - diskon + ppn
    bayar = int(np.ceil(total / 10000) * 10000) if rng.random() < 0.8 else total
    lines += ["-" * WIDTH, row("Subtotal", rp(subtotal))]
    if diskon:
        lines.append(row("Diskon", rp(diskon)))
    if ppn:
        lines.append(row("PPN 11%", rp(ppn)))
    lines += [row("TOTAL", rp(total)), row("TUNAI", rp(bayar)), row("KEMBALI", rp(bayar - total)),
              "", "Terima kasih".center(WIDTH)]
    return lines, {"file": f"nota_{idx:03d}.jpg", "toko": toko, "tanggal": d.isoformat(),
                   "total": total, "items": items}


def render(lines: list[str], font_path: str, difficulty: str, rng: random.Random) -> Image.Image:
    font = ImageFont.truetype(font_path, 22) if font_path else ImageFont.load_default()
    char_w = font.getlength("M")
    lh = 31
    w, h = int(char_w * WIDTH + 60), lh * len(lines) + 60
    paper = Image.new("L", (w, h), rng.randint(238, 252))
    draw = ImageDraw.Draw(paper)
    for i, ln in enumerate(lines):
        draw.text((30, 30 + i * lh), ln, fill=rng.randint(10, 50), font=font)

    cfg = {"easy": (0.0, 0.0, 2, 95), "normal": (2.5, 0.6, 7, 80), "hard": (5.0, 1.2, 15, 45)}[difficulty]
    angle, blur, noise, quality = cfg
    if difficulty != "easy":
        grad = np.linspace(rng.uniform(0.85, 1.0), rng.uniform(0.9, 1.05), w)[None, :]  # bayangan miring
        paper = Image.fromarray(np.clip(np.asarray(paper, dtype=np.float32) * grad, 0, 255).astype(np.uint8))
        canvas = Image.new("L", (w + 120, h + 120), 200)
        canvas.paste(paper, (60, 60))
        paper = canvas.rotate(rng.uniform(-angle, angle), resample=Image.BICUBIC, fillcolor=200)
    if blur:
        paper = paper.filter(ImageFilter.GaussianBlur(rng.uniform(blur * 0.5, blur)))
    arr = np.asarray(paper, dtype=np.float32) + np.random.default_rng(rng.randint(0, 10**6)).normal(0, noise, (paper.height, paper.width))
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGB")
    return img, quality


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--difficulty", choices=["easy", "normal", "hard"], default="normal")
    p.add_argument("--out", default="data/samples")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--font", default=None)
    args = p.parse_args()

    font = args.font or next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
    if font is None:
        sys.exit("Font monospace tidak ditemukan. Berikan lewat --font path/ke/font.ttf")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    truth = []
    for i in range(1, args.n + 1):
        lines, t = build_receipt(rng, i)
        img, quality = render(lines, font, args.difficulty, rng)
        img.save(out / t["file"], quality=quality)
        truth.append(t)
    (out / "truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{args.n} nota ({args.difficulty}) ditulis ke {out}/")


if __name__ == "__main__":
    main()
