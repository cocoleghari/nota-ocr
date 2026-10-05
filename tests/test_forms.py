import numpy as np
import pandas as pd

from receipts.forms import items_from_frame, items_to_frame
from receipts.models import LineItem


def test_roundtrip():
    items = [LineItem("Beras", 2, 30000, 60000), LineItem("Gula", 1, None, 17500)]
    back = items_from_frame(items_to_frame(items))
    assert [(i.nama, i.qty, i.subtotal) for i in back] == [("Beras", 2, 60000), ("Gula", 1, 17500)]


def test_edited_table_cleanup():
    df = pd.DataFrame({"nama": ["Beras", "", None, "Telur"], "qty": [2, 1, 1, np.nan],
                       "harga_satuan": [30000, 5, 5, 29000], "subtotal": [np.nan, 5, 5, np.nan]})
    items = items_from_frame(df)
    assert [i.nama for i in items] == ["Beras", "Telur"]          # baris tanpa nama dibuang
    assert items[0].subtotal == 60000                              # dihitung dari qty x harga
    assert items[1].qty == 1 and items[1].subtotal == 29000        # qty kosong dianggap 1
