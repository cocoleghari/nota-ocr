"""Jembatan antara tabel yang diedit pengguna dan objek Receipt."""
from __future__ import annotations

import pandas as pd

from .models import LineItem

COLUMNS = ["nama", "qty", "harga_satuan", "subtotal"]


def items_to_frame(items: list[LineItem]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"nama": i.nama, "qty": i.qty, "harga_satuan": i.harga_satuan, "subtotal": i.subtotal} for i in items],
        columns=COLUMNS,
    )


def items_from_frame(df: pd.DataFrame) -> list[LineItem]:
    """Baca tabel hasil edit. Baris tanpa nama dibuang; subtotal kosong dihitung dari qty x harga."""
    items: list[LineItem] = []
    for _, row in df.iterrows():
        nama = "" if pd.isna(row.get("nama")) else str(row["nama"]).strip()
        if not nama:
            continue
        qty = float(row["qty"]) if pd.notna(row.get("qty")) and float(row["qty"]) > 0 else 1.0
        unit = int(round(row["harga_satuan"])) if pd.notna(row.get("harga_satuan")) else None
        if pd.notna(row.get("subtotal")):
            sub = int(round(row["subtotal"]))
        else:
            sub = int(round(unit * qty)) if unit is not None else 0
        items.append(LineItem(nama, qty, unit, sub))
    return items
