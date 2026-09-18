import sys
import json
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QGroupBox, QFormLayout, QDoubleSpinBox, QHeaderView, QMessageBox,
    QComboBox, QSpinBox, QLineEdit, QFileDialog, QGridLayout,
    QSplitter, QTextEdit, QCheckBox, QAbstractItemView,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QImage, QBrush, QColor, QIcon, QGuiApplication, QPalette, QFont
)

import packer3d
import exporter
import spec_parser
import settings
import order_import
import order_export
import mailer
import platform_utils
import shipments
from spec_import_dialog import SpecImportDialog
from order_import_dialog import OrderImportDialog
from device_editor import DeviceEditorDialog
from email_dialog import EmailDialog, prepare_attachments


APP_DIR = platform_utils.app_dir()
RESOURCE_DIR = platform_utils.resource_dir()
DEVICES_FILE = APP_DIR / "devices.json"
ICON_FILE = APP_DIR / "icon.ico"
PALLET_THICKNESS_MM = 150


def _apply_light_palette(app: QApplication):
    app.setStyle("Fusion")

    p = QPalette()
    p.setColor(QPalette.Window,          QColor(240, 240, 240))
    p.setColor(QPalette.WindowText,      QColor(20, 20, 20))
    p.setColor(QPalette.Base,            QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase,   QColor(245, 245, 245))
    p.setColor(QPalette.Text,            QColor(20, 20, 20))
    p.setColor(QPalette.Button,          QColor(240, 240, 240))
    p.setColor(QPalette.ButtonText,      QColor(20, 20, 20))
    p.setColor(QPalette.BrightText,      QColor(200, 0, 0))
    p.setColor(QPalette.Link,            QColor(25, 118, 210))
    p.setColor(QPalette.Highlight,       QColor(46, 125, 50))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ToolTipBase,     QColor(255, 255, 220))
    p.setColor(QPalette.ToolTipText,     QColor(20, 20, 20))
    p.setColor(QPalette.PlaceholderText, QColor(140, 140, 140))

    p.setColor(QPalette.Disabled, QPalette.Text,       QColor(150, 150, 150))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(150, 150, 150))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(150, 150, 150))

    app.setPalette(p)


def pallet_label(group: int, attempt: int) -> str:
    if attempt <= 1:
        return f"№{group}"
    return f"№{group} (+{attempt - 1})"


class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._title = title

        self.toggle_button = QPushButton("▼  " + title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setStyleSheet(
            "QPushButton { text-align: left; padding: 6px 8px; "
            "font-weight: bold; border: 1px solid #bbb; "
            "border-radius: 4px; background: #eef4ee; color: #222; }"
            "QPushButton:hover { background: #dceadc; }"
        )

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content)

        self.toggle_button.toggled.connect(self._on_toggle)

    def _on_toggle(self, checked):
        self.content.setVisible(checked)
        self.toggle_button.setText(
            ("▼  " if checked else "▶  ") + self._title
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Расчёт укладки коробок на паллету")

        self.setMinimumSize(700, 420)

        platform_utils.ensure_user_files()

        if ICON_FILE.exists():
            try:
                self.setWindowIcon(QIcon(str(ICON_FILE)))
            except Exception:
                pass

        self.devices = self.load_devices()
        self.last_calc = None
        self._settings = settings.load_settings()

        self.pallet_overrides = {}
        self.side_first_layer_groups = set()
        self._updating_pallet_settings = False

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(main_splitter)

        # ======================= ЛЕВАЯ ПАНЕЛЬ =======================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self.pallet_box = CollapsibleBox("Параметры паллеты (мм)")
        pallet_form = QFormLayout()
        pallet_form.setContentsMargins(0, 0, 0, 0)

        self.pallet_length = QDoubleSpinBox()
        self.pallet_length.setRange(1, 5000); self.pallet_length.setValue(1200)
        self.pallet_length.setSuffix(" мм")

        self.pallet_width = QDoubleSpinBox()
        self.pallet_width.setRange(1, 5000); self.pallet_width.setValue(800)
        self.pallet_width.setSuffix(" мм")

        self.pallet_height = QDoubleSpinBox()
        self.pallet_height.setRange(1, 5000); self.pallet_height.setValue(1500)
        self.pallet_height.setSuffix(" мм")

        self.pallet_max_weight = QDoubleSpinBox()
        self.pallet_max_weight.setRange(1, 5000); self.pallet_max_weight.setValue(1000)
        self.pallet_max_weight.setSuffix(" кг")

        self.pallet_tare_weight = QDoubleSpinBox()
        self.pallet_tare_weight.setRange(0, 500)
        self.pallet_tare_weight.setValue(25)
        self.pallet_tare_weight.setSuffix(" кг")

        self.max_overhang_spin = QDoubleSpinBox()
        self.max_overhang_spin.setRange(0, 1000)
        self.max_overhang_spin.setValue(0)
        self.max_overhang_spin.setSuffix(" мм")
        self.max_overhang_spin.setToolTip(
            "На сколько мм коробка может свисать за границу своих опор.\n"
            "0 = запрещено (коробка должна полностью опираться)."
        )

        pallet_form.addRow("Длина:", self.pallet_length)
        pallet_form.addRow("Ширина:", self.pallet_width)
        pallet_form.addRow("Макс. высота стопки:", self.pallet_height)
        pallet_form.addRow("Макс. вес:", self.pallet_max_weight)
        pallet_form.addRow("Вес тары:", self.pallet_tare_weight)
        pallet_form.addRow("Макс. свес над опорами:", self.max_overhang_spin)
        self.pallet_box.content_layout.addLayout(pallet_form)
        left_layout.addWidget(self.pallet_box, 0)

        pick_group = QGroupBox("Добавить в заказ")
        pick_layout = QVBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Поиск по названию...")
        pick_layout.addWidget(self.search_edit)

        self.device_combo = QComboBox()
        pick_layout.addWidget(self.device_combo)

        self.device_info = QLabel("—")
        self.device_info.setStyleSheet("color: #555; font-size: 11px;")
        self.device_info.setWordWrap(True)
        pick_layout.addWidget(self.device_info)

        row = QHBoxLayout()
        row.addWidget(QLabel("Кол-во:"))
        self.qty_spin = QSpinBox(); self.qty_spin.setRange(1, 10000); self.qty_spin.setValue(1)
        row.addWidget(self.qty_spin)

        row.addWidget(QLabel("Паллета №:"))
        self.add_pallet_spin = QSpinBox()
        self.add_pallet_spin.setRange(1, 999)
        self.add_pallet_spin.setValue(1)
        row.addWidget(self.add_pallet_spin)

        self.btn_add_to_order = QPushButton("➕ Добавить")
        row.addWidget(self.btn_add_to_order)
        pick_layout.addLayout(row)

        self.btn_edit_devices = QPushButton("📝 Редактировать справочник коробок")
        self.btn_edit_devices.setStyleSheet("QPushButton { padding: 6px; }")
        pick_layout.addWidget(self.btn_edit_devices)

        io_row2 = QHBoxLayout()
        io_row2.setSpacing(4)

        _btn_style = (
            "QPushButton {{ padding: 6px 8px; font-size: 11px; "
            "font-weight: bold; color: white; background-color: {bg}; "
            "border-radius: 3px; }}"
            "QPushButton:hover {{ background-color: {hover}; }}"
        )

        self.btn_load_spec = QPushButton("📥 Спецификация")
        self.btn_load_spec.setStyleSheet(_btn_style.format(
            bg="#1976d2", hover="#1565c0"
        ))
        self.btn_load_spec.setToolTip(
            "Загрузить спецификацию оборудования из Excel."
        )

        self.btn_import_order = QPushButton("📂 Импорт заказа")
        self.btn_import_order.setStyleSheet(_btn_style.format(
            bg="#7b1fa2", hover="#6a1b9a"
        ))
        self.btn_import_order.setToolTip(
            "Excel, где колонки: A — модель, B — кол-во, C — паллета №."
        )

        self.btn_export_order = QPushButton("📤 Экспорт заказа")
        self.btn_export_order.setStyleSheet(_btn_style.format(
            bg="#00838f", hover="#006064"
        ))
        self.btn_export_order.setToolTip(
            "Сохранить текущий заказ в Excel."
        )

        io_row2.addWidget(self.btn_load_spec, 1)
        io_row2.addWidget(self.btn_import_order, 1)
        io_row2.addWidget(self.btn_export_order, 1)
        pick_layout.addLayout(io_row2)

        pick_group.setLayout(pick_layout)
        left_layout.addWidget(pick_group, 0)

        order_group = QGroupBox("Заказ")
        order_layout = QVBoxLayout()

        self.order_table = QTableWidget()
        self.order_table.setColumnCount(6)
        self.order_table.setHorizontalHeaderLabels([
            "Название", "Ш×Г×В (мм)", "Вес (кг)", "Кол-во", "Тип", "Паллета №"
        ])
        self.order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.order_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.order_table.setMinimumHeight(90)
        order_layout.addWidget(self.order_table)

        btn_row = QHBoxLayout()
        self.btn_del_order = QPushButton("➖ Удалить строку")
        self.btn_clear_order = QPushButton("🗑 Очистить заказ")
        btn_row.addWidget(self.btn_del_order)
        btn_row.addWidget(self.btn_clear_order)
        order_layout.addLayout(btn_row)

        io_row = QHBoxLayout()
        self.btn_save_order = QPushButton("💾 Сохранить заказ (JSON)")
        self.btn_load_order = QPushButton("📂 Загрузить заказ (JSON)")
        self.btn_save_order.setStyleSheet("QPushButton { padding: 6px; }")
        self.btn_load_order.setStyleSheet("QPushButton { padding: 6px; }")
        io_row.addWidget(self.btn_save_order)
        io_row.addWidget(self.btn_load_order)
        order_layout.addLayout(io_row)

        order_group.setLayout(order_layout)
        left_layout.addWidget(order_group, 1)

        pallets_settings_group = QGroupBox("Настройки паллет (по номерам)")
        ps_layout = QVBoxLayout()

        self.cb_uniform_pallets = QCheckBox(
            "Паллеты одинаковые (использовать общие параметры)"
        )
        self.cb_uniform_pallets.setChecked(True)
        self.cb_uniform_pallets.setToolTip(
            "Если снять — в таблице ниже можно задать свои размеры,\n"
            "макс. вес и высоту для каждой паллеты отдельно."
        )
        ps_layout.addWidget(self.cb_uniform_pallets)

        self.pallet_settings_table = QTableWidget()
        self.pallet_settings_table.setColumnCount(7)
        self.pallet_settings_table.setHorizontalHeaderLabels([
            "№", "Кор.", "Д, мм", "Ш, мм", "В, мм", "Вес, кг",
            "1-й слой боком?"
        ])
        h = self.pallet_settings_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for c in (2, 3, 4, 5):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.Stretch)
        self.pallet_settings_table.verticalHeader().setVisible(False)
        self.pallet_settings_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.pallet_settings_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.pallet_settings_table.setMinimumHeight(70)
        ps_layout.addWidget(self.pallet_settings_table)

        ps_btn_row = QHBoxLayout()
        self.btn_refresh_pallets = QPushButton("🔄 Обновить список")
        self.btn_refresh_pallets.setStyleSheet("QPushButton { padding: 4px; }")
        ps_btn_row.addWidget(self.btn_refresh_pallets)
        ps_btn_row.addStretch(1)
        ps_layout.addLayout(ps_btn_row)

        pallets_settings_group.setLayout(ps_layout)
        left_layout.addWidget(pallets_settings_group, 1)

        checks_group = QGroupBox("Опции")
        checks_grid = QGridLayout()
        checks_grid.setContentsMargins(6, 6, 6, 6)
        checks_grid.setHorizontalSpacing(12)
        checks_grid.setVerticalSpacing(4)

        self.cb_show_labels = QCheckBox("Показывать номера паллет в 3D")
        self.cb_show_labels.setChecked(True)

        self.cb_use_tare = QCheckBox("Учитывать вес тары в общем весе")
        self.cb_use_tare.setChecked(False)

        self.cb_full_support = QCheckBox("Опора по всему периметру")
        self.cb_full_support.setChecked(False)

        self.cb_side_on_floor = QCheckBox(
            "Разрешать боковую укладку коробок по всей паллете"
        )
        self.cb_side_on_floor.setChecked(False)
        self.cb_side_on_floor.setToolTip(
            "Если СНЯТО (по умолчанию):\n"
            "  • все коробки укладываются преимущественно плашмя\n"
            "  • боком — только если плашмя никак не влезает\n\n"
            "Если ВКЛЮЧЕНО:\n"
            "  • алгоритм сам выбирает ориентацию каждой коробки\n"
            "  • может уложить боком любую, если так эффективнее\n"
            "  • слои получаются разной высоты — иногда это плюс\n"
        )

        self.cb_group_by_model = QCheckBox("Группировать коробки по моделям")
        self.cb_group_by_model.setChecked(False)

        self.cb_post_optimize = QCheckBox(
            "Оптимизировать свободное место после укладки"
        )
        self.cb_post_optimize.setChecked(False)
        self.cb_post_optimize.setToolTip(
            "После обычной укладки программа ещё раз проходит по свободным\n"
            "местам и пытается втиснуть туда оставшиеся МЕЛКИЕ коробки\n"
            "(до 450 мм по большей стороне).\n\n"
            "Работает недолго (до 2 секунд на паллету)."
        )

        self.cb_prefer_tight = QCheckBox("Прижимать коробки к соседним")
        self.cb_prefer_tight.setChecked(False)
        self.cb_prefer_tight.setToolTip(
            "При укладке каждой коробки алгоритм выбирает позицию,\n"
            "где больше площадь соприкосновения с уже уложенными.\n\n"
            "Результат: коробки кучкуются, а не разбегаются по углам.\n"
            "Габаритный объём обычно уменьшается на 5–15%."
        )

        self.cb_repack = QCheckBox("Переупаковка в конце")
        self.cb_repack.setChecked(False)
        self.cb_repack.setToolTip(
            "После укладки программа пробует переложить все коробки\n"
            "несколько раз с разными приоритетами и оставляет тот\n"
            "вариант, где габаритный объём меньше.\n\n"
            "Работает в 2–3 раза дольше. Обычно даёт −10–20% объёма."
        )

        checks_grid.addWidget(self.cb_show_labels,   0, 0)
        checks_grid.addWidget(self.cb_use_tare,      0, 1)
        checks_grid.addWidget(self.cb_full_support,  1, 0)
        checks_grid.addWidget(self.cb_side_on_floor, 1, 1)
        checks_grid.addWidget(self.cb_group_by_model, 2, 0)
        checks_grid.addWidget(self.cb_post_optimize,  2, 1)
        checks_grid.addWidget(self.cb_prefer_tight,   3, 0)
        checks_grid.addWidget(self.cb_repack,         3, 1)

        checks_group.setLayout(checks_grid)
        left_layout.addWidget(checks_group, 0)

        self.btn_calc = QPushButton("📦 Рассчитать укладку")
        self.btn_calc.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "font-weight: bold; padding: 10px; font-size: 14px; }"
            "QPushButton:hover { background-color: #388e3c; }"
        )
        left_layout.addWidget(self.btn_calc, 0)

        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("Экспорт:"))
        self.btn_export_excel = QPushButton("📊 Excel")
        self.btn_export_pdf = QPushButton("📄 PDF")
        self.btn_screenshot = QPushButton("📸 Скриншот 3D")
        for b in (self.btn_export_excel, self.btn_export_pdf,
                  self.btn_screenshot):
            b.setStyleSheet("QPushButton { padding: 6px 10px; }")
        export_row.addWidget(self.btn_export_excel)
        export_row.addWidget(self.btn_export_pdf)
        export_row.addWidget(self.btn_screenshot)

        self.btn_send_email = None
        if platform_utils.is_windows():
            self.btn_send_email = QPushButton("📧 Outlook")
            self.btn_send_email.setStyleSheet(
                "QPushButton { padding: 6px 10px; font-weight: bold; "
                "background: #1976d2; color: white; border-radius: 3px; }"
                "QPushButton:hover { background: #1565c0; }"
            )
            self.btn_send_email.setToolTip(
                "Открыть новое письмо в классическом Outlook\n"
                "с вложениями PDF/Excel."
            )
            export_row.addWidget(self.btn_send_email)

        self.btn_shipments = QPushButton("📦 Отгрузки")
        self.btn_shipments.setStyleSheet(
            "QPushButton { padding: 6px 10px; font-weight: bold; "
            "background: #7b1fa2; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #6a1b9a; }"
        )
        self.btn_shipments.setToolTip(
            "Учёт отправок демо-оборудования: список, поиск,\n"
            "статусы, возвраты, PDF для транспортной компании."
        )
        export_row.addWidget(self.btn_shipments)

        export_row.addStretch(1)
        left_layout.addLayout(export_row)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_widget)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(380)

        # ======================= ПРАВАЯ ПАНЕЛЬ =======================
        right_splitter = QSplitter(Qt.Vertical)

        results_group = QGroupBox("Результаты расчёта")
        results_layout = QVBoxLayout(results_group)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setStyleSheet(
            "QTextEdit { font-family: Consolas, Menlo, monospace; "
            "font-size: 12px; background: #fafafa; color: #1e1e1e; }"
        )
        self.results_text.setPlainText("Здесь появятся результаты...")
        self.results_text.setMinimumHeight(80)
        results_layout.addWidget(self.results_text)
        right_splitter.addWidget(results_group)

        viz_group = QGroupBox("Визуализация укладки (3D)")
        viz_layout = QVBoxLayout(viz_group)
        self.viewer = packer3d.Viewer3D()
        self.viewer.setMinimumHeight(120)
        viz_layout.addWidget(self.viewer, 1)

        self.legend_label = QLabel("")
        self.legend_label.setTextFormat(Qt.RichText)
        self.legend_label.setStyleSheet("font-size: 11px; color: #1e1e1e;")
        self.legend_label.setWordWrap(True)
        viz_layout.addWidget(self.legend_label)

        hint = QLabel(
            "🖱 ЛКМ — вращение, ПКМ — сдвиг, колесо — зум.  "
            "Оранжевый контур = габаритный объём паллеты."
        )
        hint.setStyleSheet("color: #888; font-size: 10px;")
        viz_layout.addWidget(hint)
        right_splitter.addWidget(viz_group)

        right_splitter.setSizes([250, 600])
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 3)

        main_splitter.addWidget(left_scroll)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([480, 920])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)

        self.main_splitter = main_splitter
        self.right_splitter = right_splitter

        # ======================= СИГНАЛЫ =======================
        self.search_edit.textChanged.connect(self.filter_devices)
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        self.btn_add_to_order.clicked.connect(self.add_to_order)
        self.btn_del_order.clicked.connect(self.delete_order_row)
        self.btn_clear_order.clicked.connect(self.clear_order)
        self.btn_calc.clicked.connect(self.calculate)
        self.btn_edit_devices.clicked.connect(self.open_device_editor)
        self.btn_load_spec.clicked.connect(self.load_specification)
        self.btn_import_order.clicked.connect(self.import_order_from_excel)
        self.btn_export_order.clicked.connect(self.export_order_to_excel)
        self.btn_export_excel.clicked.connect(self.export_excel)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.btn_screenshot.clicked.connect(self.screenshot_3d)
        if self.btn_send_email is not None:
            self.btn_send_email.clicked.connect(self.send_email)
        self.btn_shipments.clicked.connect(self.open_shipments)
        self.btn_save_order.clicked.connect(self.save_order)
        self.btn_load_order.clicked.connect(self.load_order)
        self.cb_show_labels.toggled.connect(self.on_toggle_labels)
        self.btn_refresh_pallets.clicked.connect(self.refresh_pallet_settings)
        self.pallet_settings_table.itemChanged.connect(
            self.on_pallet_settings_changed
        )
        self.pallet_settings_table.cellClicked.connect(
            self.on_pallet_settings_clicked
        )
        self.cb_uniform_pallets.toggled.connect(self.refresh_pallet_settings)

        for sb in (self.pallet_length, self.pallet_width,
                   self.pallet_height, self.pallet_max_weight):
            sb.valueChanged.connect(self._on_global_pallet_changed)

        self.refresh_device_list()
        self.refresh_pallet_settings()
        self._apply_settings()
        self._refresh_overdue_banner()

    # ======================= Настройки окна =======================
    def _apply_settings(self):
        s = self._settings or {}

        sp = s.get("splitters", {}) or {}
        main_sz = sp.get("main")
        if isinstance(main_sz, list) and len(main_sz) == 2:
            try:
                self.main_splitter.setSizes([int(v) for v in main_sz])
            except Exception:
                pass
        right_sz = sp.get("right")
        if isinstance(right_sz, list) and len(right_sz) == 2:
            try:
                self.right_splitter.setSizes([int(v) for v in right_sz])
            except Exception:
                pass

        pal = s.get("pallet", {}) or {}
        self.pallet_length.setValue(float(pal.get("L", 1200)))
        self.pallet_width.setValue(float(pal.get("W", 800)))
        self.pallet_height.setValue(float(pal.get("H", 1500)))
        self.pallet_max_weight.setValue(float(pal.get("max_weight", 1000)))
        self.pallet_tare_weight.setValue(float(pal.get("tare_weight", 25)))
        self.max_overhang_spin.setValue(float(pal.get("max_overhang_mm", 0)))

        fl = s.get("flags", {}) or {}
        self.cb_use_tare.setChecked(bool(fl.get("use_tare", False)))
        self.cb_full_support.setChecked(bool(fl.get("full_support", False)))
        self.cb_side_on_floor.setChecked(bool(fl.get("side_on_floor", False)))
        self.cb_group_by_model.setChecked(bool(fl.get("group_by_model", False)))
        self.cb_show_labels.setChecked(bool(fl.get("show_labels", True)))
        self.cb_post_optimize.setChecked(
            bool(fl.get("post_optimize", False))
        )
        self.cb_prefer_tight.setChecked(
            bool(fl.get("prefer_tight", False))
        )
        self.cb_repack.setChecked(
            bool(fl.get("repack", False))
        )

    def _apply_window_geometry(self):
        s = self._settings or {}
        win = s.get("window", {}) or {}
        w = int(win.get("width") or 1400)
        h = int(win.get("height") or 850)

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(w, h)
            return

        g = screen.availableGeometry()
        w = min(w, max(g.width() - 40, 500))
        h = min(h, max(g.height() - 80, 400))
        w = max(w, self.minimumWidth())
        h = max(h, self.minimumHeight())

        cx = g.left() + (g.width() - w) // 2
        cy = g.top() + (g.height() - h) // 2
        self.setGeometry(cx, cy, w, h)

    def _collect_settings(self) -> dict:
        geo = self.geometry()
        return {
            "window": {
                "width": geo.width(),
                "height": geo.height(),
            },
            "splitters": {
                "main": list(self.main_splitter.sizes()),
                "right": list(self.right_splitter.sizes()),
            },
            "pallet": {
                "L": self.pallet_length.value(),
                "W": self.pallet_width.value(),
                "H": self.pallet_height.value(),
                "max_weight": self.pallet_max_weight.value(),
                "tare_weight": self.pallet_tare_weight.value(),
                "max_overhang_mm": self.max_overhang_spin.value(),
            },
            "flags": {
                "use_tare": self.cb_use_tare.isChecked(),
                "full_support": self.cb_full_support.isChecked(),
                "side_on_floor": self.cb_side_on_floor.isChecked(),
                "group_by_model": self.cb_group_by_model.isChecked(),
                "show_labels": self.cb_show_labels.isChecked(),
                "post_optimize": self.cb_post_optimize.isChecked(),
                "prefer_tight": self.cb_prefer_tight.isChecked(),
                "repack": self.cb_repack.isChecked(),
            },
            "last_dir": (self._settings or {}).get("last_dir", ""),
        }

    def closeEvent(self, event):
        try:
            settings.save_settings(self._collect_settings())
        except Exception:
            pass
        super().closeEvent(event)

    # ======================= Справочник =======================
    def load_devices(self):
        if not DEVICES_FILE.exists():
            QMessageBox.critical(
                self, "Ошибка",
                f"Файл {DEVICES_FILE.name} не найден.\n\n"
                f"Ожидаемое расположение:\n{DEVICES_FILE}"
            )
            sys.exit(1)
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def open_device_editor(self):
        dlg = DeviceEditorDialog(self)
        if dlg.exec():
            self.devices = self.load_devices()
            self.refresh_device_list(self.search_edit.text())

    def refresh_device_list(self, filter_text=""):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        ft = filter_text.lower().strip()
        for d in self.devices:
            if ft and ft not in d["name"].lower():
                continue
            label = d["name"]
            if d.get("section"):
                label += f"  [{d['section'][:40]}]"
            self.device_combo.addItem(label, userData=d)
        self.device_combo.blockSignals(False)
        self.update_device_info()

    def filter_devices(self, text):
        self.refresh_device_list(text)

    def on_device_changed(self):
        self.qty_spin.setValue(1)
        self.update_device_info()

    def update_device_info(self):
        d = self.device_combo.currentData()
        if not d:
            self.device_info.setText("—"); return
        dims = d.get("dims_mm")
        dims_str = "×".join(str(int(x)) for x in dims) + " мм" if dims else "нет данных"
        weight = d.get("weight_kg")
        weight_str = f"{weight} кг" if weight is not None else "нет данных"
        kind = "МАСТЕР-коробка" if d["type"] == "master" else "Обычная коробка"
        self.device_info.setText(
            f"Тип: {kind}   |   Размер: {dims_str}   |   Вес: {weight_str}"
        )

    # ======================= Настройки паллет =======================
    def _on_global_pallet_changed(self):
        if self.cb_uniform_pallets.isChecked():
            self.refresh_pallet_settings()

    def refresh_pallet_settings(self):
        self._updating_pallet_settings = True

        counts = {}
        for row in range(self.order_table.rowCount()):
            pg_item = self.order_table.item(row, 5)
            if pg_item is None:
                continue
            try:
                g = int(pg_item.text().strip())
            except (ValueError, AttributeError):
                continue
            qty_item = self.order_table.item(row, 3)
            try:
                qty = int(qty_item.text()) if qty_item else 0
            except ValueError:
                qty = 0
            counts[g] = counts.get(g, 0) + qty

        groups = sorted(counts.keys())
        uniform = self.cb_uniform_pallets.isChecked()

        glob_L = self.pallet_length.value()
        glob_W = self.pallet_width.value()
        glob_H = self.pallet_height.value()
        glob_MW = self.pallet_max_weight.value()

        grey = QBrush(QColor(238, 238, 238))
        white = QBrush(QColor(255, 255, 255))
        side_hl = QBrush(QColor(255, 245, 200))

        self.pallet_settings_table.setRowCount(0)

        for g in groups:
            row = self.pallet_settings_table.rowCount()
            self.pallet_settings_table.insertRow(row)

            ov = self.pallet_overrides.get(g, {}) or {}
            val_L = float(ov.get("L", glob_L)) if not uniform else glob_L
            val_W = float(ov.get("W", glob_W)) if not uniform else glob_W
            val_H = float(ov.get("H", glob_H)) if not uniform else glob_H
            val_MW = float(ov.get("max_weight", glob_MW)) if not uniform else glob_MW

            it_num = QTableWidgetItem(str(g))
            it_num.setTextAlignment(Qt.AlignCenter)
            it_num.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.pallet_settings_table.setItem(row, 0, it_num)

            it_cnt = QTableWidgetItem(str(counts[g]))
            it_cnt.setTextAlignment(Qt.AlignCenter)
            it_cnt.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.pallet_settings_table.setItem(row, 1, it_cnt)

            for col, val in ((2, val_L), (3, val_W), (4, val_H), (5, val_MW)):
                it = QTableWidgetItem(f"{val:g}")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if uniform:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    it.setBackground(grey)
                else:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                                Qt.ItemIsEditable)
                    it.setBackground(white)
                self.pallet_settings_table.setItem(row, col, it)

            is_side = g in self.side_first_layer_groups
            it_side = QTableWidgetItem("ДА" if is_side else "нет")
            it_side.setTextAlignment(Qt.AlignCenter)
            it_side.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if is_side:
                it_side.setBackground(QBrush(QColor(255, 200, 60)))
                f = QFont()
                f.setBold(True)
                it_side.setFont(f)
                it_side.setForeground(QBrush(QColor(80, 40, 0)))
            else:
                it_side.setForeground(QBrush(QColor(150, 150, 150)))
            self.pallet_settings_table.setItem(row, 6, it_side)

            if g in self.side_first_layer_groups:
                for col in (0, 1, 2, 3, 4, 5):
                    c = self.pallet_settings_table.item(row, col)
                    if c is not None:
                        c.setBackground(side_hl)

        self._updating_pallet_settings = False

    def on_pallet_settings_clicked(self, row: int, col: int):
        if col != 6:
            return
        num_item = self.pallet_settings_table.item(row, 0)
        if num_item is None:
            return
        try:
            g = int(num_item.text())
        except ValueError:
            return

        if g in self.side_first_layer_groups:
            self.side_first_layer_groups.discard(g)
        else:
            self.side_first_layer_groups.add(g)

        self.refresh_pallet_settings()

    def on_pallet_settings_changed(self, item):
        if self._updating_pallet_settings:
            return

        row = item.row()
        col = item.column()
        num_item = self.pallet_settings_table.item(row, 0)
        if num_item is None:
            return
        try:
            g = int(num_item.text())
        except ValueError:
            return

        if col in (2, 3, 4, 5):
            if self.cb_uniform_pallets.isChecked():
                return
            txt = item.text().strip().replace(",", ".")
            try:
                val = float(txt)
            except ValueError:
                self._updating_pallet_settings = True
                old = self.pallet_overrides.get(g, {})
                keys = {2: "L", 3: "W", 4: "H", 5: "max_weight"}
                k = keys[col]
                fallback = {
                    "L": self.pallet_length.value(),
                    "W": self.pallet_width.value(),
                    "H": self.pallet_height.value(),
                    "max_weight": self.pallet_max_weight.value(),
                }[k]
                item.setText(f"{float(old.get(k, fallback)):g}")
                self._updating_pallet_settings = False
                return

            keys = {2: "L", 3: "W", 4: "H", 5: "max_weight"}
            k = keys[col]
            ov = self.pallet_overrides.setdefault(g, {})
            ov[k] = float(val)
            self._updating_pallet_settings = True
            item.setText(f"{float(val):g}")
            self._updating_pallet_settings = False

    # ======================= Заказ =======================
    def _add_device_row(self, d, qty, pallet_no):
        dims = d.get("dims_mm") or (0, 0, 0)
        weight = d.get("weight_kg")
        row = self.order_table.rowCount()
        self.order_table.insertRow(row)
        self.order_table.setItem(row, 0, QTableWidgetItem(d["name"]))
        self.order_table.setItem(
            row, 1, QTableWidgetItem("×".join(str(int(x)) for x in dims))
        )
        self.order_table.setItem(
            row, 2, QTableWidgetItem("" if weight is None else str(weight))
        )
        self.order_table.setItem(row, 3, QTableWidgetItem(str(qty)))
        self.order_table.setItem(
            row, 4,
            QTableWidgetItem("МАСТЕР" if d["type"] == "master" else "обычная")
        )
        self.order_table.setItem(row, 5, QTableWidgetItem(str(pallet_no)))
        for col in (0, 1, 2, 4):
            item = self.order_table.item(row, col)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def add_to_order(self):
        d = self.device_combo.currentData()
        if not d:
            QMessageBox.warning(self, "Ошибка", "Выбери устройство.")
            return
        self._add_device_row(d, self.qty_spin.value(),
                             self.add_pallet_spin.value())
        self.refresh_pallet_settings()

    def delete_order_row(self):
        current = self.order_table.currentRow()
        if current >= 0:
            self.order_table.removeRow(current)
            self.refresh_pallet_settings()

    def clear_order(self):
        if QMessageBox.question(
            self, "Подтверждение", "Очистить весь заказ?"
        ) == QMessageBox.Yes:
            self.order_table.setRowCount(0)
            self.refresh_pallet_settings()

    # ======================= Импорт спецификации =======================
    def load_specification(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать файл спецификации", "",
            "Excel (*.xlsx *.xlsm);;Все файлы (*)"
        )
        if not path:
            return

        try:
            spec = spec_parser.parse_spec(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка",
                                 f"Не удалось прочитать файл:\n{e}")
            return

        if not spec["items"]:
            QMessageBox.warning(
                self, "Пусто",
                "В файле не найдено ни одной позиции оборудования."
            )
            return

        known_models = {d["name"] for d in self.devices}
        dlg = SpecImportDialog(spec, known_models, self)
        if not dlg.exec():
            return

        selected = dlg.get_selected()
        unknown_checked = dlg.get_unknown_checked()
        pallet_no = dlg.get_pallet_no()

        if not selected and not unknown_checked:
            QMessageBox.information(self, "Ничего не выбрано",
                                    "Не отмечено ни одной позиции.")
            return

        if unknown_checked:
            ans = QMessageBox.question(
                self, "Неизвестные модели",
                "Следующие модели не найдены в справочнике и "
                "будут пропущены:\n\n  • "
                + "\n  • ".join(unknown_checked)
                + "\n\nПродолжить добавление остальных?"
            )
            if ans != QMessageBox.Yes:
                return

        added = 0
        for model, qty in selected:
            d = next((x for x in self.devices if x["name"] == model), None)
            if d is None:
                continue
            self._add_device_row(d, qty, pallet_no)
            added += 1

        self.refresh_pallet_settings()

        QMessageBox.information(
            self, "Готово",
            f"Добавлено позиций: {added}\n"
            f"Пропущено (нет в справочнике): {len(unknown_checked)}"
        )

    # ======================= Импорт заказа =======================
    def import_order_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт заказа из Excel", "",
            "Excel (*.xlsx *.xlsm);;Все файлы (*)"
        )
        if not path:
            return

        try:
            parsed = order_import.parse_order(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка",
                                 f"Не удалось прочитать файл:\n{e}")
            return

        if not parsed["items"]:
            QMessageBox.warning(
                self, "Пусто",
                "В файле не найдено ни одной позиции."
            )
            return

        known_models = {d["name"] for d in self.devices}
        dlg = OrderImportDialog(parsed["items"], known_models, self)
        if not dlg.exec():
            return

        selected = dlg.get_selected()
        unknown_checked = dlg.get_unknown_checked()

        if not selected and not unknown_checked:
            QMessageBox.information(self, "Ничего не выбрано",
                                    "Не отмечено ни одной позиции.")
            return

        if unknown_checked:
            ans = QMessageBox.question(
                self, "Неизвестные модели",
                "Следующие модели не найдены в справочнике:\n\n  • "
                + "\n  • ".join(unknown_checked)
                + "\n\nПродолжить?"
            )
            if ans != QMessageBox.Yes:
                return

        added = 0
        for name, qty, pallet in selected:
            d = next((x for x in self.devices if x["name"] == name), None)
            if d is None:
                continue
            self._add_device_row(d, qty, pallet)
            added += 1

        self.refresh_pallet_settings()

        QMessageBox.information(
            self, "Готово",
            f"Добавлено позиций: {added}\n"
            f"Пропущено: {len(unknown_checked)}"
        )

    # ======================= Экспорт заказа =======================
    def export_order_to_excel(self):
        if self.order_table.rowCount() == 0:
            QMessageBox.warning(self, "Экспорт", "Заказ пуст.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт заказа в Excel", "order.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".xlsm")):
            path += ".xlsx"

        items = []
        try:
            for row in range(self.order_table.rowCount()):
                name = self.order_table.item(row, 0).text()
                qty_item = self.order_table.item(row, 3)
                qty = int(qty_item.text()) if qty_item else 0
                pg_item = self.order_table.item(row, 5)
                pg_str = pg_item.text().strip() if pg_item else "1"
                pallet_group = int(pg_str) if pg_str else 1
                items.append({"name": name, "qty": qty,
                              "pallet_group": pallet_group})
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать:\n{e}")
            return

        pallet_params = {
            "L": self.pallet_length.value(),
            "W": self.pallet_width.value(),
            "H": self.pallet_height.value(),
            "max_weight": self.pallet_max_weight.value(),
        }

        try:
            order_export.export_order_xlsx(items, path,
                                           pallet_params=pallet_params)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", str(e))
            return

        QMessageBox.information(self, "Готово",
                                f"Заказ экспортирован:\n{path}")

    # ======================= Чекбокс подписей =======================
    def on_toggle_labels(self, checked):
        self.viewer.set_show_labels(checked)

    # ======================= Заказ JSON =======================
    def _collect_order_data(self):
        items = []
        for row in range(self.order_table.rowCount()):
            name = self.order_table.item(row, 0).text()
            dims_str = self.order_table.item(row, 1).text()
            weight_str = self.order_table.item(row, 2).text()
            qty = int(self.order_table.item(row, 3).text())
            kind = self.order_table.item(row, 4).text()
            pg_item = self.order_table.item(row, 5)
            pg_str = pg_item.text().strip() if pg_item else "1"
            pallet_group = int(pg_str) if pg_str else 1
            items.append({
                "name": name, "dims": dims_str,
                "weight_kg": float(weight_str) if weight_str else None,
                "qty": qty, "kind": kind, "pallet_group": pallet_group,
            })

        return {
            "version": "1.9",
            "pallet": {
                "L": self.pallet_length.value(),
                "W": self.pallet_width.value(),
                "H": self.pallet_height.value(),
                "max_weight": self.pallet_max_weight.value(),
                "tare_weight": self.pallet_tare_weight.value(),
                "use_tare": self.cb_use_tare.isChecked(),
                "max_overhang_mm": self.max_overhang_spin.value(),
                "full_support": self.cb_full_support.isChecked(),
                "side_on_floor": self.cb_side_on_floor.isChecked(),
                "group_by_model": self.cb_group_by_model.isChecked(),
                "post_optimize": self.cb_post_optimize.isChecked(),
                "prefer_tight": self.cb_prefer_tight.isChecked(),
                "repack": self.cb_repack.isChecked(),
            },
            "pallet_uniform": self.cb_uniform_pallets.isChecked(),
            "pallet_overrides": {
                str(k): dict(v) for k, v in self.pallet_overrides.items()
            },
            "side_first_layer_groups": sorted(self.side_first_layer_groups),
            "show_labels": self.cb_show_labels.isChecked(),
            "items": items,
        }

    def save_order(self):
        if self.order_table.rowCount() == 0:
            QMessageBox.warning(self, "Сохранение", "Заказ пуст.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить заказ", "order.json", "Заказ (*.json)"
        )
        if not path:
            return
        try:
            data = self._collect_order_data()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        QMessageBox.information(self, "Готово", f"Заказ сохранён:\n{path}")

    def load_order(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить заказ", "", "Заказ (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return

        p = data.get("pallet", {})
        self.pallet_length.setValue(float(p.get("L", 1200)))
        self.pallet_width.setValue(float(p.get("W", 800)))
        self.pallet_height.setValue(float(p.get("H", 1500)))
        self.pallet_max_weight.setValue(float(p.get("max_weight", 1000)))
        self.pallet_tare_weight.setValue(float(p.get("tare_weight", 25)))
        self.max_overhang_spin.setValue(float(p.get("max_overhang_mm", 0)))
        self.cb_use_tare.setChecked(bool(p.get("use_tare", False)))
        self.cb_full_support.setChecked(bool(p.get("full_support", False)))
        self.cb_side_on_floor.setChecked(bool(p.get("side_on_floor", False)))
        self.cb_group_by_model.setChecked(bool(p.get("group_by_model", False)))
        self.cb_post_optimize.setChecked(bool(p.get("post_optimize", False)))
        self.cb_prefer_tight.setChecked(bool(p.get("prefer_tight", False)))
        self.cb_repack.setChecked(bool(p.get("repack", False)))
        self.cb_show_labels.setChecked(bool(data.get("show_labels", True)))

        self.cb_uniform_pallets.setChecked(bool(data.get("pallet_uniform", True)))

        po = data.get("pallet_overrides", {}) or {}
        self.pallet_overrides = {}
        for k, v in po.items():
            try:
                g = int(k)
            except ValueError:
                continue
            if not isinstance(v, dict):
                continue
            ov = {}
            for kk in ("L", "W", "H", "max_weight"):
                if kk in v:
                    try:
                        ov[kk] = float(v[kk])
                    except (TypeError, ValueError):
                        pass
            if ov:
                self.pallet_overrides[g] = ov

        self.side_first_layer_groups = set(
            int(x) for x in data.get("side_first_layer_groups", [])
        )

        self.order_table.setRowCount(0)
        for it in data.get("items", []):
            row = self.order_table.rowCount()
            self.order_table.insertRow(row)
            self.order_table.setItem(row, 0, QTableWidgetItem(it.get("name", "")))
            self.order_table.setItem(row, 1, QTableWidgetItem(it.get("dims", "")))
            w = it.get("weight_kg")
            self.order_table.setItem(
                row, 2, QTableWidgetItem("" if w is None else str(w))
            )
            self.order_table.setItem(row, 3, QTableWidgetItem(str(it.get("qty", 1))))
            self.order_table.setItem(
                row, 4, QTableWidgetItem(it.get("kind", "обычная"))
            )
            self.order_table.setItem(
                row, 5, QTableWidgetItem(str(it.get("pallet_group", 1)))
            )
            for col in (0, 1, 2, 4):
                item = self.order_table.item(row, col)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

        self.refresh_pallet_settings()

        QMessageBox.information(self, "Готово",
                                f"Загружено позиций: {self.order_table.rowCount()}")

    # ======================= Расчёт =======================
    def calculate(self):
        if self.order_table.rowCount() == 0:
            QMessageBox.warning(self, "Ошибка", "Заказ пуст.")
            return

        items = []
        try:
            for row in range(self.order_table.rowCount()):
                name = self.order_table.item(row, 0).text()
                dims_str = self.order_table.item(row, 1).text()
                weight_str = self.order_table.item(row, 2).text()
                qty = int(self.order_table.item(row, 3).text())
                pg_item = self.order_table.item(row, 5)
                pg_str = pg_item.text().strip() if pg_item else "1"
                pallet_group = int(pg_str) if pg_str else 1
                L, W, H = [float(x) for x in dims_str.split("×")]
                weight = float(weight_str) if weight_str else 0.0
                items.append({
                    "name": name, "dims": (L, W, H),
                    "weight_kg": weight, "qty": qty,
                    "pallet_group": pallet_group,
                })
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать:\n{e}")
            return

        pl = self.pallet_length.value()
        pw = self.pallet_width.value()
        ph = self.pallet_height.value()
        pmw = self.pallet_max_weight.value()
        tare = self.pallet_tare_weight.value()
        use_tare = self.cb_use_tare.isChecked()
        max_overhang_mm = self.max_overhang_spin.value()
        full_support = self.cb_full_support.isChecked()
        side_on_floor = self.cb_side_on_floor.isChecked()
        group_by_model = self.cb_group_by_model.isChecked()
        post_optimize = self.cb_post_optimize.isChecked()
        prefer_tight = self.cb_prefer_tight.isChecked()
        repack = self.cb_repack.isChecked()
        prefer_flat_first = not side_on_floor
        side_first_layer_groups = set(self.side_first_layer_groups)
        uniform = self.cb_uniform_pallets.isChecked()
        pallet_overrides = {} if uniform else dict(self.pallet_overrides)

        try:
            pallets, unpacked = packer3d.pack_items(
                pl, pw, ph, pmw, items,
                max_overhang_mm=max_overhang_mm,
                require_full_support=full_support,
                prefer_flat_first=prefer_flat_first,
                group_by_model=group_by_model,
                side_first_layer_groups=side_first_layer_groups,
                pallet_overrides=pallet_overrides,
                post_optimize=post_optimize,
                prefer_tight=prefer_tight,
                repack=repack,
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка упаковки", str(e))
            return

        ordered_total = sum(it["qty"] for it in items)
        placed_total = sum(len(p["placed"]) for p in pallets)
        goods_weight = sum(p["weight_kg"] for p in pallets)
        tare_total = tare * len(pallets) if use_tare else 0.0
        total_weight = goods_weight + tare_total
        total_volume = sum(p["volume_m3"] for p in pallets)
        total_bbox_volume = sum(p["bbox_volume_m3"] for p in pallets)

        by_model = {}
        for it in items:
            name = it["name"]
            if name not in by_model:
                by_model[name] = {
                    "qty_ordered": 0, "dims": it["dims"],
                    "weight_kg": it["weight_kg"],
                    "placed": 0, "unpacked": 0,
                    "pallet_breakdown": {},
                }
            by_model[name]["qty_ordered"] += it["qty"]

        for p in pallets:
            label = pallet_label(p["group"], p["attempt"])
            for b in p["placed"]:
                m = b["name"].split("#")[0]
                if m in by_model:
                    by_model[m]["placed"] += 1
                    pb = by_model[m]["pallet_breakdown"]
                    pb[label] = pb.get(label, 0) + 1

        for u in unpacked:
            m = u["name"].split("#")[0]
            if m in by_model:
                by_model[m]["unpacked"] += 1

        group_extra = {}
        for p in pallets:
            group_extra.setdefault(p["group"], 0)
            group_extra[p["group"]] += 1
        overflow_groups = {g for g, cnt in group_extra.items() if cnt > 1}

        lines = []
        if uniform:
            lines.append(f"Паллета: {pl:.0f}×{pw:.0f}×{ph:.0f} мм, до {pmw:.0f} кг")
        else:
            lines.append(
                f"Паллеты индивидуальные (базовые: {pl:.0f}×{pw:.0f}×{ph:.0f} мм, "
                f"до {pmw:.0f} кг)"
            )
        lines.append(f"Макс. свес над опорами: {max_overhang_mm:.0f} мм")
        lines.append(f"Опора по всему периметру: "
                     f"{'да' if full_support else 'нет (мин. 50%)'}")
        lines.append(f"Приоритет плоской укладки: "
                     f"{'да' if prefer_flat_first else 'нет (бок разрешён на полу)'}")
        lines.append(f"Группировка по моделям: "
                     f"{'да' if group_by_model else 'нет'}")
        lines.append(f"Пост-оптимизация свободного места: "
                     f"{'да' if post_optimize else 'нет'}")
        lines.append(f"Прижимать коробки к соседним: "
                     f"{'да' if prefer_tight else 'нет'}")
        lines.append(f"Переупаковка в конце: "
                     f"{'да' if repack else 'нет'}")
        if side_first_layer_groups:
            lines.append("Группы с 1-м слоем боком: "
                         + ", ".join(str(g) for g in sorted(side_first_layer_groups)))
        lines.append(f"Всего физических паллет: {len(pallets)}")
        lines.append(f"Уложено: {placed_total} из {ordered_total} коробок")
        lines.append(f"Общий вес коробок: {goods_weight:.2f} кг")
        if use_tare:
            lines.append(f"Вес тары ({tare:.1f} кг × {len(pallets)} пал.): "
                         f"{tare_total:.2f} кг")
            lines.append(f"ОБЩИЙ ВЕС БРУТТО: {total_weight:.2f} кг")
        else:
            lines.append(f"ОБЩИЙ ВЕС: {total_weight:.2f} кг (без тары)")
        lines.append(f"Общий объём коробок: {total_volume:.4f} м³")
        lines.append(f"Общий габаритный объём: {total_bbox_volume:.4f} м³")

        unstable = [p for p in pallets if not p.get("cog_stable", True)]
        if unstable:
            lines.append("")
            lines.append(
                f"⚠️  Устойчивость: {len(unstable)} паллет(ы) с ЦТ вне "
                f"±{int(packer3d.COG_WARN_FRACTION * 100)}% от центра:"
            )
            for i, p in enumerate(pallets, 1):
                if p.get("cog_stable", True):
                    continue
                ox, oy = p["cog_offset_mm"]
                lines.append(
                    f"     • Физ. #{i} ({pallet_label(p['group'], p['attempt'])}) "
                    f"— смещение ЦТ ({ox:+.0f}; {oy:+.0f}) мм"
                )

        lines.append("")
        lines.append("Сводка по физическим паллетам:")
        for i, p in enumerate(pallets, 1):
            label = pallet_label(p["group"], p["attempt"])
            mark_side = " [1-й слой: бок]" if p.get("side_first_layer") else ""
            mark_cog = "" if p.get("cog_stable", True) else "  ⚠️ ЦТ"
            p_max = p.get("max_weight", pmw)
            lines.append(
                f"  Физ. #{i}  →  Паллета {label}{mark_side}  —  "
                f"{len(p['placed'])} кор.,  "
                f"{p['weight_kg']:.2f} кг,  "
                f"высота {p['height_mm']:.0f} мм "
                f"({100 * p['height_mm'] / p_max:.0f}% от макс.){mark_cog}"
            )

        for g in sorted(overflow_groups):
            lines.append("")
            lines.append(
                f"⚠️  Группа {g}: коробки не поместились на одну паллету — "
                f"продолжения: {group_extra[g]} шт."
            )

        for i, p in enumerate(pallets, 1):
            bx, by, bz = p["bbox_size_mm"]
            label = pallet_label(p["group"], p["attempt"])
            p_L = p.get("L", pl); p_W = p.get("W", pw)
            p_H = p.get("H", ph); p_MW = p.get("max_weight", pmw)
            lines.append("")
            header = f"── Паллета {label}  [физическая #{i}]"
            if p.get("side_first_layer"):
                header += "  [1-й слой: бок]"
            header += " ──"
            lines.append(header)
            lines.append(f"   паллета:             {p_L:.0f}×{p_W:.0f}×{p_H:.0f} мм, "
                         f"до {p_MW:.0f} кг")
            lines.append(f"   коробок:             {len(p['placed'])}")
            lines.append(f"   вес коробок:         {p['weight_kg']:.2f} кг "
                         f"({100 * p['weight_kg'] / p_MW:.0f}% от макс.)")
            if use_tare:
                lines.append(f"   + тара:              {tare:.2f} кг")
                lines.append(f"   вес брутто:          {p['weight_kg'] + tare:.2f} кг")
            lines.append(f"   объём коробок:       {p['volume_m3']:.4f} м³")
            lines.append(f"   габаритный объём:    {p['bbox_volume_m3']:.4f} м³ "
                         f"({bx:.0f}×{by:.0f}×{bz:.0f} мм)")
            lines.append(f"   высота:              {p['height_mm']:.0f} мм "
                         f"({100 * p['height_mm'] / p_H:.0f}% от макс.)")
            cx, cy, cz = p["cog_mm"]
            ox, oy = p["cog_offset_mm"]
            cog_mark = "✅" if p.get("cog_stable", True) else "⚠️"
            lines.append(f"   ЦТ:                  ({cx:.0f}; {cy:.0f}; {cz:.0f}) мм  "
                         f"смещение ({ox:+.0f}; {oy:+.0f}) мм  {cog_mark}")
            composition = {}
            for b in p["placed"]:
                m = b["name"].split("#")[0]
                composition[m] = composition.get(m, 0) + 1
            if composition:
                lines.append("   состав:")
                for m in sorted(composition, key=lambda x: -composition[x]):
                    lines.append(f"       • {m}: {composition[m]} шт")

        lines.append("")
        lines.append("По моделям (с разбивкой по паллетам):")
        for name, d in by_model.items():
            L, W, H = d["dims"]
            mark = "✅" if d["unpacked"] == 0 else "⚠️"
            lines.append(
                f"  {mark} {name}  —  {d['placed']}/{d['qty_ordered']} шт  "
                f"({int(L)}×{int(W)}×{int(H)} мм, {d['weight_kg'] or 0} кг/шт)"
            )
            if d["pallet_breakdown"]:
                for label, cnt in d["pallet_breakdown"].items():
                    lines.append(f"       • Паллета {label}: {cnt} шт")
            if d["unpacked"]:
                lines.append(f"       ❌ не поместилось: {d['unpacked']} шт")

        if unpacked:
            lines.append("")
            lines.append(
                f"⚠️  Не поместилось: {len(unpacked)} шт."
            )

        self.results_text.setPlainText("\n".join(lines))
        print("\n".join(lines))

        self.last_calc = {
            "pallet": {"L": pl, "W": pw, "H": ph, "max_weight": pmw,
                       "tare_weight": tare, "use_tare": use_tare,
                       "max_overhang_mm": max_overhang_mm,
                       "full_support": full_support,
                       "side_on_floor": side_on_floor,
                       "group_by_model": group_by_model,
                       "uniform": uniform},
            "side_first_layer_groups": sorted(side_first_layer_groups),
            "items": items, "pallets": pallets, "unpacked": unpacked,
            "by_model": by_model, "goods_weight": goods_weight,
            "tare_total": tare_total, "total_weight": total_weight,
        }

        self.viewer.show_layout(
            pl, pw, ph, pallets,
            pallet_thickness=PALLET_THICKNESS_MM,
            show_labels=self.cb_show_labels.isChecked(),
        )

        legend = self.viewer.get_legend(pallets)
        parts = []
        for name, (r, g, b) in legend.items():
            parts.append(
                f'<span style="background: rgb({r},{g},{b}); '
                f'color:white; padding:1px 6px; border-radius:3px;">'
                f'&nbsp;&nbsp;</span> {name}'
            )
        self.legend_label.setText("&nbsp; ".join(parts))

    # ======================= Экспорт =======================
    def export_excel(self):
        if not self.last_calc:
            QMessageBox.warning(self, "Экспорт", "Сначала рассчитайте укладку.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить Excel-отчёт", "pallet_report.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            exporter.export_excel(self.last_calc, path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", str(e))
            return
        QMessageBox.information(self, "Готово", f"Excel сохранён:\n{path}")

    def export_pdf(self):
        if not self.last_calc:
            QMessageBox.warning(self, "Экспорт", "Сначала рассчитайте укладку.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PDF-отчёт", "pallet_report.pdf",
            "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            exporter.export_pdf(self.last_calc, path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", str(e))
            return
        QMessageBox.information(self, "Готово", f"PDF сохранён:\n{path}")

    # ======================= Отгрузки =======================
    def open_shipments(self):
        from shipments_dialog import ShipmentsDialog
        dlg = ShipmentsDialog(self)
        dlg.exec()
        self._refresh_overdue_banner()

    def _refresh_overdue_banner(self):
        try:
            overdue = shipments.overdue_records()
        except Exception:
            overdue = []

        if overdue:
            n = len(overdue)
            self.btn_shipments.setText(f"📦 Отгрузки ({n}!)")
            self.btn_shipments.setStyleSheet(
                "QPushButton { padding: 6px 10px; font-weight: bold; "
                "background: #d32f2f; color: white; border-radius: 3px; }"
                "QPushButton:hover { background: #b71c1c; }"
            )
            self.btn_shipments.setToolTip(
                f"⚠ Просрочено отправок: {n}.\n"
                "Открой список, чтобы увидеть детали."
            )
        else:
            self.btn_shipments.setText("📦 Отгрузки")
            self.btn_shipments.setStyleSheet(
                "QPushButton { padding: 6px 10px; font-weight: bold; "
                "background: #7b1fa2; color: white; border-radius: 3px; }"
                "QPushButton:hover { background: #6a1b9a; }"
            )
            self.btn_shipments.setToolTip(
                "Учёт отправок демо-оборудования: список, поиск,\n"
                "статусы, возвраты, PDF для транспортной компании."
            )

    # ======================= Почта =======================
    def send_email(self):
        if not self.last_calc:
            QMessageBox.warning(self, "Outlook", "Сначала рассчитайте укладку.")
            return

        n_pallets = len(self.last_calc["pallets"])
        ordered = sum(it["qty"] for it in self.last_calc["items"])
        placed = sum(len(p["placed"]) for p in self.last_calc["pallets"])

        default_subject = (
            f"Отчёт об укладке коробок на паллету — "
            f"{datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        default_body = (
            "Здравствуйте!\n\n"
            f"Направляю отчёт об укладке коробок на паллету.\n\n"
            f"• Всего паллет: {n_pallets}\n"
            f"• Уложено коробок: {placed} из {ordered}\n"
            f"• Общий вес: {self.last_calc['total_weight']:.2f} кг\n"
            f"\nВо вложении — PDF-отчёт и Excel-расчёт.\n\n"
            "С уважением,\n"
        )

        dlg = EmailDialog(
            default_subject=default_subject,
            default_body=default_body,
            can_attach_pdf=True,
            can_attach_xlsx=True,
            parent=self,
        )
        if not dlg.exec():
            return

        subject = dlg.get_subject()
        body = dlg.get_body()
        need_pdf = dlg.wants_pdf()
        need_xlsx = dlg.wants_xlsx()

        if not (need_pdf or need_xlsx):
            QMessageBox.warning(self, "Outlook", "Не выбрано ни одного вложения.")
            return

        paths, warns = prepare_attachments(
            self.last_calc, need_pdf, need_xlsx, viewer=self.viewer
        )
        if not paths:
            QMessageBox.critical(
                self, "Ошибка",
                "Не удалось подготовить файлы вложений:\n\n" + "\n".join(warns)
            )
            return

        ok, err = mailer.send_via_outlook(subject, body, paths)

        if not ok:
            QMessageBox.critical(self, "Ошибка Outlook", err)
            return

        msg = (
            "Письмо открыто в Outlook со вложениями:\n\n"
            + "\n".join(f"  • {Path(p).name}" for p in paths)
            + "\n\nВ окне Outlook нажми «Кому…» и выбери получателя "
            "из адресной книги, затем «Отправить»."
        )
        if warns:
            msg += "\n\nПредупреждения:\n" + "\n".join(warns)
        QMessageBox.information(self, "Outlook", msg)

    # ======================= Скриншот 3D =======================
    def screenshot_3d(self):
        if not self.last_calc:
            QMessageBox.warning(self, "Скриншот", "Сначала рассчитайте укладку.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить скриншот 3D", "pallet_3d.png", "PNG (*.png)"
        )
        if not path:
            return
        try:
            img = self.viewer.render_screenshot(scale=3)
            if img is None or img.isNull():
                raise RuntimeError("Не удалось получить изображение 3D")
            if not img.save(path, "PNG"):
                raise RuntimeError("Не удалось сохранить PNG")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        QMessageBox.information(
            self, "Готово",
            f"Скриншот сохранён:\n{path}\nРазмер: {img.width()}×{img.height()} px"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    _apply_light_palette(app)
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window._apply_window_geometry)
    sys.exit(app.exec())