"""
Диалог редактирования справочника устройств (devices.json).
Поддерживает импорт/экспорт справочника в Excel.
"""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QComboBox, QMessageBox,
    QHeaderView, QAbstractItemView, QFileDialog
)
from PySide6.QtCore import Qt

import devices_io


def _app_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


DEVICES_FILE = _app_dir() / "devices.json"


class DeviceEditorDialog(QDialog):
    """Окно редактирования справочника коробок."""

    COL_NAME = 0
    COL_TYPE = 1
    COL_SECTION = 2
    COL_W = 3
    COL_D = 4
    COL_H = 5
    COL_WEIGHT = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование справочника коробок")
        self.resize(1100, 700)

        self.devices = self._load()

        layout = QVBoxLayout(self)

        # поиск + кнопки сверху
        top = QHBoxLayout()
        top.addWidget(QLabel("🔍 Поиск:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("фильтр по названию...")
        top.addWidget(self.search_edit, 1)

        self.btn_imp = QPushButton("📥 Импорт из Excel")
        self.btn_imp.setStyleSheet(
            "QPushButton { padding: 6px 8px; font-weight: bold; "
            "background: #1976d2; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #1565c0; }"
        )
        self.btn_imp.setToolTip(
            "Загрузить справочник из Excel-файла.\n"
            "Колонки: Название | Тип | Секция | Ш | Г | В | Вес.\n"
            "Совпадающие по названию записи можно заменить или пропустить."
        )

        self.btn_exp = QPushButton("📤 Экспорт в Excel")
        self.btn_exp.setStyleSheet(
            "QPushButton { padding: 6px 8px; font-weight: bold; "
            "background: #00838f; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #006064; }"
        )
        self.btn_exp.setToolTip(
            "Сохранить весь справочник в Excel-файл.\n"
            "Формат совместим с «📥 Импорт из Excel»."
        )

        top.addWidget(self.btn_imp)
        top.addWidget(self.btn_exp)

        self.btn_add = QPushButton("➕ Добавить")
        self.btn_dup = QPushButton("📋 Дублировать")
        self.btn_del = QPushButton("➖ Удалить")
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_dup)
        top.addWidget(self.btn_del)
        layout.addLayout(top)

        # таблица
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Название", "Тип", "Секция",
            "Ш (мм)", "Г (мм)", "В (мм)", "Вес (кг)"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 240)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked |
                                   QAbstractItemView.EditKeyPressed)
        layout.addWidget(self.table, 1)

        hint = QLabel(
            "Тип: <b>обычная</b> или <b>МАСТЕР</b>.  "
            "Размеры Ш×Г×В в мм.  "
            "Вес в кг (можно оставить пустым для МАСТЕР-коробок).  "
            "Двойной клик по ячейке — редактирование.  "
            "📥 Импорт / 📤 Экспорт — обмен справочником через Excel."
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setTextFormat(Qt.RichText)
        layout.addWidget(hint)

        # кнопки снизу
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_save = QPushButton("💾 Сохранить")
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "font-weight: bold; padding: 8px 20px; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        self.btn_cancel = QPushButton("Отмена")
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_save)
        layout.addLayout(bottom)

        # сигналы
        self.search_edit.textChanged.connect(self.refresh_table)
        self.btn_add.clicked.connect(self.add_row)
        self.btn_dup.clicked.connect(self.dup_row)
        self.btn_del.clicked.connect(self.del_row)
        self.btn_imp.clicked.connect(self.import_excel)
        self.btn_exp.clicked.connect(self.export_excel)
        self.btn_save.clicked.connect(self.save)
        self.btn_cancel.clicked.connect(self.reject)

        self.refresh_table()

    # ---------- работа с файлом ----------
    def _load(self):
        if not DEVICES_FILE.exists():
            return []
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, devices):
        with open(DEVICES_FILE, "w", encoding="utf-8") as f:
            json.dump(devices, f, ensure_ascii=False, indent=2)

    # ---------- таблица ----------
    def refresh_table(self):
        ft = self.search_edit.text().lower().strip()
        self.table.setRowCount(0)
        for d in self.devices:
            if ft and ft not in d["name"].lower():
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._fill_row(row, d)

    def _fill_row(self, row, d):
        name = d.get("name", "")
        is_master = d.get("type") == "master"
        kind = "МАСТЕР" if is_master else "обычная"
        section = d.get("section", "") or ""

        dims = d.get("dims_mm") or (0, 0, 0)
        w = "" if d.get("weight_kg") is None else str(d.get("weight_kg"))

        self.table.setItem(row, self.COL_NAME, QTableWidgetItem(name))
        self.table.setItem(row, self.COL_TYPE, QTableWidgetItem(kind))
        self.table.setItem(row, self.COL_SECTION, QTableWidgetItem(section))
        self.table.setItem(row, self.COL_W, QTableWidgetItem(str(int(dims[0]))))
        self.table.setItem(row, self.COL_D, QTableWidgetItem(str(int(dims[1]))))
        self.table.setItem(row, self.COL_H, QTableWidgetItem(str(int(dims[2]))))
        self.table.setItem(row, self.COL_WEIGHT, QTableWidgetItem(w))

    def _collect_from_table(self):
        """Считывает таблицу и превращает в список dict для devices.json."""
        devices = []
        errors = []
        for row in range(self.table.rowCount()):
            try:
                name = self.table.item(row, self.COL_NAME).text().strip()
                kind = self.table.item(row, self.COL_TYPE).text().strip().upper()
                section = (self.table.item(row, self.COL_SECTION).text().strip()
                           if self.table.item(row, self.COL_SECTION) else "")
                w = float(self.table.item(row, self.COL_W).text().replace(",", "."))
                d = float(self.table.item(row, self.COL_D).text().replace(",", "."))
                h = float(self.table.item(row, self.COL_H).text().replace(",", "."))

                weight_item = self.table.item(row, self.COL_WEIGHT)
                weight_str = weight_item.text().strip() if weight_item else ""
                weight = float(weight_str.replace(",", ".")) if weight_str else None

                if not name:
                    continue

                devices.append({
                    "name": name,
                    "section": section,
                    "type": "master" if "МАСТЕР" in kind or kind == "MASTER" else "box",
                    "dims_mm": [w, d, h],
                    "weight_kg": weight,
                })
            except Exception as e:
                errors.append(f"Строка {row + 1}: {e}")
        return devices, errors

    # ---------- кнопки ----------
    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        dummy = {
            "name": "НОВАЯ-КОРОБКА",
            "type": "box",
            "section": "",
            "dims_mm": (200, 200, 100),
            "weight_kg": 1.0,
        }
        self._fill_row(row, dummy)
        self.table.setCurrentCell(row, self.COL_NAME)
        self.table.editItem(self.table.item(row, self.COL_NAME))

    def dup_row(self):
        cur = self.table.currentRow()
        if cur < 0:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(self.table.columnCount()):
            src = self.table.item(cur, col)
            new_item = QTableWidgetItem(src.text() if src else "")
            self.table.setItem(row, col, new_item)

    def del_row(self):
        cur = self.table.currentRow()
        if cur < 0:
            return
        name_item = self.table.item(cur, self.COL_NAME)
        name = name_item.text() if name_item else "?"
        if QMessageBox.question(
            self, "Подтверждение", f"Удалить «{name}»?"
        ) == QMessageBox.Yes:
            self.table.removeRow(cur)

    # ---------- импорт / экспорт Excel ----------
    def export_excel(self):
        # на всякий случай синхронизируем self.devices с таблицей
        devices, errors = self._collect_from_table()
        if errors:
            ans = QMessageBox.question(
                self, "Ошибки в данных",
                "В таблице есть некорректные строки. "
                "Экспортировать то, что удалось прочитать?\n\n"
                + "\n".join(errors[:5])
            )
            if ans != QMessageBox.Yes:
                return

        if not devices:
            QMessageBox.warning(self, "Экспорт", "Справочник пуст.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт справочника в Excel", "devices.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".xlsm")):
            path += ".xlsx"

        try:
            devices_io.export_devices_xlsx(devices, path)
        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка", f"Не удалось сохранить файл:\n{e}"
            )
            return

        QMessageBox.information(
            self, "Готово",
            f"Экспортировано записей: {len(devices)}\n\n{path}"
        )

    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт справочника из Excel", "",
            "Excel (*.xlsx *.xlsm);;Все файлы (*)"
        )
        if not path:
            return

        try:
            imported, errors = devices_io.import_devices_xlsx(path)
        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка", f"Не удалось прочитать файл:\n{e}"
            )
            return

        if not imported:
            QMessageBox.warning(
                self, "Пусто",
                "В файле не найдено ни одной записи.\n"
                "Ожидаются колонки: Название | Тип | Секция | Ш | Г | В | Вес."
            )
            return

        # считаем дубликаты по имени
        existing_names = {d.get("name", "") for d in self.devices}
        new_count = sum(1 for d in imported if d["name"] not in existing_names)
        dup_count = len(imported) - new_count

        replace_existing = False
        if dup_count > 0:
            msg = QMessageBox(self)
            msg.setWindowTitle("Дубликаты")
            msg.setText(
                f"В файле {len(imported)} записей:\n"
                f"  • Новых: {new_count}\n"
                f"  • Совпадают по имени с текущими: {dup_count}\n\n"
                f"Что делать с совпадающими?"
            )
            btn_replace = msg.addButton(
                "Заменить существующие", QMessageBox.AcceptRole
            )
            btn_skip = msg.addButton(
                "Пропустить (только новые)", QMessageBox.AcceptRole
            )
            btn_cancel = msg.addButton("Отмена", QMessageBox.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked is btn_cancel:
                return
            replace_existing = (clicked is btn_replace)

        merged = list(self.devices)
        by_name = {d.get("name", ""): i for i, d in enumerate(merged)}

        for d in imported:
            nm = d["name"]
            if nm in by_name:
                if replace_existing:
                    merged[by_name[nm]] = d
            else:
                by_name[nm] = len(merged)
                merged.append(d)

        self.devices = merged
        self._save(self.devices)     # сразу сохраняем в devices.json
        self.refresh_table()

        if errors:
            QMessageBox.warning(
                self, "Готово (с замечаниями)",
                f"Импортировано. Всего записей в справочнике: "
                f"{len(self.devices)}\n"
                f"Пропущено строк с ошибками: {len(errors)}\n\n"
                + "\n".join(errors[:5])
                + ("\n…" if len(errors) > 5 else "")
            )
        else:
            QMessageBox.information(
                self, "Готово",
                f"Импортировано. Всего записей: {len(self.devices)}"
            )

    # ---------- сохранение ----------
    def save(self):
        devices, errors = self._collect_from_table()
        if errors:
            QMessageBox.critical(
                self, "Ошибки в данных",
                "Исправь ошибки перед сохранением:\n\n" + "\n".join(errors[:10])
            )
            return

        if not devices:
            QMessageBox.warning(self, "Пусто", "Справочник пуст — сохранение отменено.")
            return

        # сохраняем файл рядом с приложением
        self._save(devices)
        QMessageBox.information(
            self, "Сохранено",
            f"Сохранено {len(devices)} записей в:\n{DEVICES_FILE}"
        )
        self.accept()