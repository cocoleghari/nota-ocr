import io
import json

import pytest
from PIL import Image, ImageDraw

from receipts.evaluate import aggregate, score_receipt, similar
from receipts.extractors import OCRUnavailable, get_extractor
from receipts.extractors.claude_vision import ClaudeVisionExtractor, parse_model_json
from receipts.models import LineItem, Receipt
from receipts.preprocess import deskew, estimate_skew


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (200, 300), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_parse_model_json_handles_code_fences():
    assert parse_model_json('```json\n{"total": 5000}\n```') == {"total": 5000}
    assert parse_model_json('Berikut hasilnya: {"total": 1}') == {"total": 1}
    with pytest.raises(ValueError):
        parse_model_json("tidak ada json")


def test_claude_extractor_needs_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(OCRUnavailable):
        ClaudeVisionExtractor()


def test_claude_extractor_parses_response(monkeypatch):
    sent = {}

    class FakeResp:
        status_code = 200

        def json(self):
            body = {"toko": "Toko A", "tanggal": "2026-09-12", "total": 60000,
                    "items": [{"nama": "Beras", "qty": 2, "harga_satuan": 30000, "subtotal": 60000}]}
            return {"content": [{"type": "text", "text": "```json\n" + json.dumps(body) + "\n```"}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, payload=json, headers=headers)
        return FakeResp()

    monkeypatch.setattr("receipts.extractors.claude_vision.requests.post", fake_post)
    r = ClaudeVisionExtractor(api_key="kunci-palsu", model="model-uji").extract(_png_bytes())
    assert r.toko == "Toko A" and r.total == 60000 and r.warnings == []
    assert sent["headers"]["x-api-key"] == "kunci-palsu" and sent["payload"]["model"] == "model-uji"
    assert sent["payload"]["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"


def test_claude_extractor_reports_api_errors(monkeypatch):
    class Bad:
        status_code = 401
        text = "invalid x-api-key"

    monkeypatch.setattr("receipts.extractors.claude_vision.requests.post", lambda *a, **k: Bad())
    with pytest.raises(RuntimeError, match="401"):
        ClaudeVisionExtractor(api_key="x").extract(_png_bytes())


def test_unknown_engine_name():
    with pytest.raises(ValueError, match="tidak dikenal"):
        get_extractor("abc")


def _lined_page(n=18):
    img = Image.new("L", (600, 800), 255)
    d = ImageDraw.Draw(img)
    for i in range(n):
        y = 60 + i * 38
        d.rectangle([60, y, 60 + 380 + (i % 3) * 40, y + 14], fill=20)  # "baris teks"
    return img


def test_deskew_recovers_rotation():
    page = _lined_page()
    tilted = page.rotate(3.0, resample=Image.BICUBIC, fillcolor=255)
    angle = estimate_skew(tilted)
    assert abs(angle - (-3.0)) <= 1.0
    fixed = deskew(tilted)
    assert abs(estimate_skew(fixed)) <= 1.0


def test_similarity_and_scoring():
    assert similar("Susu UHT 1L", "SUSU UHT ILL") > 0.8
    truth = {"file": "a.jpg", "toko": "Toko A", "tanggal": "2026-09-12", "total": 60000,
             "items": [{"nama": "Beras", "qty": 2, "subtotal": 60000}]}
    from datetime import date
    good = Receipt(toko="TOKO A", tanggal=date(2026, 9, 12), total=60000, items=[LineItem("Beras", 2, 30000, 60000)])
    bad = Receipt(toko="Toko A", tanggal=date(2026, 9, 12), total=50000, items=[LineItem("Beras", 2, 30000, 60000)],
                  warnings=["x"])
    s_good, s_bad = score_receipt(good, truth), score_receipt(bad, truth)
    assert s_good["sempurna"] and not s_bad["sempurna"] and s_bad["ditandai"]
    agg = aggregate([s_good, s_bad])
    assert agg["sempurna_pct"] == 50 and agg["kesalahan_tertangkap_pct"] == 100
    assert agg["tanpa_tanda_benar_pct"] == 100


def test_noise_estimate_separates_clean_from_noisy():
    import numpy as np

    from receipts.preprocess import NOISE_THRESHOLD, estimate_noise
    page = _lined_page()
    arr = np.asarray(page, dtype=np.float32)
    noisy = Image.fromarray(np.clip(arr + np.random.default_rng(0).normal(0, 10, arr.shape), 0, 255).astype(np.uint8))
    assert estimate_noise(page) < NOISE_THRESHOLD < estimate_noise(noisy)


def test_preprocess_auto_skips_denoise_on_clean_image():
    import numpy as np

    from receipts.preprocess import preprocess
    buf = io.BytesIO()
    _lined_page().convert("RGB").save(buf, format="PNG")
    clean_auto = np.asarray(preprocess(buf.getvalue(), "auto"))
    clean_gray = np.asarray(preprocess(buf.getvalue(), "gray"))
    assert np.array_equal(clean_auto, clean_gray)  # gambar bersih: auto = gray
    import pytest as _pt
    with _pt.raises(ValueError):
        preprocess(buf.getvalue(), "tidak-ada")
