"""Rekap nota dari foto (Streamlit). Jalankan: streamlit run app.py"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from receipts import ui
from receipts.export import export_excel
from receipts.extractors import OCRUnavailable, get_extractor
from receipts.forms import items_from_frame, items_to_frame
from receipts.models import Receipt, fmt_rp
from receipts.storage import (
    DuplicateReceipt, connect, delete_receipt, file_hash, items_df, receipts_df, save_receipt,
)

st.set_page_config(page_title="Rekap nota", page_icon="🧾", layout="wide")
st.markdown(f"<style>{ui.CSS}</style>", unsafe_allow_html=True)

ENGINE_LABELS = {"tesseract": "Tesseract (lokal, gratis)", "claude": "Claude vision (API, berbayar)"}
PLOT_CONFIG = {"displayModeBar": False}


@st.cache_resource
def get_conn():
    path = os.getenv("NOTA_DB", "data/nota.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return connect(path)


@st.cache_resource(show_spinner=False)
def load_extractor(name: str):
    """Kembalikan (mesin, pesan_galat). Galat ditampilkan ke pengguna, bukan dilempar."""
    try:
        return get_extractor(name), None
    except OCRUnavailable as exc:
        return None, str(exc)


def show(fig: go.Figure, height: int, show_legend: bool = False) -> None:
    st.plotly_chart(ui.apply_flat(fig, height, show_legend), config=PLOT_CONFIG)


conn = get_conn()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.subheader("Mesin pembaca nota")
    engine_name = st.radio("Pilih mesin", list(ENGINE_LABELS), format_func=ENGINE_LABELS.get,
                           label_visibility="collapsed")
    extractor, engine_error = load_extractor(engine_name)
    if engine_error:
        st.warning(engine_error)
    elif engine_name == "claude":
        st.caption("Foto nota dikirim ke server Anthropic untuk dibaca.")
    else:
        st.caption("Foto diproses di komputer ini dan tidak dikirim ke mana pun.")
    st.caption(f"Data tersimpan di {os.getenv('NOTA_DB', 'data/nota.db')}.")

st.markdown(ui.hero("Rekap nota", "Foto nota jadi data yang rapi, bisa dikoreksi, dan siap diekspor ke Excel."),
            unsafe_allow_html=True)
tab_upload, tab_recap, tab_export = st.tabs(["Unggah nota", "Rekap", "Ekspor"])


# ------------------------------------------------------------------ kartu koreksi satu nota
def review_card(filename: str, data: bytes, h: str, result: Receipt) -> None:
    with st.container(border=True):
        img_col, form_col = st.columns([1, 2])
        img_col.image(data, caption=filename)
        with form_col:
            if result.warnings:
                st.markdown(ui.pill("warn", "Perlu dicek") + " " + " ".join(result.warnings[:2]),
                            unsafe_allow_html=True)
            else:
                st.markdown(ui.pill("up", "Terbaca lengkap") + " Tetap periksa sekilas sebelum menyimpan.",
                            unsafe_allow_html=True)
            c1, c2 = st.columns([2, 1])
            toko = c1.text_input("Toko", value=result.toko or "", key=f"toko:{h}")
            tanggal = c2.date_input("Tanggal", value=result.tanggal, key=f"tgl:{h}")
            edited = st.data_editor(
                items_to_frame(result.items), num_rows="dynamic", hide_index=True, key=f"items:{h}",
                column_config={
                    "nama": "Item",
                    "qty": st.column_config.NumberColumn("Qty", min_value=0),
                    "harga_satuan": st.column_config.NumberColumn("Harga satuan", format="%d"),
                    "subtotal": st.column_config.NumberColumn("Subtotal", format="%d"),
                },
            )
            items = items_from_frame(edited)
            base = sum(i.subtotal for i in items)
            t1, t2, t3 = st.columns(3)
            pajak = t1.number_input("Pajak & layanan", min_value=0, value=int(result.pajak or 0), step=500, key=f"pajak:{h}")
            diskon = t2.number_input("Diskon", min_value=0, value=int(result.diskon or 0), step=500, key=f"diskon:{h}")
            total = t3.number_input("Total", min_value=0, value=int(result.total or base), step=500, key=f"total:{h}")

            final = Receipt(toko=toko.strip() or None, tanggal=tanggal, waktu=result.waktu, items=items,
                            pajak=pajak or None, diskon=diskon or None, total=total or None,
                            engine=result.engine)
            problems = final.check()
            for msg in problems:
                st.caption(f"⚠ {msg}")
            if st.button("Simpan nota", key=f"save:{h}", type="primary"):
                final.subtotal = base  # turunan dari item yang sudah dikoreksi
                try:
                    rid = save_receipt(conn, final, file_hash=h, filename=filename)
                    st.success(f"Tersimpan sebagai nota #{rid}.")
                    st.rerun()
                except DuplicateReceipt:
                    st.info("Foto ini sudah pernah disimpan.")


# ------------------------------------------------------------------ tab unggah
with tab_upload:
    files = st.file_uploader("Unggah foto nota (boleh banyak sekaligus)", type=["png", "jpg", "jpeg", "webp"],
                             accept_multiple_files=True)
    st.caption("Foto yang lurus, terang, dan memenuhi bingkai memberi hasil terbaik. "
               "Semua hasil bisa dikoreksi sebelum disimpan.")
    if not files:
        st.info("Belum ada foto. Contoh nota tersedia di folder data/samples.")
    elif extractor is None:
        st.error("Mesin yang dipilih belum siap. Lihat pesan di sidebar.")
    else:
        for f in files:
            data = f.getvalue()
            h = file_hash(data)
            row = conn.execute("SELECT id FROM receipts WHERE file_hash = ?", (h,)).fetchone()
            if row:
                st.caption(f"{f.name}: sudah tersimpan sebagai nota #{row['id']}.")
                continue
            key = f"ekstraksi:{engine_name}:{h}"
            if key not in st.session_state:
                with st.spinner(f"Membaca {f.name}..."):
                    try:
                        st.session_state[key] = extractor.extract(data)
                    except Exception as exc:  # noqa: BLE001 - satu foto gagal tidak menghentikan yang lain
                        st.session_state[key] = exc
            result = st.session_state[key]
            if isinstance(result, Exception):
                st.error(f"{f.name}: gagal dibaca ({result}).")
                continue
            review_card(f.name, data, h, result)

# ------------------------------------------------------------------ tab rekap
with tab_recap:
    rec = receipts_df(conn)
    if rec.empty:
        st.info("Belum ada nota tersimpan. Unggah dan simpan nota di tab pertama.")
    else:
        top_store = rec.groupby("toko")["total"].sum().idxmax() if rec["toko"].notna().any() else "-"
        st.markdown(
            ui.kpi_strip([
                ui.kpi_card("Jumlah nota", ui.fmt_int(len(rec))),
                ui.kpi_card("Total belanja", fmt_rp(rec["total"].sum())),
                ui.kpi_card("Rata-rata per nota", fmt_rp(rec["total"].mean())),
                ui.kpi_card("Toko terbesar", str(top_store)),
            ]),
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        left, right = st.columns(2)
        with left, st.container(border=True):
            st.markdown(ui.panel_title("Belanja per bulan"), unsafe_allow_html=True)
            monthly = (rec.dropna(subset=["tanggal"]).assign(bulan=lambda d: d["tanggal"].dt.strftime("%Y-%m"))
                       .groupby("bulan")["total"].sum().reset_index())
            fig_m = go.Figure(go.Bar(x=monthly["bulan"], y=monthly["total"], marker_color=ui.ACCENT,
                                     hovertemplate="%{x}: Rp%{y:,.0f}<extra></extra>"))
            fig_m.update_yaxes(tickprefix="Rp", tickformat=",.0f")
            show(fig_m, 300)
        with right, st.container(border=True):
            st.markdown(ui.panel_title("Belanja per toko"), unsafe_allow_html=True)
            per_store = (rec.assign(toko=rec["toko"].fillna("(tanpa nama)")).groupby("toko")["total"].sum()
                         .sort_values().tail(8).reset_index())
            fig_s = go.Figure(go.Bar(x=per_store["total"], y=per_store["toko"], orientation="h",
                                     marker_color=ui.TEAL, hovertemplate="%{y}: Rp%{x:,.0f}<extra></extra>"))
            fig_s.update_layout(bargap=0.35)
            show(fig_s, 300)

        st.dataframe(
            rec.drop(columns=["filename"]), hide_index=True,
            column_config={
                "id": "No.", "tanggal": st.column_config.DateColumn("Tanggal", format="DD MMM YYYY"),
                "waktu": "Waktu", "toko": "Toko", "engine": "Mesin",
                **{k: st.column_config.NumberColumn(v, format="Rp %d")
                   for k, v in {"subtotal": "Subtotal", "pajak": "Pajak & layanan",
                                "diskon": "Diskon", "total": "Total"}.items()},
            },
        )
        with st.expander("Hapus nota"):
            options = {int(r.id): f"#{int(r.id)}  {r.toko or '(tanpa nama)'}  {fmt_rp(r.total or 0)}"
                       for r in rec.itertuples()}
            pick = st.selectbox("Pilih nota", list(options), format_func=options.get)
            if st.button("Hapus nota ini"):
                delete_receipt(conn, pick)
                st.rerun()

# ------------------------------------------------------------------ tab ekspor
with tab_export:
    rec, itm = receipts_df(conn), items_df(conn)
    if rec.empty:
        st.info("Belum ada data untuk diekspor.")
    else:
        st.markdown(ui.panel_title("Unduh rekap", "Excel berisi empat lembar: Rekap nota, Detail item, "
                                   "Per toko, dan Per bulan. Baris total memakai rumus SUM."),
                    unsafe_allow_html=True)
        buffer = io.BytesIO()
        export_excel(rec, itm, buffer)
        st.download_button("Unduh Excel (.xlsx)", buffer.getvalue(), file_name="rekap_nota.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.download_button("Unduh detail item (.csv)", itm.to_csv(index=False), file_name="detail_item.csv",
                           mime="text/csv")
