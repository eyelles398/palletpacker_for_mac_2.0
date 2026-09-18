"""
Простой диалог подготовки письма для Outlook.
Получатель НЕ вводится здесь — он выбирается в самом Outlook.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QCheckBox, QPushButton, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt


class EmailDialog(QDialog):
    """Только классический Outlook. Тема, текст, вложения."""

    def __init__(self, default_subject: str, default_body: str,
                 can_attach_pdf: bool, can_attach_xlsx: bool,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отправить отчёт через Outlook")
        self.resize(620, 520)

        layout = QVBoxLayout(self)

        # Тема
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Тема:"))
        self.subject_edit = QLineEdit(default_subject)
        row2.addWidget(self.subject_edit, 1)
        layout.addLayout(row2)

        # Тело
        layout.addWidget(QLabel("Текст письма:"))
        self.body_edit = QTextEdit()
        self.body_edit.setPlainText(default_body)
        layout.addWidget(self.body_edit, 1)

        # Вложения
        att_group = QGroupBox("Вложения")
        att_layout = QVBoxLayout(att_group)
        self.cb_pdf = QCheckBox("PDF-отчёт (.pdf)")
        self.cb_pdf.setChecked(can_attach_pdf)
        self.cb_pdf.setEnabled(can_attach_pdf)
        self.cb_xlsx = QCheckBox("Excel-отчёт (.xlsx)")
        self.cb_xlsx.setChecked(can_attach_xlsx)
        self.cb_xlsx.setEnabled(can_attach_xlsx)
        att_layout.addWidget(self.cb_pdf)
        att_layout.addWidget(self.cb_xlsx)
        layout.addWidget(att_group)

        # Подсказка
        hint = QLabel(
            "Откроется <b>классический Outlook</b> с новым письмом: "
            "тема и текст уже заполнены, файлы прикреплены.<br>"
            "Получателя выбери в самом Outlook из адресной книги "
            "(кнопка <b>«Кому…»</b>)."
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setTextFormat(Qt.RichText)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Кнопки
        bottom = QHBoxLayout()
        bottom.addStretch(1)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_send = QPushButton("📧 Открыть в Outlook")
        self.btn_send.setStyleSheet(
            "QPushButton { background-color: #1976d2; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #1565c0; }"
        )

        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_send)
        layout.addLayout(bottom)

        self.btn_send.clicked.connect(self._on_send)
        self.btn_cancel.clicked.connect(self.reject)

    def _on_send(self):
        if not (self.cb_pdf.isChecked() or self.cb_xlsx.isChecked()):
            QMessageBox.warning(
                self, "Вложения",
                "Отметь хотя бы одно вложение."
            )
            return
        self.accept()

    # ---------- геттеры ----------

    def get_subject(self) -> str:
        return self.subject_edit.text().strip()

    def get_body(self) -> str:
        return self.body_edit.toPlainText()

    def wants_pdf(self) -> bool:
        return self.cb_pdf.isChecked() and self.cb_pdf.isEnabled()

    def wants_xlsx(self) -> bool:
        return self.cb_xlsx.isChecked() and self.cb_xlsx.isEnabled()


# ---------- подготовка вложений ----------

def prepare_attachments(data, need_pdf: bool, need_xlsx: bool,
                        viewer=None) -> tuple:
    """
    Готовит временные файлы PDF/XLSX для вложения.
    Возвращает (paths, warnings).
    """
    import tempfile
    import exporter

    paths = []
    warnings = []

    tmp_dir = Path(tempfile.gettempdir()) / "PalletPacker_mail"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return [], [f"Не удалось создать папку TEMP: {e}"]

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    if need_pdf:
        pdf_path = tmp_dir / f"pallet_report_{stamp}.pdf"
        try:
            img = None
            if viewer is not None:
                try:
                    img = viewer.render_screenshot(scale=2)
                except Exception:
                    img = None
            exporter.export_pdf(data, str(pdf_path), image=img)
            paths.append(str(pdf_path))
        except Exception as e:
            warnings.append(f"PDF не сохранён: {e}")

    if need_xlsx:
        xlsx_path = tmp_dir / f"pallet_report_{stamp}.xlsx"
        try:
            exporter.export_excel(data, str(xlsx_path))
            paths.append(str(xlsx_path))
        except Exception as e:
            warnings.append(f"Excel не сохранён: {e}")

    return paths, warnings