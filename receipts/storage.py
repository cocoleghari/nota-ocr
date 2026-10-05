"""Penyimpanan SQLite: nota dan item, dengan deteksi unggahan ganda lewat hash file."""
from __future__ import annotations

import hashlib
import sqlite3

import pandas as pd

from .models import Receipt

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT UNIQUE,
    filename TEXT,
    toko TEXT,
    tanggal TEXT,
    waktu TEXT,
    subtotal INTEGER,
    pajak INTEGER,
    diskon INTEGER,
    total INTEGER,
    engine TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    nama TEXT,
    qty REAL,
    harga_satuan INTEGER,
    subtotal INTEGER
);
"""


class DuplicateReceipt(Exception):
    """Foto yang sama sudah pernah disimpan."""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_receipt(conn: sqlite3.Connection, r: Receipt, *, file_hash: str, filename: str = "") -> int:
    with conn:  # satu transaksi: nota dan itemnya masuk bersama atau tidak sama sekali
        try:
            cur = conn.execute(
                "INSERT INTO receipts (file_hash, filename, toko, tanggal, waktu, subtotal, pajak, diskon,"
                " total, engine) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (file_hash, filename, r.toko, r.tanggal.isoformat() if r.tanggal else None, r.waktu,
                 r.subtotal, r.pajak, r.diskon, r.total, r.engine),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateReceipt(filename or file_hash[:8]) from exc
        rid = cur.lastrowid
        conn.executemany(
            "INSERT INTO items (receipt_id, nama, qty, harga_satuan, subtotal) VALUES (?,?,?,?,?)",
            [(rid, i.nama, i.qty, i.harga_satuan, i.subtotal) for i in r.items],
        )
    return rid


def receipts_df(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT id, tanggal, waktu, toko, subtotal, pajak, diskon, total, engine, filename FROM receipts"
        " ORDER BY tanggal DESC, id DESC", conn)
    df["tanggal"] = pd.to_datetime(df["tanggal"])
    return df


def items_df(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT r.id AS nota_id, r.tanggal, r.toko, i.nama, i.qty, i.harga_satuan, i.subtotal"
        " FROM items i JOIN receipts r ON r.id = i.receipt_id ORDER BY r.tanggal DESC, r.id DESC, i.id", conn)
    df["tanggal"] = pd.to_datetime(df["tanggal"])
    return df


def delete_receipt(conn: sqlite3.Connection, receipt_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
