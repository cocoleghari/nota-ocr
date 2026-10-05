"""Model data nota dan pemeriksaan konsistensi."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date


ROUNDING_TOLERANCE = 100


def fmt_rp(value: int | float) -> str:
    return "Rp" + f"{value:,.0f}".replace(",", ".")


def suspicious_name(nama: str) -> bool:
    """Nama item yang kemungkinan besar salah baca: memuat angka berformat harga (15.500) atau nyaris tanpa huruf.
    Pemeriksaan jumlah tidak bisa menangkap ini karena angkanya sering tetap benar."""
    if re.search(r"\d[.,]\d{3}\b", nama):
        return True
    return sum(c.isalpha() for c in nama) < 3


@dataclass
class LineItem:
    nama: str
    qty: float = 1
    harga_satuan: int | None = None
    subtotal: int = 0


@dataclass
class Receipt:
    toko: str | None = None
    tanggal: date | None = None
    waktu: str | None = None
    items: list[LineItem] = field(default_factory=list)
    subtotal: int | None = None
    pajak: int | None = None      # PPN, pajak restoran, dan biaya layanan digabung
    diskon: int | None = None
    total: int | None = None
    bayar: int | None = None
    kembalian: int | None = None
    engine: str = ""
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def items_sum(self) -> int:
        return sum(i.subtotal for i in self.items)

    def check(self) -> list[str]:
        """Periksa kelengkapan dan konsistensi angka. Dipakai untuk menandai nota yang perlu dicek."""
        out: list[str] = []
        if not self.toko:
            out.append("Nama toko tidak terbaca.")
        if self.tanggal is None:
            out.append("Tanggal tidak terbaca.")
        if self.total is None:
            out.append("Total tidak terbaca.")
        if not self.items:
            out.append("Tidak ada item yang terbaca.")
        ragu = [i.nama for i in self.items if suspicious_name(i.nama)]
        if ragu:
            out.append("Nama item meragukan: " + ", ".join(f"'{n}'" for n in ragu[:2]) + ".")
        if self.items:
            s, pajak, diskon = self.items_sum, self.pajak or 0, self.diskon or 0
            if self.subtotal is not None and abs(s - self.subtotal) > 0:
                out.append(f"Jumlah item ({fmt_rp(s)}) tidak cocok dengan subtotal ({fmt_rp(self.subtotal)}).")
            base = self.subtotal if self.subtotal is not None else s
            # toleransi 100 rupiah untuk pembulatan; total tanpa pajak dipakai bila harga sudah termasuk pajak
            wajar = (base + pajak - diskon, base - diskon)
            if self.total is not None and all(abs(self.total - w) > ROUNDING_TOLERANCE for w in wajar):
                out.append(f"Subtotal/item ({fmt_rp(base)}) tidak sesuai dengan total ({fmt_rp(self.total)}).")
        return out

    @property
    def needs_review(self) -> bool:
        return bool(self.warnings)


def receipt_from_dict(d: dict, engine: str = "") -> Receipt:
    """Bangun Receipt dari dict hasil ekstraksi (misalnya JSON dari model vision), dengan validasi tipe."""
    def as_int(v):
        if v is None or v == "":
            return None
        try:
            return int(round(float(str(v).replace(".", "").replace(",", ".")))) if isinstance(v, str) else int(round(v))
        except (TypeError, ValueError):
            return None

    tanggal = None
    if d.get("tanggal"):
        try:
            tanggal = date.fromisoformat(str(d["tanggal"])[:10])
        except ValueError:
            tanggal = None

    items = []
    for it in d.get("items") or []:
        if not isinstance(it, dict) or not it.get("nama"):
            continue
        sub = as_int(it.get("subtotal"))
        unit = as_int(it.get("harga_satuan"))
        try:
            qty = float(it.get("qty") or 1)
        except (TypeError, ValueError):
            qty = 1
        if sub is None and unit is not None:
            sub = int(round(unit * qty))
        items.append(LineItem(str(it["nama"]).strip(), qty, unit, sub or 0))

    r = Receipt(
        toko=(str(d["toko"]).strip() or None) if d.get("toko") else None,
        tanggal=tanggal,
        waktu=str(d["waktu"]) if d.get("waktu") else None,
        items=items,
        subtotal=as_int(d.get("subtotal")),
        pajak=as_int(d.get("pajak")),
        diskon=as_int(d.get("diskon")),
        total=as_int(d.get("total")),
        bayar=as_int(d.get("bayar")),
        kembalian=as_int(d.get("kembalian")),
        engine=engine,
    )
    r.warnings = r.check()
    return r
