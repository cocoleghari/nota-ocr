"""Mengubah teks hasil OCR menjadi Receipt terstruktur.

Pendekatan berbasis aturan yang dirancang untuk struk Indonesia: format angka 25.000, tanggal
dd/mm/yyyy atau "12 Sep 2026", kata kunci TOTAL/PPN/TUNAI, dan galat OCR yang umum (O jadi 0, l jadi 1).
"""
from __future__ import annotations

import re
from datetime import date

from .models import LineItem, Receipt

MONTHS = {
    "jan": 1, "januari": 1, "feb": 2, "februari": 2, "mar": 3, "maret": 3, "apr": 4, "april": 4,
    "mei": 5, "may": 5, "jun": 6, "juni": 6, "jul": 7, "juli": 7, "agu": 8, "agt": 8, "agus": 8,
    "agustus": 8, "aug": 8, "sep": 9, "sept": 9, "september": 9, "okt": 10, "oktober": 10,
    "oct": 10, "nov": 11, "november": 11, "des": 12, "desember": 12, "dec": 12,
}

# ---------------------------------------------------------------- angka
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5"})
_AMOUNT_TAIL = re.compile(r"(?P<amt>-?(?:Rp\.?\s*)?\d[\dOolI|S.,]*)\s*$")


def parse_amount(text: str) -> int | None:
    """Ubah teks nominal Rupiah ('Rp 25.000', '1.250.000,00', '25000') menjadi bilangan bulat."""
    s = re.sub(r"(?i)rp\.?", "", text).replace(" ", "").strip()
    if not s:
        return None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    if not s or not s[0].isdigit():  # token nominal selalu diawali angka; sisanya boleh salah baca (O, l, I)
        return None
    s = s.translate(_DIGIT_FIX)
    if not re.fullmatch(r"[\d.,]+", s):
        return None

    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot != -1 and last_comma != -1:  # keduanya ada: yang terakhir adalah desimal
        dec = "." if last_dot > last_comma else ","
        thou = "," if dec == "." else "."
        s = s.replace(thou, "").replace(dec, ".")
    elif last_dot != -1 or last_comma != -1:
        sep = "." if last_dot != -1 else ","
        parts = s.split(sep)
        if len(parts) > 2:
            s = "".join(parts)                      # 1.250.000
        elif len(parts[1]) == 3:
            s = "".join(parts)                      # 25.000 (ribuan)
        elif len(parts[1]) in (1, 2):
            s = parts[0] + "." + parts[1]           # 25,50 (desimal)
        elif parts[1] == "":
            s = parts[0]
        else:
            return None
    try:
        value = int(round(float(s)))
    except ValueError:
        return None
    return -value if neg else value


def _looks_like_money(token: str, value: int) -> bool:
    """Hindari nomor jalan, jam, atau kode: nominal harus >= 500 dan berpemisah atau >= 4 digit."""
    plain = re.sub(r"[^\d]", "", token)
    has_sep = bool(re.search(r"\d[.,]\d{3}\b", token))
    return abs(value) >= 500 and (has_sep or len(plain) >= 4)


def last_amount(line: str) -> int | None:
    m = _AMOUNT_TAIL.search(line)
    if not m:
        return None
    value = parse_amount(m.group("amt"))
    if value is None or not _looks_like_money(m.group("amt"), value):
        return None
    return value


# ---------------------------------------------------------------- tanggal dan jam
_CONFUSED_DATE = re.compile(r"\b[\dOoIl|]{1,2}[/\-.][\dOoIl|]{1,2}[/\-.][\dOoIl|]{2,4}\b")
_DATE_DMY = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_DATE_YMD = re.compile(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b")
_DATE_NAMED = re.compile(r"\b(\d{1,2})\s*([A-Za-z]{3,9})\.?\s*,?\s*(\d{2,4})\b")
_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(?::[0-5]\d)?\b")


def _make_date(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    if not 2000 <= y <= 2100:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    text = _CONFUSED_DATE.sub(lambda m: m.group(0).translate(_DIGIT_FIX), text)
    if m := _DATE_YMD.search(text):
        if d := _make_date(int(m[1]), int(m[2]), int(m[3])):
            return d
    for m in _DATE_DMY.finditer(text):
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        if d := _make_date(y, b, a) or _make_date(y, a, b):  # format Indonesia: hari dulu
            return d
    for m in _DATE_NAMED.finditer(text):
        month = MONTHS.get(m[2].lower())
        if month and (d := _make_date(int(m[3]), month, int(m[1]))):
            return d
    return None


def parse_time(text: str) -> str | None:
    m = _TIME.search(text)
    return f"{int(m[1]):02d}:{m[2]}" if m else None


# ---------------------------------------------------------------- klasifikasi baris
_SKIP_COUNT = re.compile(r"(?i)\b(total|jumlah)\s*(item|itm|qty|barang|produk|pcs)\b|\b(item|qty)\s*:")
_SUBTOTAL = re.compile(r"(?i)\bsub\s*-?\s*tota[l1i|]")
_KEMBALI = re.compile(r"(?i)\b(kembali(an)?|change)\b")
_DISKON = re.compile(r"(?i)\b(diskon|discount|disc|potongan|promo|voucher)\b")
_PAJAK = re.compile(r"(?i)\b(ppn|pajak|tax|pb1|service|servis|svc|biaya\s*layanan)\b")
_TOTAL = re.compile(r"(?i)\b(grand\s*tota[l1i|]|total\s*(bayar|tagihan|belanja)|tota[l1i|]|tagihan)\b")
_BAYAR = re.compile(r"(?i)\b(tunai|cash|dibayar|bayar|debit|kartu|qris|uang)\b")
_NOT_ITEM = re.compile(
    r"(?i)\b(jl|jalan|rt|rw|kel|kec|kota|kab|telp?|tlp|hp|wa|fax|npwp|kasir|cashier|struk|nota|"
    r"invoice|meja|table|terima\s*kasih|thank|selamat|wifi|password|www|http)\b|@\w+\.\w+"
)
_PHONE = re.compile(r"\b0\d{2,4}[- ]?\d{3,}[- ]?\d{2,}\b|\b62\d{8,}\b")


def classify(line: str) -> str | None:
    """Jenis baris ringkasan (subtotal/pajak/diskon/total/bayar/kembalian) atau 'skip'; None bila bukan."""
    c = re.sub(r"(?<=[A-Za-z])0|0(?=[A-Za-z])", "O", line)  # T0TAL -> TOTAL
    if _SKIP_COUNT.search(c):
        return "skip"
    for name, rx in (("subtotal", _SUBTOTAL), ("kembalian", _KEMBALI), ("diskon", _DISKON),
                     ("pajak", _PAJAK), ("total", _TOTAL), ("bayar", _BAYAR)):
        if rx.search(c):
            return name
    return None


# ---------------------------------------------------------------- baris item
_QTY_UNIT = re.compile(r"^(?P<name>.*?)\s*(?P<qty>\d{1,3})\s*[xX@*]\s*(?P<unit>\d[\dOolI|S.,]*)\s*$")
_QTY_FIRST = re.compile(r"^(?P<qty>\d{1,2})\s*[xX]?\s+(?P<name>[A-Za-z].+)$")


def _clean_name(name: str) -> str:
    name = re.sub(r"[_=~]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .:-*#")
    return name


def parse_item_line(line: str) -> tuple[LineItem | None, str | None]:
    """Kembalikan (item, None) bila baris item utuh, (item_tanpa_nama, 'perlu_nama') untuk baris lanjutan
    seperti '2 x 25.000   50.000', atau (None, None) bila bukan item."""
    sub = last_amount(line)
    if sub is None or sub <= 0:
        return None, None
    m_tail = _AMOUNT_TAIL.search(line)
    rest = line[: m_tail.start()].strip()

    if mq := _QTY_UNIT.match(rest):
        qty, unit = int(mq["qty"]), parse_amount(mq["unit"])
        name = _clean_name(mq["name"])
        item = LineItem(name, qty, unit, sub)
        return (item, None) if sum(c.isalpha() for c in name) >= 2 else (item, "perlu_nama")

    qty = 1
    if mf := _QTY_FIRST.match(rest):
        qty, rest = int(mf["qty"]), mf["name"]
    name = _clean_name(rest)
    if sum(c.isalpha() for c in name) < 2:
        return None, None
    unit = sub // qty if qty and sub % qty == 0 else None
    return LineItem(name, qty, unit, sub), None


def _normalize_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        ln = re.sub(r"\.{3,}|_{2,}|-{3,}|={3,}|\*{3,}", " ", raw.replace("\t", " "))
        ln = re.sub(r"[ ]{2,}", "  ", ln).strip()
        if sum(c.isalnum() for c in ln) >= 2:
            out.append(ln)
    return out


def guess_store(lines: list[str]) -> str | None:
    for ln in lines[:6]:
        if sum(c.isalpha() for c in ln) < 3:
            continue
        if _NOT_ITEM.search(ln) or parse_date(ln) or _PHONE.search(ln) or classify(ln):
            continue
        return re.sub(r"\s+", " ", ln).strip(" .:-*#")
    return None


def parse_receipt(text: str, engine: str = "") -> Receipt:
    lines = _normalize_lines(text)
    r = Receipt(raw_text=text, engine=engine)
    notes: list[str] = []
    pending_name: str | None = None
    items_zone = True  # item hanya muncul sebelum baris subtotal/total

    r.toko = guess_store(lines)
    for ln in lines:
        if r.tanggal is None:
            r.tanggal = parse_date(ln)
            if r.tanggal and r.waktu is None:
                r.waktu = parse_time(ln)

    for ln in lines:
        kind = classify(ln)
        if kind == "skip":
            continue
        if kind in ("subtotal", "total", "pajak", "diskon"):
            items_zone = False
        if kind:
            amt = last_amount(ln)
            if amt is None:
                continue
            if kind == "total":
                r.total = amt
            elif kind == "subtotal":
                r.subtotal = amt
            elif kind == "pajak":
                r.pajak = (r.pajak or 0) + amt
            elif kind == "diskon":
                r.diskon = (r.diskon or 0) + abs(amt)
            elif kind == "bayar":
                r.bayar = amt
            elif kind == "kembalian":
                r.kembalian = amt
            pending_name = None
            continue

        if not items_zone or _NOT_ITEM.search(ln) or _PHONE.search(ln) or parse_date(ln):
            continue
        item, state = parse_item_line(ln)
        if item and state is None:
            r.items.append(item)
            pending_name = None
        elif item and state == "perlu_nama":
            if pending_name:
                item.nama = pending_name
                r.items.append(item)
            pending_name = None
        elif item is None and sum(c.isalpha() for c in ln) >= 3 and last_amount(ln) is None:
            pending_name = _clean_name(ln)

    for it in r.items:  # qty x harga harus sama dengan subtotal; bila tidak, percayai subtotal
        if it.harga_satuan and it.qty and round(it.harga_satuan * it.qty) != it.subtotal:
            notes.append(f"'{it.nama}': qty × harga tidak sama dengan subtotal baris.")
            it.harga_satuan = it.subtotal // int(it.qty) if it.subtotal % int(it.qty) == 0 else None

    if r.total is None and r.items:
        base = r.subtotal if r.subtotal is not None else r.items_sum
        r.total = base + (r.pajak or 0) - (r.diskon or 0)
        notes.append("Total tidak tertulis jelas di nota; dihitung dari item.")
    r.warnings = notes + r.check()
    return r
