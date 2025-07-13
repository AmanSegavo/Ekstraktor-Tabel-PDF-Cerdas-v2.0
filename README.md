# Ekstraktor Tabel PDF Cerdas v2.0

![Screenshot Aplikasi](https://github.com/AmanSegavo/Ekstraktor-Tabel-PDF-Cerdas-v2.0/blob/main/Screenshot%202025-07-13%20115820.png)

Ekstraktor Tabel PDF Cerdas adalah sebuah aplikasi desktop yang dirancang untuk mengekstrak data tabel dari file PDF secara otomatis. Aplikasi ini menggunakan model *machine learning* canggih (Microsoft Table Transformer) untuk mendeteksi dan mengekstrak struktur tabel, kemudian melakukan OCR (Optical Character Recognition) pada setiap sel untuk mengubahnya menjadi teks yang dapat diedit. Antarmuka pengguna yang interaktif memungkinkan pemantauan proses secara *real-time* dan menampilkan data yang diekstrak langsung dalam sebuah tabel.

Proyek ini dibangun untuk mengatasi tantangan dalam mengambil data terstruktur dari dokumen yang tidak terstruktur seperti PDF, di mana proses manual akan memakan banyak waktu dan rentan terhadap kesalahan.

## Fitur Utama

- **Deteksi Tabel Canggih**: Menggunakan model `microsoft/table-transformer-detection` untuk secara akurat menemukan lokasi tabel di dalam halaman PDF.
- **Pengenalan Struktur Tabel**: Memanfaatkan model `microsoft/table-transformer-structure-recognition` untuk mengidentifikasi baris dan kolom di dalam tabel yang terdeteksi.
- **OCR di Setiap Sel**: Menerapkan Tesseract OCR pada setiap sel individual untuk ekstraksi teks yang presisi, dengan dukungan untuk bahasa Inggris dan Indonesia (`eng+ind`).
- **Antarmuka Grafis (GUI)**: Dibangun dengan PySide6, menampilkan log proses dengan gaya "terminal hacker", panel kontrol yang mudah digunakan, dan tampilan data tabel *real-time*.
- **Pemrosesan Latar Belakang**: Menggunakan `multiprocessing` untuk menjalankan proses ekstraksi yang berat di latar belakang, menjaga agar antarmuka tetap responsif dan tidak membeku.
- **Fitur Lanjutan & Resume**: Proses ekstraksi dapat dihentikan dan dilanjutkan dari halaman terakhir yang diproses, sangat menghemat waktu untuk dokumen besar.
- **Manajemen Memori Otomatis**: Secara aktif memantau penggunaan RAM sistem dan secara otomatis me-restart proses *worker* jika penggunaan memori melebihi ambang batas (85%) untuk mencegah *crash* pada sistem dengan sumber daya terbatas.
- **Dukungan GPU**: Secara otomatis memanfaatkan GPU (CUDA) jika tersedia, untuk percepatan proses inferensi model secara signifikan.
- **Konversi PDF ke Gambar dengan Cache**: Mengonversi halaman PDF menjadi gambar sebagai langkah awal, dengan menyimpan gambar tersebut di cache (`temp_pdf_images`) untuk mempercepat pemrosesan ulang pada dokumen yang sama.

## Prasyarat

Sebelum Anda dapat menjalankan aplikasi ini, pastikan sistem Anda memenuhi persyaratan berikut:

1.  **Python 3.8+**: [Instal Python](https://www.python.org/downloads/) dan pastikan `pip` disertakan.
2.  **Tesseract OCR Engine**:
    *   **Windows**: Unduh dan instal dari [Tesseract at UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). Pastikan untuk menambahkan direktori instalasi Tesseract ke `PATH` environment variable.
    *   **Linux (Ubuntu/Debian)**: `sudo apt-get install tesseract-ocr tesseract-ocr-ind`
    *   **macOS**: `brew install tesseract tesseract-lang`
3.  **Poppler**: Pustaka rendering PDF yang diperlukan oleh `pdf2image`.
    *   **Windows**: Unduh biner Poppler terbaru dari [Blog Simagis](https://blog.alivate.com.au/poppler-windows/) atau [rilis GitHub ini](https://github.com/oschwartz10612/poppler-windows/releases/). Ekstrak file zip dan tambahkan direktori `bin` ke `PATH` environment variable sistem Anda.
    *   **Linux (Ubuntu/Debian)**: `sudo apt-get install poppler-utils`
    *   **macOS**: `brew install poppler`

## Instalasi

1.  **Clone repositori ini:**
    ```bash
    git clone https://github.com/AmanSegavo/Ekstraktor-Tabel-PDF-Cerdas-v2.0.git
    cd Ekstraktor-Tabel-PDF-Cerdas-v2.0
    ```

2.  **Buat dan aktifkan virtual environment (sangat direkomendasikan):**
    ```bash
    python -m venv venv
    source venv/bin/activate   # Di Windows gunakan: venv\Scripts\activate
    ```

3.  **Instal semua pustaka Python yang dibutuhkan dari `requirements.txt`:**
    ```bash
    pip install -r requirements.txt
    ```
    *Catatan: `requirements.txt` berisi daftar semua dependensi seperti `torch`, `transformers`, `pyside6`, `pytesseract`, dll. Jika Anda memiliki GPU NVIDIA, pastikan versi PyTorch yang terinstal kompatibel dengan CUDA Anda untuk performa terbaik.*

## Cara Menggunakan

1.  **Jalankan aplikasi dari direktori proyek:**
    ```bash
    python main.py
    ```
    *(Pastikan file utama Anda diberi nama `main.py` atau sesuaikan perintah di atas)*

2.  **Pilih File PDF**: Klik tombol **"Pilih File PDF"** untuk memuat dokumen yang ingin Anda proses. Nama file output CSV akan secara otomatis diusulkan berdasarkan nama file PDF, tetapi Anda bisa mengubahnya.

3.  **Mulai Ekstraksi**: Klik tombol **"Mulai Ekstraksi"**. Aplikasi akan memulai proses di latar belakang:
    *   Mengonversi PDF menjadi gambar (jika belum ada di cache).
    *   Memuat model AI (ini mungkin memerlukan waktu pada saat pertama kali dijalankan karena model perlu diunduh).
    *   Mendeteksi dan mengekstrak tabel halaman per halaman.

4.  **Pantau Proses**:
    *   **Terminal Log**: Jendela utama akan menampilkan log detail dari setiap langkah, memberikan Anda gambaran lengkap tentang apa yang sedang terjadi.
    *   **Progress Bar**: Memberikan indikasi visual dari kemajuan keseluruhan.
    *   **Overview Tabel (Real-time)**: Data yang berhasil diekstrak akan langsung muncul di panel tabel di bagian bawah, memungkinkan Anda melihat hasilnya secara langsung.

5.  **Hentikan & Lanjutkan**: Anda dapat mengklik **"Hentikan Ekstraksi"** kapan saja. Jika Anda memulai kembali proses pada file yang sama, aplikasi akan secara otomatis melanjutkan dari halaman terakhir yang belum selesai.

6.  **Lihat Hasil**: Setelah proses selesai (atau dihentikan), file CSV (`.csv`) yang telah Anda tentukan akan berisi semua data tabel yang berhasil diekstrak, lengkap dengan kolom `page_number` dan `table_on_page` untuk referensi yang mudah.

## Lisensi

Proyek ini dilisensikan di bawah Lisensi MIT. Lihat file `LICENSE` untuk detail lebih lanjut.
