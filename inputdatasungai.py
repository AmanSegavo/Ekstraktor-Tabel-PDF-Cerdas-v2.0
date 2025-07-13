import sys
import os
import torch
import pytesseract
import pandas as pd
import psutil
import time
import multiprocessing
from pathlib import Path
from PIL import Image
from pdf2image import convert_from_path
from transformers import AutoImageProcessor, AutoModelForObjectDetection
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog,
    QTextEdit, QVBoxLayout, QWidget, QProgressBar, QLabel,
    QLineEdit, QDockWidget, QTableView
)
from PySide6.QtCore import (QTimer, QAbstractTableModel, Qt, QModelIndex)
from PySide6.QtGui import QAction

# ===================================================================
# FUNGSI WORKER DAN FUNGSI BANTUAN EKSTRAKSI
# ===================================================================
def get_cell_coordinates(row_boxes, column_boxes):
    cells = []
    for row_box in row_boxes:
        row_cells = []
        for col_box in column_boxes:
            cell_box = [col_box[0], row_box[1], col_box[2], row_box[3]]
            row_cells.append(cell_box)
        cells.append(row_cells)
    return cells

def apply_ocr_to_cell(image, cell_coords):
    cell_image = image.crop(cell_coords)
    try:
        # Optimasi OCR dengan bahasa Inggris dan Indonesia
        text = pytesseract.image_to_string(cell_image, config='--psm 7 -l eng+ind').strip()
    except Exception:
        text = ""
    return text

def extraction_worker(queue, pdf_path, image_dir, output_csv, start_page, stop_signal):
    try:
        queue.put(("LOG", "Memuat model (Proses Worker Baru)..."))
        # Gunakan GPU jika tersedia
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        detection_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-detection")
        detection_model = AutoModelForObjectDetection.from_pretrained("microsoft/table-transformer-detection").to(device)
        structure_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-structure-recognition")
        structure_model = AutoModelForObjectDetection.from_pretrained("microsoft/table-transformer-structure-recognition").to(device)
        queue.put(("LOG", f"Model berhasil dimuat di worker (Device: {device})."))
        
        image_files = sorted([f for f in os.listdir(image_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))])
        total_pages = len(image_files)

        for i in range(start_page - 1, total_pages):
            if stop_signal.is_set():
                queue.put(("LOG", "Sinyal berhenti diterima. Menutup worker."))
                break
            page_num = i + 1
            image_path = os.path.join(image_dir, image_files[i])
            queue.put(("LOG", f"\n--- Memproses Halaman {page_num}/{total_pages} ---"))
            try:
                image = Image.open(image_path).convert("RGB")
            except Exception as e:
                queue.put(("LOG", f"!!! Gagal membuka gambar {image_files[i]}: {e}"))
                continue

            inputs = detection_processor(images=image, return_tensors="pt").to(device)
            outputs = detection_model(**inputs)
            target_sizes = torch.tensor([image.size[::-1]])
            detection_results = detection_processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.85)[0]
            table_boxes = [box.tolist() for label, box in zip(detection_results["labels"], detection_results["boxes"]) if detection_model.config.id2label[label.item()] == 'table']

            if not table_boxes:
                queue.put(("LOG", f"Tidak ada tabel di halaman {page_num}."))
            else:
                queue.put(("LOG", f"Ditemukan {len(table_boxes)} tabel."))
                for table_idx, table_box in enumerate(table_boxes):
                    table_image = image.crop(table_box)
                    inputs = structure_processor(images=table_image, return_tensors="pt").to(device)
                    outputs = structure_model(**inputs)
                    target_sizes = torch.tensor([table_image.size[::-1]])
                    structure_results = structure_processor.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.7)[0]

                    row_boxes = [box.tolist() for label, box in zip(structure_results["labels"], structure_results["boxes"]) if structure_model.config.id2label[label.item()] == 'table row']
                    column_boxes = [box.tolist() for label, box in zip(structure_results["labels"], structure_results["boxes"]) if structure_model.config.id2label[label.item()] == 'table column']
                    
                    row_boxes.sort(key=lambda x: x[1])
                    column_boxes.sort(key=lambda x: x[0])

                    if not row_boxes or not column_boxes:
                        continue
                    cell_coordinates = get_cell_coordinates(row_boxes, column_boxes)
                    table_data = []
                    for row in cell_coordinates:
                        row_text = [apply_ocr_to_cell(table_image, cell) for cell in row]
                        table_data.append(row_text)
                        
                    if table_data:
                        df = pd.DataFrame(table_data)
                        df['page_number'] = page_num
                        df['table_on_page'] = table_idx + 1
                        id_cols = ['page_number', 'table_on_page']
                        data_cols = [col for col in df.columns if col not in id_cols]
                        df = df[id_cols + data_cols]
                        
                        header = not os.path.exists(output_csv)
                        df.to_csv(output_csv, mode='a', header=header, index=False)
                        queue.put(("LOG", f"  Tabel #{table_idx + 1} disimpan. [{len(table_data)} baris]"))

            queue.put(("PROGRESS", page_num))
        queue.put(("DONE", "Proses worker selesai."))
    except Exception as e:
        queue.put(("ERROR", f"Error di worker: {e}"))

# ===================================================================
# KELAS MODEL PANDAS UNTUK QTABLEVIEW
# ===================================================================
class PandasModel(QAbstractTableModel):
    def __init__(self, data=pd.DataFrame()):
        super().__init__()
        self._data = data

    def rowCount(self, parent=QModelIndex()):
        return self._data.shape[0]

    def columnCount(self, parent=QModelIndex()):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return str(self._data.columns[section])
        return None
    
    def loadData(self, csv_path):
        """Memuat ulang data dari file CSV dan memperbarui tampilan."""
        try:
            if os.path.exists(csv_path):
                self._data = pd.read_csv(csv_path, on_bad_lines='skip')
            else:
                self._data = pd.DataFrame()
            self.layoutChanged.emit()
            return True
        except Exception as e:
            print(f"Error loading CSV: {e}")
            self._data = pd.DataFrame()
            self.layoutChanged.emit()
            return False

# ===================================================================
# APLIKASI GUI UTAMA
# ===================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ekstraktor Tabel PDF Cerdas v2.0")
        self.setGeometry(100, 100, 1200, 800)

        # Inisialisasi variabel state
        self.pdf_path = ""
        self.image_dir = "temp_pdf_images"
        self.output_csv = "hasil_ekstraksi.csv"
        self.worker_process = None
        self.queue = multiprocessing.Queue()
        self.stop_signal = multiprocessing.Event()
        self.total_pages = 0
        self.MEMORY_THRESHOLD = 85.0
        self.is_refreshing = False

        self._setup_ui()
        self._setup_timers()
        self.log("Sistem Siap. Silakan pilih file PDF untuk memulai.")

    def _setup_ui(self):
        # --- Terminal Hacker sebagai Central Widget ---
        self.hacker_terminal = QTextEdit()
        self.hacker_terminal.setReadOnly(True)
        self.hacker_terminal.setStyleSheet("""
            QTextEdit {
                background-color: #0C0C0C;
                color: #00FF00;
                font-family: 'Lucida Console', 'Courier New', monospace;
                font-size: 14px;
                border: 2px solid #00AA00;
            }
        """)
        self.setCentralWidget(self.hacker_terminal)
        
        # --- Panel Kontrol (Dockable) ---
        control_dock = QDockWidget("Panel Kontrol", self)
        control_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        
        control_widget = QWidget()
        layout = QVBoxLayout(control_widget)
        
        self.btn_select_pdf = QPushButton("Pilih File PDF")
        self.btn_select_pdf.clicked.connect(self.select_pdf)
        layout.addWidget(self.btn_select_pdf)
        self.lbl_pdf_path = QLabel("File PDF belum dipilih.")
        layout.addWidget(self.lbl_pdf_path)
        
        layout.addWidget(QLabel("Output CSV:"))
        self.txt_output_csv = QLineEdit(self.output_csv)
        layout.addWidget(self.txt_output_csv)
        
        self.btn_start = QPushButton("Mulai Ekstraksi")
        self.btn_start.clicked.connect(self.start_extraction)
        self.btn_start.setEnabled(False)
        layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton("Hentikan Ekstraksi")
        self.btn_stop.clicked.connect(self.stop_extraction)
        self.btn_stop.setEnabled(False)
        layout.addWidget(self.btn_stop)
        
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.lbl_memory = QLabel("Penggunaan RAM: 0%")
        layout.addWidget(self.lbl_memory)
        layout.addStretch()
        
        control_dock.setWidget(control_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, control_dock)

        # --- Overview Tabel (Dockable & Real-time) ---
        table_dock = QDockWidget("Overview Tabel (Real-time)", self)
        table_dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        
        self.table_view = QTableView()
        self.pandas_model = PandasModel()
        self.table_view.setModel(self.pandas_model)
        
        table_dock.setWidget(self.table_view)
        self.addDockWidget(Qt.BottomDockWidgetArea, table_dock)
        
        # --- Menu untuk Menampilkan/Menyembunyikan Panel ---
        view_menu = self.menuBar().addMenu("Tampilan")
        view_menu.addAction(control_dock.toggleViewAction())
        view_menu.addAction(table_dock.toggleViewAction())
        
    def _setup_timers(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_queue)
        self.timer.start(100)
        self.memory_timer = QTimer()
        self.memory_timer.timeout.connect(self.check_memory_usage)
        self.memory_timer.start(2000)

    def log(self, message):
        """Fungsi log dengan efek kursor hacker dan logging ke file."""
        current_html = self.hacker_terminal.toHtml()
        if "cursor" in current_html:
            current_html = current_html.replace('<span id="cursor">█</span>', '')
            self.hacker_terminal.setHtml(current_html)
            
        self.hacker_terminal.append(message)
        self.hacker_terminal.insertHtml('<span id="cursor">█</span>')
        self.hacker_terminal.verticalScrollBar().setValue(self.hacker_terminal.verticalScrollBar().maximum())
        
        # Simpan ke file log
        with open("ekstraksi_log.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")

    def select_pdf(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Pilih PDF", "", "PDF Files (*.pdf)")
        if file_name:
            self.pdf_path = file_name
            self.lbl_pdf_path.setText(f"File: {os.path.basename(file_name)}")
            self.btn_start.setEnabled(True)
            self.output_csv = Path(file_name).stem + "_hasil.csv"
            self.txt_output_csv.setText(self.output_csv)
            self.pandas_model.loadData(self.output_csv)

    def prepare_environment(self):
        self.output_csv = self.txt_output_csv.text()
        if not self.output_csv.endswith(".csv"):
            self.log("!!! Nama file output harus berekstensi .csv!")
            return False, 0
        
        if not os.path.exists(self.image_dir):
            os.makedirs(self.image_dir)
        
        existing_images = sorted([f for f in os.listdir(self.image_dir) if f.lower().endswith(".png")])
        
        if not existing_images:
            self.log(f">>> Mengonversi PDF ke cache gambar di: '{self.image_dir}'...")
            QApplication.processEvents()
            try:
                poppler_path = None
                possible_poppler_paths = [
                    r"D:\Release-24.08.0-0\poppler-24.08.0\Library\bin",
                    r"C:\Program Files\poppler\bin",
                    "/usr/bin",
                    "/usr/local/bin",
                ]
                for path in possible_poppler_paths:
                    if os.path.exists(path):
                        poppler_path = path
                        break
                
                images = convert_from_path(
                    self.pdf_path,
                    output_folder=self.image_dir,
                    fmt='png',
                    output_file='page_',
                    thread_count=4,
                    poppler_path=poppler_path
                )
                self.log(f">>> Konversi Selesai: {len(images)} halaman.")
            except Exception as e:
                self.log(f"!!! ERROR konversi PDF: {e}")
                self.log(">>> Pastikan Poppler terinstal. Unduh dari: https://poppler.freedesktop.org/")
                self.log(">>> Atau, tentukan path Poppler di kode atau melalui variabel lingkungan.")
                return False, 0
            else:
                existing_images = sorted([f for f in os.listdir(self.image_dir) if f.lower().endswith((".png", ".jpg"))])
                self.log(f">>> Menggunakan {len(existing_images)} gambar dari cache.")
        
        self.total_pages = len(existing_images)
        self.progress_bar.setMaximum(self.total_pages)
        start_page = 1
        if os.path.exists(self.output_csv):
            try:
                df_existing = pd.read_csv(self.output_csv, on_bad_lines='skip')
                if not df_existing.empty and 'page_number' in df_existing.columns:
                    last_processed_page = df_existing['page_number'].max()
                    if last_processed_page >= self.total_pages:
                        self.log(">>> CSV sudah mencakup semua halaman. Proses dianggap selesai.")
                        return False, 0
                    start_page = int(last_processed_page) + 1
                    self.log(f">>> CSV ditemukan. Melanjutkan dari halaman {start_page}.")
            except Exception as e:
                self.log(f"!!! Warning saat baca CSV: {e}. Memulai dari awal.")
        
        return True, start_page

    def start_extraction(self):
        success, start_page = self.prepare_environment()
        if not success:
            self.log(">>> Persiapan gagal atau sudah selesai. Proses dihentikan.")
            return

        self.progress_bar.setValue(start_page - 1)
        self.btn_start.setEnabled(False)
        self.btn_select_pdf.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log(f"\n>>> [PROSES DIMULAI] - Halaman {start_page} dari {self.total_pages}...")
        self.start_worker(start_page)

    def stop_extraction(self):
        if self.worker_process and self.worker_process.is_alive():
            self.log(">>> Mengirim sinyal berhenti ke worker...")
            self.stop_signal.set()
            self.btn_stop.setEnabled(False)

    def start_worker(self, start_page):
        if self.worker_process and self.worker_process.is_alive():
            self.log("!!! Worker sebelumnya masih berjalan, harap tunggu.")
            return
        self.log(f">>> Memulai Worker Process dari Halaman {start_page}...")
        self.stop_signal.clear()
        self.worker_process = multiprocessing.Process(
            target=extraction_worker,
            args=(self.queue, self.pdf_path, self.image_dir, self.output_csv, start_page, self.stop_signal)
        )
        self.worker_process.start()
        self.is_refreshing = False

    def check_queue(self):
        """Memeriksa pesan dari worker dan memperbarui GUI, termasuk tabel."""
        while not self.queue.empty():
            try:
                msg_type, message = self.queue.get(block=False)
                if msg_type == "LOG":
                    self.log(message)
                elif msg_type == "PROGRESS":
                    self.progress_bar.setValue(message)
                    self.pandas_model.loadData(self.output_csv)
                    self.table_view.scrollToBottom()
                elif msg_type == "DONE":
                    self.log(f">>> Worker Selesai: {message}")
                    self.process_finished()
                elif msg_type == "ERROR":
                    self.log(f"!!! ERROR KRITIS: {message}")
                    self.process_finished()
                QApplication.processEvents()
            except Exception:
                pass
    
    def process_finished(self):
        if self.worker_process:
            self.worker_process.join(timeout=3)
            if self.worker_process.is_alive():
                self.worker_process.terminate()
            self.worker_process = None

        self.pandas_model.loadData(self.output_csv)

        if self.is_refreshing:
            self.log(">>> Refresh memori selesai. Melanjutkan dalam 5 detik...")
            QTimer.singleShot(5000, self.resume_after_refresh)
        else:
            self.log("\n--- [PROSES SELESAI] ---")
            self.reset_ui()
    
    def resume_after_refresh(self):
        success, start_page = self.prepare_environment()
        if success:
            self.start_worker(start_page)
        else:
            self.log("!!! Gagal melanjutkan setelah refresh memori.")
            self.reset_ui()

    def reset_ui(self):
        self.btn_start.setEnabled(True)
        self.btn_select_pdf.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.is_refreshing = False

    def check_memory_usage(self):
        memory_info = psutil.virtual_memory()
        usage_percent = memory_info.percent
        self.lbl_memory.setText(f"Penggunaan RAM: {usage_percent:.1f}%")
        if usage_percent > self.MEMORY_THRESHOLD and self.worker_process and self.worker_process.is_alive() and not self.is_refreshing:
            self.log(f"\n!!! [MEMORI TINGGI] RAM mencapai {usage_percent}%, memicu refresh...")
            self.is_refreshing = True
            self.stop_signal.set()

# ===================================================================
# ENTRY POINT APLIKASI
# ===================================================================
if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())