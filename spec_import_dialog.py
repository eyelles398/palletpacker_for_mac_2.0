"""
Диалог импорта спецификации.
Показывает распознанные позиции, подсвечивает модели, отсутствующие
в справочнике, позволяет отметить галочками что добавлять.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QSpinBox, QGroupBox,
    QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont


class SpecImportDialog(QDialog):
    def __init__(self, spec_data, known_models, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт спецификации из Excel")
        self.resize(950, 650)
        self.spec_data = spec_data
        self.known_models = set(known_models)
        self.known_lower = {m.lower(): m for m in known_models}

        layout = QVBoxLayout(self)

        # --- Информация ---
        info_group = QGroupBox("Информация")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(
            f"<b>Заказчик:</b> {spec_data.get('customer') or '—'}"
        ))
        info_layout.addWidget(QLabel(
            f"<b>Номер спецификации:</b> {spec_data.get('spec_number') or '—'}"
            f"&nbsp;&nbsp;&nbsp;&nbsp;"
            f"<b>Дата:</b> {spec_data.get('date') or '—'}"
        ))
        info_layout.addWidget(QLabel(
            f"<b>Пропущено:</b> сертификатов — "
            f"{spec_data.get('skipped_certs', 0)}, "
            f"строк-разделителей — {spec_data.get('skipped_sections', 0)}"
        ))
        layout.addWidget(info_group)

        # --- Таблица ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "✓", "Модель", "Кол-во", "Статус"
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        for it in spec_data.get("items", []):
            self._add_row(it["model"], it["qty"])

        layout.addWidget(self.table, 1)

        # --- Кнопки ---
        ctrl = QHBoxLayout()
        self.btn_all = QPushButton("✓ Все")
        self.btn_none = QPushButton("Снять все")
        self.btn_known = QPushButton("Только известные")
        ctrl.addWidget(self.btn_all)
        ctrl.addWidget(self.btn_none)
        ctrl.addWidget(self.btn_known)
        ctrl.addStretch(1)

        self.btn_add = QPushButton("➕ Добавить в заказ")
        self.btn_add.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "font-weight: bold; padding: 8px 16px; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        self.btn_cancel = QPushButton("Отмена")
        ctrl.addWidget(self.btn_cancel)
        ctrl.addWidget(self.btn_add)
        layout.addLayout(ctrl)

        # --- Паллета + подсказка ---
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Паллета №:"))
        self.pallet_spin = QSpinBox()
        self.pallet_spin.setRange(1, 999)
        self.pallet_spin.setValue(1)
        bottom.addWidget(self.pallet_spin)
        bottom.addStretch(1)
        hint = QLabel(
            "⚠ Красным — модели, которых нет в справочнике. "
            "Они будут пропущены при добавлении."
        )
        hint.setStyleSheet("color: #b71c1c; font-size: 11px;")
        bottom.addWidget(hint)
        layout.addLayout(bottom)

        self.btn_all.clicked.connect(self.check_all)
        self.btn_none.clicked.connect(self.uncheck_all)
        self.btn_known.clicked.connect(self.check_known)
        self.btn_add.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _add_row(self, model, qty):
        row = self.table.rowCount()
        self.table.insertRow(row)

        is_known = self._resolve_model(model) is not None

        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if is_known else Qt.Unchecked)
        self.table.setItem(row, 0, chk)

        it_m = QTableWidgetItem(model)
        self.table.setItem(row, 1, it_m)

        it_q = QTableWidgetItem(str(qty))
        it_q.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 2, it_q)

        if is_known:
            it_s = QTableWidgetItem("✓ известна")
            it_s.setForeground(QBrush(QColor(0, 130, 0)))
        else:
            it_s = QTableWidgetItem("⚠ НЕТ В СПРАВОЧНИКЕ")
            it_s.setForeground(QBrush(QColor(200, 0, 0)))
            f = QFont()
            f.setBold(True)
            it_s.setFont(f)
            for col in range(4):
                c = self.table.item(row, col)
                if c:
                    c.setBackground(QBrush(QColor(255, 235, 235)))
        self.table.setItem(row, 3, it_s)

    def _resolve_model(self, model):
        """Возвращает точное имя из справочника, если найдено."""
        if model in self.known_models:
            return model
        return self.known_lower.get(model.lower())

    def check_all(self):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Checked)

    def uncheck_all(self):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Unchecked)

    def check_known(self):
        for r in range(self.table.rowCount()):
            model = self.table.item(r, 1).text()
            state = Qt.Checked if self._resolve_model(model) else Qt.Unchecked
            self.table.item(r, 0).setCheckState(state)

    def get_selected(self):
        """Список [(имя_в_справочнике, qty)] — только известные."""
        result = []
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() != Qt.Checked:
                continue
            model = self.table.item(r, 1).text()
            qty = int(self.table.item(r, 2).text())
            resolved = self._resolve_model(model)
            if resolved:
                result.append((resolved, qty))
        return result

    def get_unknown_checked(self):
        """Список отмеченных, но неизвестных моделей."""
        result = []
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() != Qt.Checked:
                continue
            model = self.table.item(r, 1).text()
            if not self._resolve_model(model):
                result.append(model)
        return result

    def get_pallet_no(self):
        return self.pallet_spin.value()