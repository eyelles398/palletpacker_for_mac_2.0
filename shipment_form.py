"""
Форма создания/редактирования отправки демо-оборудования.
Расширенный состав: модель, количество, размеры, вес, серийники.
Контрагент автоматически попадает в справочник при сохранении.
"""
from __future__ import annotations

from datetime import datetime, date

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QCheckBox, QPushButton, QMessageBox, QGroupBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFormLayout, QScrollArea, QWidget, QFrame, QDateEdit
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QBrush, QColor, QFont

import shipments as shp
import contractors as cnt


class ShipmentFormDialog(QDialog):
    """Форма создания/редактирования отправки."""

    COL_MODEL = 0
    COL_QTY = 1
    COL_DIMS = 2
    COL_WEIGHT = 3
    COL_SERIALS = 4

    def __init__(self, record: dict | None = None, parent=None):
        super().__init__(parent)
        self.is_new = record is None
        self.record = record if record else shp.new_record()

        self.setWindowTitle(
            "Новая отправка" if self.is_new
            else f"Отправка {self.record.get('id', '')}"
        )
        self.resize(960, 920)

        self.devices_map = self._collect_devices_map()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, 1)

        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)

        # ============ Заголовок ============
        header = QGroupBox("Отправка")
        hf = QFormLayout(header)

        self.id_label = QLabel(self.record.get("id", "—"))
        f = QFont(); f.setBold(True)
        self.id_label.setFont(f)

        self.created_label = QLabel(self.record.get("created_at", "—"))
        self.status_label = QLabel(shp.status_label(self.record))

        hf.addRow("Номер:", self.id_label)
        hf.addRow("Создано:", self.created_label)
        hf.addRow("Статус:", self.status_label)
        layout.addWidget(header)

        # ============ Получатель ============
        recv = QGroupBox("Получатель (для транспортной компании)")
        rf = QFormLayout(recv)

        pick_row = QHBoxLayout()
        self.btn_pick = QPushButton("📋 Выбрать из справочника")
        self.btn_pick.clicked.connect(self.pick_contractor)
        pick_row.addWidget(self.btn_pick)

        hint_pick = QLabel(
            "<i>Все контрагенты автоматически сохраняются в справочник "
            "при сохранении отправки.</i>"
        )
        hint_pick.setStyleSheet("color: #666; font-size: 11px;")
        hint_pick.setTextFormat(Qt.RichText)
        pick_row.addWidget(hint_pick)
        pick_row.addStretch(1)
        rf.addRow("", pick_row)

        self.entity_type = QComboBox()
        self.entity_type.addItem("Юридическое лицо", "legal")
        self.entity_type.addItem("Физическое лицо", "physical")
        idx = 0 if self.record.get("entity_type", "legal") == "legal" else 1
        self.entity_type.setCurrentIndex(idx)
        self.entity_type.currentIndexChanged.connect(self._on_entity_type_changed)
        rf.addRow("Тип лица:", self.entity_type)

        self.entity_name = QLineEdit(self.record.get("entity_name", ""))
        rf.addRow("Наименование / ФИО:", self.entity_name)

        self.inn = QLineEdit(self.record.get("inn", ""))
        rf.addRow("ИНН:", self.inn)

        self.address = QTextEdit()
        self.address.setPlainText(self.record.get("address", ""))
        self.address.setMaximumHeight(70)
        rf.addRow("Адрес доставки:", self.address)

        self.contact_person = QLineEdit(self.record.get("contact_person", ""))
        rf.addRow("Контактное лицо:", self.contact_person)

        self.contact_phone = QLineEdit(self.record.get("contact_phone", ""))
        rf.addRow("Телефон:", self.contact_phone)

        self.work_hours = QLineEdit(self.record.get("work_hours", ""))
        self.work_hours.setPlaceholderText("например, 09:00–18:00")
        rf.addRow("Время работы:", self.work_hours)

        break_row = QHBoxLayout()
        self.has_break = QCheckBox("Есть перерыв")
        self.has_break.setChecked(bool(self.record.get("has_break", False)))
        self.has_break.toggled.connect(self._on_break_toggled)
        break_row.addWidget(self.has_break)
        self.break_time = QLineEdit(self.record.get("break_time", ""))
        self.break_time.setPlaceholderText("например, 13:00–14:00")
        break_row.addWidget(self.break_time, 1)
        rf.addRow("Перерыв:", break_row)

        check_row = QHBoxLayout()
        self.call_before = QCheckBox("Позвонить за 30 минут")
        self.call_before.setChecked(bool(self.record.get("call_before_30min", False)))
        check_row.addWidget(self.call_before)

        self.need_pass = QCheckBox("Нужен пропуск")
        self.need_pass.setChecked(bool(self.record.get("need_pass", False)))
        check_row.addWidget(self.need_pass)
        check_row.addStretch(1)
        rf.addRow("Особые условия:", check_row)

        self.comment = QTextEdit()
        self.comment.setPlainText(self.record.get("comment", ""))
        self.comment.setMaximumHeight(70)
        rf.addRow("Комментарий:", self.comment)

        layout.addWidget(recv)

        # ============ Состав ============
        items_group = QGroupBox("Состав отправки")
        il = QVBoxLayout(items_group)

        items_hint = QLabel(
            "Размеры: <b>Ш×Г×В, мм</b> (например, 810×625×143).  "
            "Вес — в кг.  "
            "При вводе модели из справочника размеры и вес подставляются автоматически."
        )
        items_hint.setStyleSheet("color: #666; font-size: 11px;")
        items_hint.setTextFormat(Qt.RichText)
        items_hint.setWordWrap(True)
        il.addWidget(items_hint)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels([
            "Модель", "Кол-во", "Размер, мм", "Вес 1 шт, кг", "Серийные номера"
        ])
        h = self.items_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.items_table.setMinimumHeight(180)
        self.items_table.itemChanged.connect(self._on_item_changed)
        il.addWidget(self.items_table)

        items_btn = QHBoxLayout()
        self.btn_add_item = QPushButton("➕ Добавить позицию")
        self.btn_add_item.clicked.connect(self.add_item_row)
        items_btn.addWidget(self.btn_add_item)

        self.btn_del_item = QPushButton("➖ Удалить позицию")
        self.btn_del_item.clicked.connect(self.del_item_row)
        items_btn.addWidget(self.btn_del_item)

        self.btn_from_order = QPushButton("📦 Из текущего заказа")
        self.btn_from_order.setToolTip(
            "Подставить состав, размеры и вес из расчёта в главном окне."
        )
        self.btn_from_order.clicked.connect(self.load_from_order)
        items_btn.addWidget(self.btn_from_order)

        items_btn.addStretch(1)
        il.addLayout(items_btn)

        layout.addWidget(items_group)

        # ============ Грузовые характеристики ============
        cargo = QGroupBox("Грузовые характеристики (итог по отправке)")
        cf = QFormLayout(cargo)

        cargo_hint = QLabel(
            "Можно ввести вручную или нажать <b>«Пересчитать из состава»</b> — "
            "тогда вес и объём посчитаются автоматически."
        )
        cargo_hint.setStyleSheet("color: #666; font-size: 11px;")
        cargo_hint.setTextFormat(Qt.RichText)
        cargo_hint.setWordWrap(True)
        cf.addRow("", cargo_hint)

        cargo_row = QHBoxLayout()

        self.cargo_weight = QLineEdit(
            str(self.record.get("cargo_weight_kg", "") or "")
        )
        self.cargo_weight.setPlaceholderText("0.0")
        cargo_row.addWidget(QLabel("Вес, кг:"))
        cargo_row.addWidget(self.cargo_weight)

        cargo_row.addSpacing(10)

        self.cargo_volume = QLineEdit(
            str(self.record.get("cargo_volume_m3", "") or "")
        )
        self.cargo_volume.setPlaceholderText("0.0")
        cargo_row.addWidget(QLabel("Объём, м³:"))
        cargo_row.addWidget(self.cargo_volume)

        cargo_row.addSpacing(10)

        self.cargo_bbox = QLineEdit(
            str(self.record.get("cargo_bbox_volume_m3", "") or "")
        )
        self.cargo_bbox.setPlaceholderText("0.0")
        cargo_row.addWidget(QLabel("Габаритный, м³:"))
        cargo_row.addWidget(self.cargo_bbox)

        cargo_row.addSpacing(10)

        self.cargo_pallets = QLineEdit(
            str(self.record.get("cargo_pallets", "") or "")
        )
        self.cargo_pallets.setPlaceholderText("0")
        cargo_row.addWidget(QLabel("Паллет, шт:"))
        cargo_row.addWidget(self.cargo_pallets)

        cargo_row.addStretch(1)
        cf.addRow("", cargo_row)

        recalc_row = QHBoxLayout()
        self.btn_recalc = QPushButton("🔄 Пересчитать из состава")
        self.btn_recalc.setStyleSheet(
            "QPushButton { padding: 6px 14px; font-weight: bold; "
            "background: #00838f; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #006064; }"
        )
        self.btn_recalc.setToolTip(
            "Пересчитать вес и объём коробок на основе позиций состава.\n"
            "Габаритный объём и паллеты остаются как есть."
        )
        self.btn_recalc.clicked.connect(self.recalc_cargo)
        recalc_row.addWidget(self.btn_recalc)
        recalc_row.addStretch(1)
        cf.addRow("", recalc_row)

        layout.addWidget(cargo)

        # ============ Внутренний учёт ============
        internal = QGroupBox("Внутренний учёт")
        inf = QFormLayout(internal)

        dates_row = QHBoxLayout()

        self.ship_date = QDateEdit()
        self.ship_date.setCalendarPopup(True)
        self.ship_date.setDisplayFormat("dd.MM.yyyy")
        self._set_date(self.ship_date, self.record.get("ship_date", ""))
        dates_row.addWidget(QLabel("Отправлено:"))
        dates_row.addWidget(self.ship_date)

        dates_row.addSpacing(20)

        self.planned_return = QDateEdit()
        self.planned_return.setCalendarPopup(True)
        self.planned_return.setDisplayFormat("dd.MM.yyyy")
        self.planned_return.setMinimumDate(QDate(2000, 1, 1))
        self.planned_return.setSpecialValueText("—")
        self._set_date(self.planned_return,
                       self.record.get("planned_return_date", ""),
                       allow_empty=True)
        dates_row.addWidget(QLabel("Планируемый возврат:"))
        dates_row.addWidget(self.planned_return)

        dates_row.addStretch(1)
        inf.addRow("Даты:", dates_row)

        self.actual_return = QLineEdit(
            self.record.get("actual_return_date", "") or "—"
        )
        self.actual_return.setReadOnly(True)
        self.actual_return.setStyleSheet("background: #eee; color: #555;")
        inf.addRow("Фактический возврат:", self.actual_return)

        self.shipped_by = QLineEdit(self.record.get("shipped_by", ""))
        inf.addRow("Кто отправил:", self.shipped_by)

        self.tracking = QLineEdit(self.record.get("tracking_number", ""))
        inf.addRow("Номер накладной:", self.tracking)

        self.cost = QLineEdit(str(self.record.get("delivery_cost", 0) or 0))
        inf.addRow("Стоимость доставки, ₽:", self.cost)

        layout.addWidget(internal)

        for it in self.record.get("items", []):
            self._add_item_row(
                it.get("model", ""),
                it.get("qty", 1),
                shp.format_dimensions(it.get("dims_mm")),
                it.get("weight_kg"),
                "; ".join(it.get("serials", []) or []),
            )

        # ============ Кнопки внизу ============
        bottom = QHBoxLayout()
        bottom.addStretch(1)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("💾 Сохранить")
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        self.btn_save.clicked.connect(self.on_save)
        bottom.addWidget(self.btn_save)

        outer.addLayout(bottom)

        self._on_entity_type_changed()
        self._on_break_toggled(self.has_break.isChecked())

    # ---------- вспомогательное ----------

    def _collect_devices_map(self) -> dict:
        main = None
        node = self.parent()
        while node is not None:
            if hasattr(node, "devices"):
                main = node
                break
            node = node.parent() if hasattr(node, "parent") else None
        if main is None:
            return {}
        try:
            return {d.get("name", "").strip().lower(): d
                    for d in main.devices if d.get("name")}
        except Exception:
            return {}

    def _set_date(self, widget: QDateEdit, text: str,
                  allow_empty: bool = False):
        if not text:
            if allow_empty:
                widget.setDate(QDate(2000, 1, 1))
            else:
                widget.setDate(QDate.currentDate())
            return
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                d = datetime.strptime(text, fmt).date()
                widget.setDate(QDate(d.year, d.month, d.day))
                return
            except ValueError:
                continue
        widget.setDate(QDate.currentDate())

    def _date_str(self, widget: QDateEdit, allow_empty: bool = False) -> str:
        d = widget.date()
        if allow_empty and d == QDate(2000, 1, 1):
            return ""
        return d.toString("yyyy-MM-dd")

    def _on_entity_type_changed(self):
        is_legal = self.entity_type.currentData() == "legal"
        self.inn.setEnabled(is_legal)
        if not is_legal:
            self.inn.setText("")

    def _on_break_toggled(self, checked):
        self.break_time.setEnabled(checked)

    # ---------- позиции ----------

    def _add_item_row(self, model="", qty=1, dims="", weight="", serials=""):
        row = self.items_table.rowCount()
        self.items_table.blockSignals(True)
        self.items_table.insertRow(row)

        self.items_table.setItem(row, self.COL_MODEL,
                                 QTableWidgetItem(str(model)))

        it_q = QTableWidgetItem(str(qty))
        it_q.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_QTY, it_q)

        self.items_table.setItem(row, self.COL_DIMS,
                                 QTableWidgetItem(str(dims or "")))

        w_text = ""
        if weight not in (None, ""):
            try:
                w_text = f"{float(weight):g}"
            except (TypeError, ValueError):
                w_text = str(weight)
        it_w = QTableWidgetItem(w_text)
        it_w.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.items_table.setItem(row, self.COL_WEIGHT, it_w)

        self.items_table.setItem(row, self.COL_SERIALS,
                                 QTableWidgetItem(serials))

        self.items_table.blockSignals(False)

    def add_item_row(self):
        row = self.items_table.rowCount()
        self._add_item_row("", 1, "", "", "")
        self.items_table.setCurrentCell(row, self.COL_MODEL)
        self.items_table.editItem(self.items_table.item(row, self.COL_MODEL))

    def del_item_row(self):
        cur = self.items_table.currentRow()
        if cur >= 0:
            self.items_table.removeRow(cur)

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != self.COL_MODEL:
            return
        model = item.text().strip()
        if not model:
            return
        dev = self.devices_map.get(model.lower())
        if not dev:
            return

        row = item.row()
        dims_cell = self.items_table.item(row, self.COL_DIMS)
        weight_cell = self.items_table.item(row, self.COL_WEIGHT)

        if dims_cell is not None and not dims_cell.text().strip():
            dims = dev.get("dims_mm") or []
            txt = shp.format_dimensions(dims)
            if txt:
                self.items_table.blockSignals(True)
                dims_cell.setText(txt)
                self.items_table.blockSignals(False)

        if weight_cell is not None and not weight_cell.text().strip():
            w = dev.get("weight_kg")
            if w is not None:
                try:
                    self.items_table.blockSignals(True)
                    weight_cell.setText(f"{float(w):g}")
                    self.items_table.blockSignals(False)
                except (TypeError, ValueError):
                    pass

    def load_from_order(self):
        main = None
        node = self.parent()
        while node is not None:
            if hasattr(node, "last_calc"):
                main = node
                break
            node = node.parent() if hasattr(node, "parent") else None

        calc = getattr(main, "last_calc", None) if main else None
        if not calc:
            QMessageBox.information(
                self, "Из текущего заказа",
                "В главном окне нет рассчитанного заказа.\n"
                "Сначала сделай расчёт укладки."
            )
            return

        models = calc.get("by_model", {})
        if not models:
            QMessageBox.information(
                self, "Из текущего заказа", "В заказе нет позиций."
            )
            return

        if self.items_table.rowCount() > 0:
            ans = QMessageBox.question(
                self, "Из текущего заказа",
                "В форме уже есть позиции. Заменить их составом из заказа?"
            )
            if ans != QMessageBox.Yes:
                return
            self.items_table.setRowCount(0)

        for name, d in models.items():
            dims = d.get("dims") or []
            weight = d.get("weight_kg")
            self._add_item_row(
                name,
                int(d.get("qty_ordered", 0)),
                shp.format_dimensions(dims),
                weight,
                "",
            )

        pallets = calc.get("pallets", [])
        weight_total = sum(float(p.get("weight_kg", 0)) for p in pallets)
        volume = sum(float(p.get("volume_m3", 0)) for p in pallets)
        bbox = sum(float(p.get("bbox_volume_m3", 0)) for p in pallets)

        self.cargo_weight.setText(f"{weight_total:.2f}")
        self.cargo_volume.setText(f"{volume:.4f}")
        self.cargo_bbox.setText(f"{bbox:.4f}")
        self.cargo_pallets.setText(str(len(pallets)))

    def recalc_cargo(self):
        items = self._collect_items()
        if not items:
            QMessageBox.information(
                self, "Пересчёт",
                "Состав пуст — нечего считать."
            )
            return

        weight = shp.calc_weight_from_items(items)
        volume = shp.calc_volume_from_items(items)

        self.cargo_weight.setText(f"{weight:.2f}")
        self.cargo_volume.setText(f"{volume:.4f}")

        QMessageBox.information(
            self, "Пересчёт выполнен",
            f"Вес коробок: {weight:.2f} кг\n"
            f"Объём коробок: {volume:.4f} м³\n\n"
            f"Габаритный объём и количество паллет не изменены — "
            f"проверь их отдельно."
        )

    def _collect_items(self) -> list:
        items = []
        for row in range(self.items_table.rowCount()):
            model_item = self.items_table.item(row, self.COL_MODEL)
            qty_item = self.items_table.item(row, self.COL_QTY)
            dims_item = self.items_table.item(row, self.COL_DIMS)
            weight_item = self.items_table.item(row, self.COL_WEIGHT)
            ser_item = self.items_table.item(row, self.COL_SERIALS)

            model = model_item.text().strip() if model_item else ""
            if not model:
                continue

            try:
                qty = int(qty_item.text()) if qty_item else 1
            except ValueError:
                qty = 1

            dims = shp.parse_dimensions(dims_item.text() if dims_item else "")

            weight = 0.0
            if weight_item:
                try:
                    weight = float(weight_item.text().replace(",", ".") or 0)
                except ValueError:
                    weight = 0.0

            serials_raw = ser_item.text().strip() if ser_item else ""
            serials = [
                s.strip() for s in serials_raw.replace(",", ";").split(";")
                if s.strip()
            ]

            items.append({
                "model": model,
                "qty": qty,
                "dims_mm": dims,
                "weight_kg": weight,
                "serials": serials,
            })
        return items

    # ---------- работа со справочником ----------

    def pick_contractor(self):
        from contractors_dialog import ContractorPickerDialog
        dlg = ContractorPickerDialog(self)
        if not dlg.exec():
            return
        c = dlg.get_selected()
        if not c:
            return

        typ = c.get("entity_type", "legal")
        self.entity_type.setCurrentIndex(0 if typ == "legal" else 1)
        self.entity_name.setText(c.get("entity_name", ""))
        self.inn.setText(c.get("inn", ""))
        self.address.setPlainText(c.get("address", ""))
        self.contact_person.setText(c.get("contact_person", ""))
        self.contact_phone.setText(c.get("contact_phone", ""))
        self.work_hours.setText(c.get("work_hours", ""))
        self.has_break.setChecked(bool(c.get("has_break", False)))
        self.break_time.setText(c.get("break_time", ""))
        self.call_before.setChecked(bool(c.get("call_before_30min", False)))
        self.need_pass.setChecked(bool(c.get("need_pass", False)))
        self.comment.setPlainText(c.get("comment", ""))

    def _autosave_contractor(self, rec: dict):
        """Автоматически сохраняет контрагента в справочник."""
        if not rec.get("entity_name", "").strip():
            return
        try:
            cnt.upsert_contractor({
                "entity_type": rec.get("entity_type", "legal"),
                "entity_name": rec.get("entity_name", ""),
                "inn": rec.get("inn", ""),
                "address": rec.get("address", ""),
                "contact_person": rec.get("contact_person", ""),
                "contact_phone": rec.get("contact_phone", ""),
                "work_hours": rec.get("work_hours", ""),
                "has_break": rec.get("has_break", False),
                "break_time": rec.get("break_time", ""),
                "call_before_30min": rec.get("call_before_30min", False),
                "need_pass": rec.get("need_pass", False),
                "comment": rec.get("comment", ""),
            })
        except Exception:
            pass

    # ---------- сохранение ----------

    def _collect(self) -> dict:
        rec = dict(self.record)
        rec["entity_type"] = self.entity_type.currentData()
        rec["entity_name"] = self.entity_name.text().strip()
        rec["inn"] = self.inn.text().strip()
        rec["address"] = self.address.toPlainText().strip()
        rec["contact_person"] = self.contact_person.text().strip()
        rec["contact_phone"] = self.contact_phone.text().strip()
        rec["work_hours"] = self.work_hours.text().strip()
        rec["has_break"] = self.has_break.isChecked()
        rec["break_time"] = self.break_time.text().strip()
        rec["call_before_30min"] = self.call_before.isChecked()
        rec["need_pass"] = self.need_pass.isChecked()
        rec["comment"] = self.comment.toPlainText().strip()

        rec["ship_date"] = self._date_str(self.ship_date)
        rec["planned_return_date"] = self._date_str(
            self.planned_return, allow_empty=True
        )
        rec["actual_return_date"] = self.record.get("actual_return_date", "")
        rec["shipped_by"] = self.shipped_by.text().strip()
        rec["tracking_number"] = self.tracking.text().strip()
        try:
            rec["delivery_cost"] = float(
                self.cost.text().replace(",", ".").strip() or 0
            )
        except ValueError:
            rec["delivery_cost"] = 0

        def _f(s):
            try:
                return float((s or "").replace(",", ".").strip() or 0)
            except ValueError:
                return 0.0

        def _i(s):
            try:
                return int((s or "").strip() or 0)
            except ValueError:
                return 0

        rec["cargo_weight_kg"] = _f(self.cargo_weight.text())
        rec["cargo_volume_m3"] = _f(self.cargo_volume.text())
        rec["cargo_bbox_volume_m3"] = _f(self.cargo_bbox.text())
        rec["cargo_pallets"] = _i(self.cargo_pallets.text())

        rec["items"] = self._collect_items()
        return rec

    def _validate(self, rec: dict) -> list:
        warnings = []
        if not rec["address"]:
            warnings.append("• не указан адрес доставки")
        if not rec["entity_name"]:
            warnings.append("• не указано наименование/ФИО")
        if rec["entity_type"] == "legal" and not rec["inn"]:
            warnings.append("• не указан ИНН (для юр. лица)")
        if not rec["contact_person"]:
            warnings.append("• не указано контактное лицо")
        if not rec["contact_phone"]:
            warnings.append("• не указан телефон")
        if not rec["items"]:
            warnings.append("• не добавлены позиции состава")
        for it in rec["items"]:
            if it["qty"] > 1 and len(it["serials"]) != it["qty"]:
                warnings.append(
                    f"• «{it['model']}»: указано серийников "
                    f"{len(it['serials'])}, а количество {it['qty']}"
                )
        return warnings

    def on_save(self):
        rec = self._collect()
        warnings = self._validate(rec)

        if warnings:
            text = (
                "Не все обязательные поля заполнены:\n\n"
                + "\n".join(warnings)
                + "\n\nПродолжить сохранение?"
            )
            ans = QMessageBox.warning(
                self, "Проверка данных", text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return

        # автосохранение контрагента в справочник
        self._autosave_contractor(rec)

        if self.is_new:
            shp.add_shipment(rec)
        else:
            shp.update_shipment(rec)

        self.saved_record = rec
        self.accept()

    def get_record(self) -> dict:
        return getattr(self, "saved_record", self.record)