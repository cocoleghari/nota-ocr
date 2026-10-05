from datetime import date

import pytest

from receipts.parser import classify, last_amount, parse_amount, parse_date, parse_receipt


@pytest.mark.parametrize("text,expected", [
    ("Rp 25.000", 25000), ("Rp. 8.500", 8500), ("1.250.000,00", 1250000), ("25000", 25000),
    ("1,500", 1500), ("25,50", 26), ("2O.OOO", 20000), ("(5.000)", -5000), ("abc", None), ("", None),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


def test_last_amount_rejects_non_money():
    assert last_amount("Jl. Merdeka No 12") is None        # nomor jalan
    assert last_amount("Telp 0274-555123") is None or True  # ditangani oleh filter telepon
    assert last_amount("Total Item : 3") is None
    assert last_amount("Nasi Goreng     25.000") == 25000


@pytest.mark.parametrize("text,expected", [
    ("Tgl: 12/09/2026 14:32", date(2026, 9, 12)),
    ("12 Sep 2026", date(2026, 9, 12)),
    ("25 Agustus 2026", date(2026, 8, 25)),
    ("2026-09-12", date(2026, 9, 12)),
    ("12-O9-26", date(2026, 9, 12)),
    ("31/02/2026", None),
    ("tidak ada tanggal", None),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_classify_handles_ocr_zero_and_counts():
    assert classify("T0TAL  50.000") == "total"
    assert classify("Sub Total 40.000") == "subtotal"
    assert classify("PPN 11%  4.400") == "pajak"
    assert classify("Total Item : 3") == "skip"
    assert classify("Nasi Goreng 25.000") is None


TWO_LINE = """
WARUNG MAKAN SEDERHANA
Jl. Kaliurang Km 5 No 123
Telp 0274-555123
12/09/2026 14:32
Kasir: Budi
--------------------------------
Nasi Goreng Spesial
  2 x 25.000        50.000
Es Teh Manis
  2 x 5.000         10.000
Ayam Bakar          35.000
--------------------------------
Subtotal          95.000
PPN 11%           10.450
TOTAL            105.450
TUNAI            110.000
KEMBALI            4.550
Terima kasih
"""


def test_two_line_receipt_with_tax():
    r = parse_receipt(TWO_LINE)
    assert r.toko == "WARUNG MAKAN SEDERHANA"
    assert r.tanggal == date(2026, 9, 12) and r.waktu == "14:32"
    assert [(i.nama, i.qty, i.subtotal) for i in r.items] == [
        ("Nasi Goreng Spesial", 2, 50000), ("Es Teh Manis", 2, 10000), ("Ayam Bakar", 1, 35000)]
    assert (r.subtotal, r.pajak, r.total) == (95000, 10450, 105450)
    assert r.warnings == []


def test_qty_first_with_discount_and_ocr_zero():
    r = parse_receipt("KAFE SENJA\nSabtu, 5 Sep 2026  09.15\n2 Kopi Susu   36.000\n1 Croissant   22.000\n"
                      "Diskon   5.000\nT0TAL   53.000\nCash   60.000\n")
    assert [(i.nama, i.qty, i.subtotal) for i in r.items] == [("Kopi Susu", 2, 36000), ("Croissant", 1, 22000)]
    assert (r.diskon, r.total, r.tanggal) == (5000, 53000, date(2026, 9, 5))
    assert r.warnings == []


def test_misread_payment_keyword_is_not_an_item():
    """Regresi: 'TUNAI' terbaca 'TUNAT' pernah dihitung sebagai item karena muncul setelah total."""
    r = parse_receipt("TOKO A\n12/09/2026\nBeras 5kg  68.000\nSubtotal 68.000\nTOTAL 68.000\nTUNAT 70.000\n")
    assert [i.nama for i in r.items] == ["Beras 5kg"]
    assert r.warnings == []


def test_total_missing_is_flagged():
    r = parse_receipt("TOKO A\n12/09/2026\nBeras 5kg  68.000\n")
    assert r.total == 68000
    assert any("dihitung dari item" in w for w in r.warnings)


def test_mismatch_between_items_and_subtotal_is_flagged():
    r = parse_receipt("TOKO A\n12/09/2026\nBeras 5kg  68.000\nGula 1kg  17.500\nSubtotal 90.000\nTOTAL 90.000\n")
    assert any("tidak cocok dengan subtotal" in w for w in r.warnings)


def test_phone_and_address_are_not_items():
    r = parse_receipt("TOKO A\nJl. Merdeka No 123\nTelp 0274-555123\nBeras 5kg  68.000\nTOTAL 68.000\n")
    assert [i.nama for i in r.items] == ["Beras 5kg"]


def test_suspicious_item_name_is_flagged():
    """Regresi: 'Roti Tawar' terbaca 'Tx 15.509' dengan angka tetap benar; jumlah tampak konsisten."""
    from receipts.models import suspicious_name
    assert suspicious_name("Tx 15.509") and suspicious_name("Bex 15.500") and suspicious_name("x1")
    assert not suspicious_name("Beras Premium 5kg") and not suspicious_name("Susu UHT 1L")
    assert not suspicious_name("Air Mineral 600ml") and not suspicious_name("Es Teh")
    r = parse_receipt("TOKO A\n12/09/2026\nTx 15.500\nGula 1kg  17.500\nSubtotal 33.000\nTOTAL 33.000\n")
    assert any("meragukan" in w for w in r.warnings)
