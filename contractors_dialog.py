"""
Справочник контрагентов: список, поиск, выбор, редактирование, удаление.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QFormLayout, QTextEdit, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt

import contractors as cnt


class ContractorPickerDialog(QDialog):
    """Диалог выбора/редактирования контрагентов."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справочник контрагентов")
        self.resize(950, 560)

        self._selected = None
        layout = QVBoxLayout(self)

        # ---------- поиск + кнопки ----------
        top = QHBoxLayout()
        top.addWidget(QLabel("🔍 Поиск:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("название, ИНН, контакт, телефон...")
        self.search.textChanged.connect(self.refresh)
        top.addWidget(self.search, 1)

        self.btn_add = QPushButton("➕ Добавить")
        self.btn_add.setStyleSheet(
            "QPushButton { padding: 6px 10px; font-weight: bold; "
            "background: #1976d2; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #1565c0; }"
        )
        self.btn_add.clicked.connect(self.add_contractor)
        top.addWidget(self.btn_add)

        self.btn_edit = QPushButton("✏️ Редактировать")
        self.btn_edit.clicked.connect(self.edit_contractor)
        top.addWidget(self.btn_edit)

        self.btn_del = QPushButton("🗑 Удалить")
        self.btn_del.setStyleSheet(
            "QPushButton { padding: 6px 10px; font-weight: bold; "
            "background: #d32f2f; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #b71c1c; }"
        )
        self.btn_del.clicked.connect(self.delete_contractor)
        top.addWidget(self.btn_del)

        layout.addLayout(top)

        # ---------- таблица ----------
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Организация / ФИО", "ИНН", "Контактное лицо",
            "Телефон", "Адрес"
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(lambda _item: self._on_ok())
        layout.addWidget(self.table, 1)

        # ---------- нижние кнопки ----------
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_cancel = QPushButton("Закрыть")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Выбрать")
        btn_ok.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        btn_ok.clicked.connect(self._on_ok)
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_ok)
        layout.addLayout(bottom)

        self.refresh()

    # ---------- список ----------

    def refresh(self):
        query = self.search.text()
        records = cnt.search_contractors(query)
        self.table.setRowCount(0)
        for c in records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(c.get("entity_name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(c.get("inn", "")))
            self.table.setItem(row, 2, QTableWidgetItem(c.get("contact_person", "")))
            self.table.setItem(row, 3, QTableWidgetItem(c.get("contact_phone", "")))
            self.table.setItem(row, 4, QTableWidgetItem(c.get("address", "")))

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    # ---------- выбор ----------

    def _current_name_inn(self) -> tuple:
        cur = self.table.currentRow()
        if cur < 0:
            return "", ""
        name_item = self.table.item(cur, 0)
        inn_item = self.table.item(cur, 1)
        name = name_item.text() if name_item else ""
        inn = inn_item.text() if inn_item else ""
        return name, inn

    def _on_ok(self):
        name, inn = self._current_name_inn()
        if not name:
            QMessageBox.information(self, "Выбор", "Выбери строку из списка.")
            return

        record = cnt.find_contractor(name, inn)
        if record is None:
            for c in cnt.load_contractors():
                if (c.get("entity_name", "").strip().lower()
                        == name.strip().lower()):
                    record = c
                    break

        if record is None:
            cur = self.table.currentRow()
            record = {
                "entity_name": name,
                "inn": inn,
                "contact_person": self.table.item(cur, 2).text()
                    if self.table.item(cur, 2) else "",
                "contact_phone": self.table.item(cur, 3).text()
                    if self.table.item(cur, 3) else "",
                "address": self.table.item(cur, 4).text()
                    if self.table.item(cur, 4) else "",
                "entity_type": "legal",
            }

        self._selected = record
        self.accept()

    def get_selected(self) -> dict | None:
        return self._selected

    # ---------- действия ----------

    def add_contractor(self):
        dlg = ContractorEditDialog(None, self)
        if dlg.exec():
            self.refresh()

    def edit_contractor(self):
        name, inn = self._current_name_inn()
        if not name:
            QMessageBox.information(self, "Редактирование",
                                    "Выбери строку из списка.")
            return
        record = cnt.find_contractor(name, inn)
        if record is None:
            QMessageBox.warning(self, "Ошибка",
                                "Не удалось найти контрагента в базе.")
            return
        dlg = ContractorEditDialog(record, self)
        if dlg.exec():
            self.refresh()

    def delete_contractor(self):
        name, inn = self._current_name_inn()
        if not name:
            QMessageBox.information(self, "Удаление",
                                    "Выбери строку из списка.")
            return
        ans = QMessageBox.question(
            self, "Удаление контрагента",
            f"Удалить из справочника?\n\n"
            f"Организация: {name}\n"
            f"ИНН: {inn or '—'}\n\n"
            f"Это действие нельзя отменить.\n"
            f"(Уже созданные отправки не пострадают.)"
        )
        if ans != QMessageBox.Yes:
            return
        cnt.delete_contractor(name, inn)
        self.refresh()


# ============================================================
#             Редактор одного контрагента
# ============================================================

class ContractorEditDialog(QDialog):
    """Форма создания/редактирования одного контрагента."""

    def __init__(self, record: dict | None = None, parent=None):
        super().__init__(parent)
        self.is_new = record is None
        self.record = record or {}

        self.setWindowTitle(
            "Новый контрагент" if self.is_new
            else f"Редактирование: {self.record.get('entity_name', '')}"
        )
        self.resize(560, 620)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.entity_type = QComboBox()
        self.entity_type.addItem("Юридическое лицо", "legal")
        self.entity_type.addItem("Физическое лицо", "physical")
        idx = 0 if self.record.get("entity_type", "legal") == "legal" else 1
        self.entity_type.setCurrentIndex(idx)
        self.entity_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Тип лица:", self.entity_type)

        self.entity_name = QLineEdit(self.record.get("entity_name", ""))
        form.addRow("Наименование / ФИО:", self.entity_name)

        self.inn = QLineEdit(self.record.get("inn", ""))
        form.addRow("ИНН:", self.inn)

        self.address = QTextEdit()
        self.address.setPlainText(self.record.get("address", ""))
        self.address.setMaximumHeight(80)
        form.addRow("Адрес доставки:", self.address)

        self.contact_person = QLineEdit(self.record.get("contact_person", ""))
        form.addRow("Контактное лицо:", self.contact_person)

        self.contact_phone = QLineEdit(self.record.get("contact_phone", ""))
        form.addRow("Телефон:", self.contact_phone)

        self.work_hours = QLineEdit(self.record.get("work_hours", ""))
        self.work_hours.setPlaceholderText("например, 09:00–18:00")
        form.addRow("Время работы:", self.work_hours)

        break_row = QHBoxLayout()
        self.has_break = QCheckBox("Есть перерыв")
        self.has_break.setChecked(bool(self.record.get("has_break", False)))
        self.has_break.toggled.connect(
            lambda v: self.break_time.setEnabled(v)
        )
        break_row.addWidget(self.has_break)
        self.break_time = QLineEdit(self.record.get("break_time", ""))
        self.break_time.setPlaceholderText("например, 13:00–14:00")
        self.break_time.setEnabled(self.has_break.isChecked())
        break_row.addWidget(self.break_time, 1)
        form.addRow("Перерыв:", break_row)

        check_row = QHBoxLayout()
        self.call_before = QCheckBox("Позвонить за 30 мин")
        self.call_before.setChecked(bool(self.record.get("call_before_30min", False)))
        check_row.addWidget(self.call_before)

        self.need_pass = QCheckBox("Нужен пропуск")
        self.need_pass.setChecked(bool(self.record.get("need_pass", False)))
        check_row.addWidget(self.need_pass)
        check_row.addStretch(1)
        form.addRow("Особые условия:", check_row)

        self.comment = QTextEdit()
        self.comment.setPlainText(self.record.get("comment", ""))
        self.comment.setMaximumHeight(70)
        form.addRow("Комментарий:", self.comment)

        layout.addLayout(form)
        layout.addStretch(1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("💾 Сохранить")
        btn_save.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        btn_save.clicked.connect(self.save)
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_save)
        layout.addLayout(bottom)

        self._on_type_changed()

    def _on_type_changed(self):
        is_legal = self.entity_type.currentData() == "legal"
        self.inn.setEnabled(is_legal)
        if not is_legal:
            self.inn.setText("")

    def save(self):
        name = self.entity_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Проверка",
                                "Укажи Наименование / ФИО.")
            return

        # при редактировании — если имя/ИНН изменились, удаляем старую запись
        if not self.is_new:
            old_name = self.record.get("entity_name", "")
            old_inn = self.record.get("inn", "")
            new_inn = self.inn.text().strip()
            if old_name != name or old_inn != new_inn:
                cnt.delete_contractor(old_name, old_inn)

        cnt.upsert_contractor({
            "entity_type": self.entity_type.currentData(),
            "entity_name": name,
            "inn": self.inn.text().strip(),
            "address": self.address.toPlainText().strip(),
            "contact_person": self.contact_person.text().strip(),
            "contact_phone": self.contact_phone.text().strip(),
            "work_hours": self.work_hours.text().strip(),
            "has_break": self.has_break.isChecked(),
            "break_time": self.break_time.text().strip(),
            "call_before_30min": self.call_before.isChecked(),
            "need_pass": self.need_pass.isChecked(),
            "comment": self.comment.toPlainText().strip(),
        })
        self.accept()