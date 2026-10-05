"""Praproses foto nota agar lebih mudah dibaca OCR: orientasi, kontras, ukuran, dan kemiringan."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter, ImageOps

MIN_WIDTH = 1400
NOISE_THRESHOLD = 4.0  # di atas ini gambar dianggap berderau dan perlu diredam


def load_image(data: bytes) -> Image.Image:
    """Buka gambar dan hormati orientasi EXIF (foto ponsel sering tersimpan miring)."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def estimate_skew(gray: Image.Image, max_angle: float = 8.0, step: float = 0.5) -> float:
    """Perkirakan sudut kemiringan teks (derajat) lewat variansi proyeksi baris.

    Teks yang lurus menghasilkan proyeksi horizontal dengan puncak dan lembah tajam (variansi besar).
    """
    small = gray.copy()
    small.thumbnail((700, 700))
    arr = np.asarray(small, dtype=np.float32)
    binary = (arr < arr.mean() * 0.85).astype(np.uint8) * 255
    base = Image.fromarray(binary)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step, step):
        rotated = base.rotate(float(angle), resample=Image.BILINEAR, fillcolor=0)
        score = float(np.asarray(rotated, dtype=np.float32).sum(axis=1).var())
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def estimate_noise(gray: Image.Image) -> float:
    """Perkiraan simpangan baku derau: MAD dari selisih gambar dengan versi yang dihaluskan.
    MAD tahan terhadap tepi huruf karena tepi hanya sebagian kecil piksel."""
    a = np.asarray(gray, dtype=np.float32)
    d = a - np.asarray(gray.filter(ImageFilter.GaussianBlur(1.0)), dtype=np.float32)
    return float(1.4826 * np.median(np.abs(d - np.median(d))))


def deskew(gray: Image.Image, angle: float | None = None) -> Image.Image:
    angle = estimate_skew(gray) if angle is None else angle
    if abs(angle) < 0.3:
        return gray
    return gray.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)


def adaptive_binarize(gray: Image.Image, radius: int = 20, ratio: float = 0.9) -> Image.Image:
    """Hitamkan piksel yang lebih gelap dari rata-rata sekitarnya. Tahan terhadap bayangan dan latar tak rata."""
    arr = np.asarray(gray, dtype=np.float32)
    local_mean = np.asarray(gray.filter(ImageFilter.BoxBlur(radius)), dtype=np.float32)
    return Image.fromarray(np.where(arr < local_mean * ratio, 0, 255).astype(np.uint8))


PREP_MODES = ("auto", "gray", "median", "binary")


def preprocess(data: bytes, mode: str = "auto") -> Image.Image:
    """Gambar mentah -> abu-abu, kontras otomatis, diperbesar bila kecil, ditegakkan, lalu:
    auto = median hanya bila gambar berderau (default); gray = dipertajam saja; median = selalu peredam derau;
    binary = peredam derau + binarisasi adaptif (pada pengujian lebih buruk, disimpan untuk eksperimen).
    Peredam derau membantu foto berderau tetapi mengikis huruf pada gambar yang sudah bersih."""
    if mode not in PREP_MODES:
        raise ValueError(f"mode praproses harus salah satu dari {PREP_MODES}")
    img = load_image(data)
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    if mode == "auto":
        mode = "median" if estimate_noise(gray) > NOISE_THRESHOLD else "gray"
    if gray.width < MIN_WIDTH:
        scale = MIN_WIDTH / gray.width
        gray = gray.resize((MIN_WIDTH, int(gray.height * scale)), Image.LANCZOS)
    gray = deskew(gray)
    if mode == "gray":
        return gray.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))
    gray = gray.filter(ImageFilter.MedianFilter(3))
    return gray if mode == "median" else adaptive_binarize(gray)
