# 🧾 Rekap Nota

Aplikasi Python yang mengubah foto nota atau struk belanja menjadi data terstruktur: toko, tanggal, item, dan total. Hasil OCR bisa dikoreksi sebelum disimpan ke database SQLite, lalu direkap dan diekspor ke Excel. Proyek ini juga mengukur akurasinya sendiri terhadap kunci jawaban, dan menandai nota yang meragukan agar tidak ada angka salah yang lolos diam-diam.

## Fitur

- Dua mesin pembaca dengan antarmuka sama: **Tesseract** (lokal, gratis, data tidak keluar dari komputer) dan **Claude vision** (lewat API, berbayar).
- Parser khusus nota Indonesia: angka `25.000`, tanggal `12/09/2026` atau `12 Sep 2026`, PPN dan biaya layanan, diskon, dan salah baca OCR yang umum (`T0TAL`, `2O.OOO`).
- Pemeriksaan konsistensi: jumlah item harus cocok dengan subtotal, dan subtotal dengan total. Nota yang tidak lolos ditandai **Perlu dicek**.
- Koreksi manual di aplikasi sebelum menyimpan (toko, tanggal, tabel item, pajak, diskon, total).
- Penyimpanan SQLite dengan deteksi foto ganda lewat hash file.
- Ekspor Excel empat lembar (Rekap nota, Detail item, Per toko, Per bulan) dengan baris total berupa rumus SUM.
- Alat evaluasi: generator nota sintetis dengan kunci jawaban, dan skrip pengukur akurasi.

## Menjalankan

```bash
python -m venv .venv && source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run app.py
pytest
```

**Tesseract** adalah program terpisah dari Python. Di Windows, pasang dari [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) dan centang bahasa *Indonesian* saat memasang. Bila `tesseract.exe` tidak ada di PATH, isi `TESSERACT_CMD` di `.env` (lihat `.env.example`). Di Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-ind`. Bila model bahasa Indonesia belum ada, aplikasi otomatis memakai bahasa Inggris, yang cukup untuk huruf Latin dan angka.

Untuk mesin **Claude vision**, isi `ANTHROPIC_API_KEY`. Foto nota akan dikirim ke server Anthropic.

## Mengukur akurasi

```bash
python scripts/make_sample_receipts.py --n 40 --difficulty normal --seed 401 --out data/uji
python scripts/evaluate.py data/uji --engine tesseract --show-errors
```

Untuk foto asli Anda, siapkan folder berisi gambar dan `truth.json` berformat sama dengan `data/samples/truth.json` (toko, tanggal, total, dan daftar item), lalu jalankan `evaluate.py` pada folder itu. Ini langkah yang paling bernilai: angka di bawah berasal dari nota sintetis, bukan nota nyata.

## Hasil pengukuran

Seluruh angka memakai nota sintetis buatan `make_sample_receipts.py` (font monospace bersih, dengan variasi kemiringan, bayangan, dan derau), mesin Tesseract 5.3 dengan model bahasa Inggris. Empat set di bawah dibuat dengan seed yang belum pernah dipakai untuk menyetel apa pun, dan semuanya dijalankan dengan kode yang sama dengan repositori ini.

| Set | Jumlah | Nota benar seluruhnya | Total benar | Recall item | Nota ditandai | Nota salah yang ditandai |
|---|---|---|---|---|---|---|
| normal (seed 401) | 40 | 92,5% | 100% | 97,9% | 10,0% | 100% |
| normal (seed 404) | 40 | 82,5% | 100% | 95,5% | 22,5% | 100% |
| easy (seed 402)   | 30 | 76,7% | 96,7% | 95,5% | 30,0% | 100% |
| easy (seed 403)   | 30 | 83,3% | 100% | 95,8% | 20,0% | 100% |

Gabungan 140 nota: **84,3% benar seluruhnya** (118 dari 140). Pada keempat set, setiap nota yang salah sudah ditandai "Perlu dicek", dan semua nota yang tidak ditandai memang benar. Jumlah per set kecil (30 sampai 40), jadi selisih beberapa poin antarset masih dalam batas wajar; saya tidak tahu mengapa set easy sedikit lebih rendah daripada normal.

Set **hard** (kemiringan sampai 5 derajat, derau berat, kompresi JPEG tinggi, 12 nota) gagal total pada semua varian praproses: 0% nota benar. Seluruhnya ditandai "Perlu dicek", jadi tidak ada angka salah yang lolos, tetapi Tesseract tidak cocok untuk foto seburuk itu. Di sinilah mesin Claude vision seharusnya membantu; saya belum mengukurnya.

### Percobaan praproses

| Praproses | Hasil | Keputusan |
|---|---|---|
| Tanpa peredam derau (`gray`) | Nota normal 83,3% benar, hard recall item 4,5% | Dipakai untuk gambar bersih |
| Median filter (`median`) | Normal 96,7%, hard recall 22,7%, tetapi gambar bersih turun (7 dari 12 vs 9 dari 12) | Dipakai untuk gambar berderau |
| Binarisasi adaptif (`binary`) | Hard recall 0%, terburuk | Tidak dipakai |
| `auto` | Memilih `median` hanya bila derau terukur > 4 | **Default** |

Tingkat derau diukur dengan MAD dari selisih gambar dan versi yang dihaluskan; ketiga jenis set terpisah jelas (easy ≤ 3, normal ≥ 5,9, hard ≥ 8,9). Angka pada tabel ini berasal dari set yang juga saya pakai untuk memilih, jadi sebaiknya dibaca sebagai alasan keputusan, bukan hasil akhir.

## Keputusan teknis

- **Item hanya diambil sebelum baris subtotal/total.** Tesseract pernah membaca `TUNAI` sebagai `TUNAT`, dan parser menghitungnya sebagai item. Struktur nota (item, lalu ringkasan, lalu pembayaran) dipakai sebagai aturan.
- **Pemeriksaan konsistensi dua arah.** Jumlah item harus cocok dengan subtotal, dan subtotal plus pajak minus diskon dengan total (toleransi Rp100 untuk pembulatan). Sebelumnya total yang cocok dengan subtotal meloloskan nota walau item tidak cocok.
- **Nama item meragukan ikut ditandai.** Salah baca nama (misalnya `Roti Tawar` menjadi `Tx 15.509`) tidak mengubah jumlah, jadi pemeriksaan jumlah tidak bisa menangkapnya. Nama yang memuat angka berformat harga atau nyaris tanpa huruf ditandai.
- **Manusia tetap di dalam alur.** Tidak ada nota yang tersimpan tanpa tombol Simpan, dan nota yang meragukan ditandai jelas.
- **Mesin dapat ditukar.** Tesseract dan Claude vision sama-sama mengimplementasikan `extract(bytes) -> Receipt`, sehingga bisa dibandingkan pada folder uji yang sama.
- **Proses pengembangan terdokumentasi.** Angka awal 93,3% pada set pengembangan turun ke sekitar 80% pada set baru, sebelum perbaikan; itu sebabnya hasil akhir hanya dihitung dari set yang belum pernah dipakai untuk menyetel.

## Keterbatasan

- Belum diuji pada foto nota nyata. Nota termal yang pudar, kusut, atau difoto dari samping akan memberi hasil lebih rendah daripada angka di atas.
- Mesin Claude vision hanya diuji dengan respons API tiruan, belum pernah dipanggil sungguhan, dan belum punya angka akurasi.
- Satu nota per foto; nota panjang yang dipotong jadi beberapa foto belum didukung.
- Toko diambil dari baris pertama yang masuk akal; logo tanpa teks akan salah dibaca.

## Privasi

Database `data/nota.db` berisi data belanja pribadi dan sudah ada di `.gitignore`. Jangan men-deploy aplikasi ini ke tautan publik dengan nota asli: semua pengunjung berbagi satu database yang sama. Untuk demo publik, pakai hanya nota contoh dari `data/samples`. Di Streamlit Community Cloud, `packages.txt` sudah disiapkan untuk memasang Tesseract, tetapi belum pernah saya coba di sana.

## Struktur proyek

```
app.py                         antarmuka Streamlit
receipts/models.py             Receipt, LineItem, pemeriksaan konsistensi
receipts/parser.py             teks OCR -> Receipt
receipts/preprocess.py         orientasi, kontras, kemiringan, peredam derau
receipts/extractors/           tesseract.py dan claude_vision.py
receipts/storage.py            SQLite dan deteksi duplikat
receipts/export.py             ekspor Excel
receipts/evaluate.py           metrik akurasi
receipts/forms.py, ui.py       jembatan tabel-ke-objek dan gaya tampilan
scripts/make_sample_receipts.py  generator nota sintetis dan kunci jawaban
scripts/evaluate.py            pengukur akurasi
tests/                         42 tes pytest
data/samples/                  30 nota contoh beserta truth.json
```

## Pengembangan lanjut

- Ukur pada 30 sampai 50 foto nota asli, lalu bandingkan Tesseract dengan Claude vision pada folder yang sama.
- Gunakan skor keyakinan per kata dari Tesseract untuk menandai baris yang ragu.
- Dukungan nota lebih dari satu foto, dan koreksi perspektif untuk foto dari samping.
