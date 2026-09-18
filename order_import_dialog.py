"""
Диалог импорта заказа из Excel.
Показывает распознанные позиции, позволяет править кол-во/паллету,
подсвечивает отсутствующие в справочнике модели.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont


class OrderImportDialog(QDialog):
    def __init__(self, items, known_models, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт заказа из Excel")
        self.resize(950, 620)

        self.known_models = set(known_models)
        self.known_lower = {m.lower(): m for m in known_models}

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            f"Распознано позиций: <b>{len(items)}</b>. "
            "Кол-во и № паллеты можно править прямо в таблице. "
            "Красным — модели, которых нет в справочнике."
        ))

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "✓", "Модель", "Кол-во", "Паллета №", "Статус"
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )

        for it in items:
            self._add_row(it["name"], it["qty"], it["pallet_group"])

        layout.addWidget(self.table, 1)

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

        self.btn_all.clicked.connect(self._check_all)
        self.btn_none.clicked.connect(self._uncheck_all)
        self.btn_known.clicked.connect(self._check_known)
        self.btn_add.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _add_row(self, name, qty, pallet):
        row = self.table.rowCount()
        self.table.insertRow(row)

        resolved = self._resolve(name)

        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if resolved else Qt.Unchecked)
        self.table.setItem(row, 0, chk)

        self.table.setItem(row, 1, QTableWidgetItem(name))

        it_q = QTableWidgetItem(str(qty))
        it_q.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 2, it_q)

        it_p = QTableWidgetItem(str(pallet))
        it_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 3, it_p)

        if resolved:
            it_s = QTableWidgetItem("✓ известна")
            it_s.setForeground(QBrush(QColor(0, 130, 0)))
        else:
            it_s = QTableWidgetItem("⚠ НЕТ В СПРАВОЧНИКЕ")
            it_s.setForeground(QBrush(QColor(200, 0, 0)))
            f = QFont()
            f.setBold(True)
            it_s.setFont(f)
            for col in range(5):
                c = self.table.item(row, col)
                if c:
                    c.setBackground(QBrush(QColor(255, 235, 235)))
        self.table.setItem(row, 4, it_s)

    def _resolve(self, name):
        if name in self.known_models:
            return name
        return self.known_lower.get(name.lower())

    def _check_all(self):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Checked)

    def _uncheck_all(self):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Unchecked)

    def _check_known(self):
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 1).text()
            state = Qt.Checked if self._resolve(name) else Qt.Unchecked
            self.table.item(r, 0).setCheckState(state)

    def get_selected(self):
        """[(имя_в_справочнике, qty, pallet_group)] — только известные."""
        result = []
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() != Qt.Checked:
                continue
            name = self.table.item(r, 1).text()
            resolved = self._resolve(name)
            if not resolved:
                continue
            try:
                qty = int(self.table.item(r, 2).text())
                pallet = int(self.table.item(r, 3).text())
            except (ValueError, AttributeError):
                continue
            if qty <= 0 or pallet <= 0:
                continue
            result.append((resolved, qty, pallet))
        return result

    def get_unknown_checked(self):
        result = []
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() != Qt.Checked:
                continue
            name = self.table.item(r, 1).text()
            if not self._resolve(name):
                result.append(name)
        return result