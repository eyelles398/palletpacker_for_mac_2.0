"""
Окно «Отгрузки»: список отправок демо-оборудования.
Плюс: экспорт PDF (ТК и внутренний), Excel экспорт/импорт.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont

import shipments as shp
import shipments_export as shexp
from shipment_form import ShipmentFormDialog


STATUS_FILTERS = [
    ("Все", ""),
    ("В пути", shp.STATUS_IN_TRANSIT),
    ("Доставлено", shp.STATUS_DELIVERED),
    ("Просрочено", shp.STATUS_OVERDUE),
    ("Возвращено", shp.STATUS_RETURNED),
]


class ShipmentsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отгрузки демо-оборудования")
        self.resize(1250, 720)

        layout = QVBoxLayout(self)

        # ---------- фильтры ----------
        top = QHBoxLayout()
        top.addWidget(QLabel("🔍 Поиск:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "номер, адрес, получатель, контакт, телефон..."
        )
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search, 1)

        top.addWidget(QLabel("Статус:"))
        self.status_combo = QComboBox()
        for label, value in STATUS_FILTERS:
            self.status_combo.addItem(label, value)
        self.status_combo.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.status_combo)

        layout.addLayout(top)

        # ---------- таблица ----------
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Номер", "Статус", "Создано",
            "Получатель", "Город/адрес",
            "Отправка", "Возврат (план)", "Состав"
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_shipment)
        layout.addWidget(self.table, 1)

        # ---------- нижние кнопки ----------
        bottom = QHBoxLayout()

        self.btn_new = QPushButton("➕ Новая отправка")
        self.btn_new.setStyleSheet(
            "QPushButton { padding: 6px 12px; font-weight: bold; "
            "background: #1976d2; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #1565c0; }"
        )
        self.btn_new.clicked.connect(self.new_shipment)
        bottom.addWidget(self.btn_new)

        self.btn_edit = QPushButton("✏️ Редактировать")
        self.btn_edit.clicked.connect(self.edit_shipment)
        bottom.addWidget(self.btn_edit)

        self.btn_return = QPushButton("↩️ Вернуть")
        self.btn_return.setToolTip("Поставить фактическую дату возврата = сегодня")
        self.btn_return.clicked.connect(self.mark_returned)
        bottom.addWidget(self.btn_return)

        self.btn_delete = QPushButton("🗑 Удалить")
        self.btn_delete.clicked.connect(self.delete_shipment)
        bottom.addWidget(self.btn_delete)

        bottom.addStretch(1)

        self.btn_contractors = QPushButton("📇 Справочник")
        self.btn_contractors.clicked.connect(self.open_contractors)
        bottom.addWidget(self.btn_contractors)

        layout.addLayout(bottom)

        # ---------- нижний ряд: экспорт/импорт/печать ----------
        io_row = QHBoxLayout()

        self.btn_pdf_tk = QPushButton("📄 PDF для ТК")
        self.btn_pdf_tk.setStyleSheet(
            "QPushButton { padding: 6px 12px; font-weight: bold; "
            "background: #1976d2; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #1565c0; }"
        )
        self.btn_pdf_tk.setToolTip(
            "Накладная для транспортной компании — крупный адрес,\n"
            "контакты, галочки «позвонить/пропуск», состав груза."
        )
        self.btn_pdf_tk.clicked.connect(self.export_tk_pdf)
        io_row.addWidget(self.btn_pdf_tk)

        self.btn_pdf_internal = QPushButton("📄 PDF внутренний")
        self.btn_pdf_internal.setStyleSheet(
            "QPushButton { padding: 6px 12px; font-weight: bold; "
            "background: #2e7d32; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #388e3c; }"
        )
        self.btn_pdf_internal.setToolTip(
            "Полный отчёт: адрес, все контакты, состав,\n"
            "серийники, все даты, стоимость доставки."
        )
        self.btn_pdf_internal.clicked.connect(self.export_internal_pdf)
        io_row.addWidget(self.btn_pdf_internal)

        io_row.addSpacing(20)

        self.btn_excel_export = QPushButton("📤 Excel экспорт")
        self.btn_excel_export.setStyleSheet(
            "QPushButton { padding: 6px 12px; font-weight: bold; "
            "background: #00838f; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #006064; }"
        )
        self.btn_excel_export.setToolTip(
            "Сохранить все отправки в Excel — для передачи коллегам\n"
            "или резервной копии."
        )
        self.btn_excel_export.clicked.connect(self.export_excel)
        io_row.addWidget(self.btn_excel_export)

        self.btn_excel_import = QPushButton("📥 Excel импорт")
        self.btn_excel_import.setStyleSheet(
            "QPushButton { padding: 6px 12px; font-weight: bold; "
            "background: #7b1fa2; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #6a1b9a; }"
        )
        self.btn_excel_import.setToolTip(
            "Загрузить отправки из Excel-файла, полученного от коллеги."
        )
        self.btn_excel_import.clicked.connect(self.import_excel)
        io_row.addWidget(self.btn_excel_import)

        io_row.addStretch(1)

        self.btn_close = QPushButton("Закрыть")
        self.btn_close.clicked.connect(self.accept)
        io_row.addWidget(self.btn_close)

        layout.addLayout(io_row)

        self.refresh()

    # ---------- список ----------

    def refresh(self):
        text = self.search.text()
        status = self.status_combo.currentData() or ""

        records = shp.load_shipments()
        records = shp.filter_records(records, text=text, status=status)

        def sort_key(r):
            eff = shp.compute_status(r)
            priority = 0 if eff == shp.STATUS_OVERDUE else 1
            return (priority, r.get("created_at", ""))
        records.sort(key=sort_key, reverse=False)
        records.reverse()

        self.table.setRowCount(0)
        for r in records:
            row = self.table.rowCount()
            self.table.insertRow(row)

            items_txt = shp.summary_text(r)
            addr_short = (r.get("address", "") or "").split("\n")[0]
            if len(addr_short) > 60:
                addr_short = addr_short[:60] + "…"

            vals = [
                r.get("id", ""),
                shp.status_label(r),
                r.get("created_at", ""),
                r.get("entity_name", ""),
                addr_short,
                r.get("ship_date", ""),
                r.get("planned_return_date", "") or "—",
                items_txt,
            ]
            color = QColor(shp.status_color(r))
            for col, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if col == 1:
                    item.setForeground(QBrush(QColor("#ffffff")))
                    item.setBackground(QBrush(color))
                    f = QFont()
                    f.setBold(True)
                    item.setFont(f)
                self.table.setItem(row, col, item)

        self.setWindowTitle(
            f"Отгрузки демо-оборудования — {len(records)} записей"
        )

    # ---------- действия ----------

    def _current_record(self) -> dict | None:
        cur = self.table.currentRow()
        if cur < 0:
            return None
        sid = self.table.item(cur, 0).text()
        return shp.get_shipment(sid)

    def new_shipment(self):
        dlg = ShipmentFormDialog(None, self)
        if dlg.exec():
            self.refresh()

    def edit_shipment(self):
        rec = self._current_record()
        if rec is None:
            QMessageBox.information(self, "Редактирование",
                                    "Выбери строку из списка.")
            return
        dlg = ShipmentFormDialog(rec, self)
        if dlg.exec():
            self.refresh()

    def mark_returned(self):
        rec = self._current_record()
        if rec is None:
            QMessageBox.information(self, "Возврат",
                                    "Выбери строку из списка.")
            return
        if rec.get("actual_return_date"):
            QMessageBox.information(
                self, "Возврат",
                f"Отправка {rec['id']} уже возвращена "
                f"({rec['actual_return_date']})."
            )
            return
        ans = QMessageBox.question(
            self, "Возврат",
            f"Отметить отправку {rec['id']} как возвращённую сегодня?"
        )
        if ans != QMessageBox.Yes:
            return
        shp.mark_returned(rec["id"])
        self.refresh()

    def delete_shipment(self):
        rec = self._current_record()
        if rec is None:
            QMessageBox.information(self, "Удаление",
                                    "Выбери строку из списка.")
            return
        ans = QMessageBox.question(
            self, "Удаление",
            f"Удалить отправку {rec['id']} навсегда?\n\n"
            f"Получатель: {rec.get('entity_name', '')}\n"
            f"Дата: {rec.get('ship_date', '')}"
        )
        if ans != QMessageBox.Yes:
            return
        shp.delete_shipment(rec["id"])
        self.refresh()

    def open_contractors(self):
        from contractors_dialog import ContractorPickerDialog
        dlg = ContractorPickerDialog(self)
        dlg.exec()

    # ---------- PDF ----------

    def export_tk_pdf(self):
        rec = self._current_record()
        if rec is None:
            QMessageBox.information(self, "PDF для ТК",
                                    "Выбери строку из списка.")
            return
        default = f"TK_{rec['id']}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PDF для ТК", default, "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            shexp.export_tk_pdf(rec, path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        QMessageBox.information(self, "Готово", f"PDF сохранён:\n{path}")

    def export_internal_pdf(self):
        rec = self._current_record()
        if rec is None:
            QMessageBox.information(self, "PDF внутренний",
                                    "Выбери строку из списка.")
            return
        default = f"Отправка_{rec['id']}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить внутренний PDF", default, "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            shexp.export_internal_pdf(rec, path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        QMessageBox.information(self, "Готово", f"PDF сохранён:\n{path}")

    # ---------- Excel ----------

    def export_excel(self):
        records = shp.load_shipments()
        if not records:
            QMessageBox.information(self, "Экспорт", "Нет отправок.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт отправок в Excel", "shipments.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".xlsm")):
            path += ".xlsx"
        try:
            shexp.export_shipments_xlsx(records, path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        QMessageBox.information(
            self, "Готово",
            f"Экспортировано {len(records)} отправок:\n{path}"
        )

    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт отправок из Excel", "",
            "Excel (*.xlsx *.xlsm);;Все файлы (*)"
        )
        if not path:
            return

        try:
            imported, warns = shexp.import_shipments_xlsx(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка импорта", str(e))
            return

        if not imported:
            QMessageBox.warning(self, "Импорт",
                                "В файле не найдено ни одной отправки.")
            return

        existing = {r.get("id", "") for r in shp.load_shipments()}
        new_count = sum(1 for r in imported if r["id"] not in existing)
        dup_count = len(imported) - new_count

        replace = False
        if dup_count > 0:
            msg = QMessageBox(self)
            msg.setWindowTitle("Дубликаты")
            msg.setText(
                f"В файле {len(imported)} записей:\n"
                f"  • Новых: {new_count}\n"
                f"  • Уже есть по номеру: {dup_count}\n\n"
                f"Что делать с существующими?"
            )
            btn_replace = msg.addButton("Заменить существующие",
                                        QMessageBox.AcceptRole)
            btn_skip = msg.addButton("Пропустить (только новые)",
                                     QMessageBox.AcceptRole)
            btn_cancel = msg.addButton("Отмена", QMessageBox.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked is btn_cancel:
                return
            replace = (clicked is btn_replace)

        current = shp.load_shipments()
        by_id = {r.get("id", ""): i for i, r in enumerate(current)}

        for r in imported:
            rid = r["id"]
            if rid in by_id:
                if replace:
                    current[by_id[rid]] = r
            else:
                by_id[rid] = len(current)
                current.append(r)

        shp.save_shipments(current)
        self.refresh()

        QMessageBox.information(
            self, "Импорт завершён",
            f"Всего записей: {len(current)}\n"
            f"Новых добавлено: {new_count}\n"
            f"Обновлено: {dup_count if replace else 0}"
        )