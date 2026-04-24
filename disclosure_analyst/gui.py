"""PySide6 GUI for the Disclosure Analyst application."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .analyzer import analyze
from .extractor import extract_zip
from .report import render_pdf

API_KEY_FILE = Path.home() / ".disclosure_analyst_key"


def load_saved_api_key() -> str:
    if API_KEY_FILE.exists():
        try:
            return API_KEY_FILE.read_text().strip()
        except Exception:
            return ""
    return ""


def save_api_key(key: str) -> None:
    try:
        API_KEY_FILE.write_text(key.strip())
        try:
            os.chmod(API_KEY_FILE, 0o600)
        except Exception:
            pass
    except Exception:
        pass


class AnalysisWorker(QObject):
    progress = Signal(str)
    finished = Signal(str, str)   # markdown_report, pdf_path
    failed = Signal(str)

    def __init__(self, zip_path: Path, api_key: str, out_pdf: Path):
        super().__init__()
        self.zip_path = zip_path
        self.api_key = api_key
        self.out_pdf = out_pdf

    def run(self):
        try:
            self.progress.emit("Extracting documents from ZIP...")
            extraction = extract_zip(self.zip_path)

            n_text = len(extraction.text_files)
            n_img = len(extraction.image_files)
            n_bad = len(extraction.unreadable_files)
            self.progress.emit(
                f"Extracted {n_text} text/document files, {n_img} images"
                + (f", {n_bad} unreadable" if n_bad else "")
                + ". Analyzing with Claude..."
            )

            report_md = analyze(
                extraction,
                api_key=self.api_key,
                progress=lambda msg: self.progress.emit(msg),
            )

            self.progress.emit("Generating PDF report...")
            render_pdf(report_md, self.out_pdf,
                       source_zip_name=self.zip_path.name)

            self.finished.emit(report_md, str(self.out_pdf))
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Disclosure Analyst")
        self.resize(1100, 800)

        self.api_key = load_saved_api_key() or os.environ.get("ANTHROPIC_API_KEY", "")
        self.zip_path: Path | None = None
        self.pdf_path: Path | None = None
        self.report_md: str | None = None
        self.thread: QThread | None = None
        self.worker: AnalysisWorker | None = None

        self._build_ui()
        self._refresh_buttons()

    def _build_ui(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_settings = QAction("API Key…", self)
        act_settings.triggered.connect(self.configure_api_key)
        toolbar.addAction(act_settings)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top row: file picker
        top = QHBoxLayout()
        self.pick_btn = QPushButton("Choose ZIP…")
        self.pick_btn.clicked.connect(self.choose_zip)
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setPlaceholderText("Select a disclosure .zip archive to analyze")
        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.clicked.connect(self.start_analysis)
        self.download_btn = QPushButton("Download PDF…")
        self.download_btn.clicked.connect(self.save_pdf_as)
        top.addWidget(self.pick_btn)
        top.addWidget(self.path_field, 1)
        top.addWidget(self.analyze_btn)
        top.addWidget(self.download_btn)
        layout.addLayout(top)

        # Status / progress
        prog_row = QHBoxLayout()
        self.status_label = QLabel("Idle.")
        self.status_label.setStyleSheet("color: #555;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setVisible(False)
        prog_row.addWidget(self.status_label, 1)
        prog_row.addWidget(self.progress_bar, 1)
        layout.addLayout(prog_row)

        # PDF preview
        self.pdf_doc = QPdfDocument(self)
        self.pdf_view = QPdfView(self)
        self.pdf_view.setDocument(self.pdf_doc)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        layout.addWidget(self.pdf_view, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")

    def _refresh_buttons(self):
        self.analyze_btn.setEnabled(bool(self.zip_path) and self.thread is None)
        self.download_btn.setEnabled(bool(self.pdf_path))
        self.pick_btn.setEnabled(self.thread is None)

    def configure_api_key(self):
        text, ok = QInputDialog.getText(
            self, "Anthropic API Key",
            "Enter your Anthropic API key (stored locally):",
            QLineEdit.EchoMode.Password,
            self.api_key,
        )
        if ok:
            self.api_key = text.strip()
            save_api_key(self.api_key)
            self.statusBar().showMessage("API key saved.", 4000)

    def choose_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose disclosure ZIP", "", "ZIP archives (*.zip)"
        )
        if path:
            self.zip_path = Path(path)
            self.path_field.setText(str(self.zip_path))
            self._refresh_buttons()

    def start_analysis(self):
        if not self.zip_path:
            return
        if not self.api_key:
            self.configure_api_key()
            if not self.api_key:
                QMessageBox.warning(self, "Missing API Key",
                                    "An Anthropic API key is required.")
                return

        out_pdf = Path(tempfile.gettempdir()) / f"{self.zip_path.stem}_report.pdf"

        self.progress_bar.setVisible(True)
        self.status_label.setText("Starting analysis…")

        self.thread = QThread(self)
        self.worker = AnalysisWorker(self.zip_path, self.api_key, out_pdf)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.start()
        self._refresh_buttons()

    def _on_progress(self, msg: str):
        self.status_label.setText(msg)
        self.statusBar().showMessage(msg)

    def _on_finished(self, report_md: str, pdf_path: str):
        self.report_md = report_md
        self.pdf_path = Path(pdf_path)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Done. Preview: {self.pdf_path.name}")
        self.pdf_doc.load(str(self.pdf_path))
        self._refresh_buttons()

    def _on_failed(self, err: str):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Analysis failed.")
        QMessageBox.critical(self, "Analysis failed", err)
        self._refresh_buttons()

    def _cleanup_thread(self):
        if self.thread:
            self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self._refresh_buttons()

    def save_pdf_as(self):
        if not self.pdf_path or not self.pdf_path.exists():
            return
        suggested = f"{self.zip_path.stem}_disclosure_report.pdf" if self.zip_path else "disclosure_report.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF report", suggested, "PDF files (*.pdf)"
        )
        if path:
            Path(path).write_bytes(self.pdf_path.read_bytes())
            self.statusBar().showMessage(f"Saved to {path}", 5000)


def main():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Disclosure Analyst")
    app.setOrganizationName("Disclosure Analyst")
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
