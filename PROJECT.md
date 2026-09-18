# Pallet Packer — расчёт укладки коробок на паллету

## Текущая версия: 1.4

## Стек
- Python 3.11+ (у разработчика 3.14 — тоже работает)
- PySide6, pyqtgraph.opengl, numpy, openpyxl, pillow, PyInstaller
- Inno Setup 6 — для установщика
- Собственный упаковщик (py3dbp НЕ используется)

## Файлы
- `main.py` — главное окно, весь UI
- `packer3d.py` — упаковщик + Viewer3D
- `exporter.py` — Excel-отчёт + PDF-отчёт (результаты расчёта)
- `device_editor.py` — редактор справочника
- `spec_parser.py` — парсер спецификаций Excel
- `spec_import_dialog.py` — диалог импорта спецификаций
- `order_import.py` — парсер заказа из Excel
- `order_import_dialog.py` — диалог импорта заказа
- `order_export.py` — экспорт заказа в Excel
- `settings.py` — сохранение настроек окна (settings.json)
- `make_icon.py` — генератор icon.ico (требует pillow)
- `installer.iss` — скрипт Inno Setup
- `devices.json` — справочник коробок

## Что реализовано

### v1.4
- Импорт заказа из Excel («📂 Импорт заказа из Excel»):
  A — модель, B — кол-во, C — паллета №
- **Экспорт заказа в Excel («📤 Экспорт заказа в Excel»):**
  тот же формат + шапка с параметрами паллеты и датой; round-trip с импортом
- `make_icon.py` — генератор `icon.ico`
- Иконка окна: если рядом есть `icon.ico`, подхватывается автоматически
- `installer.iss` — скрипт Inno Setup
  (установка в `%LOCALAPPDATA%\PalletPacker`, без UAC,
   ярлык на рабочем столе опционально)

### v1.3
- Сохранение настроек окна в `settings.json`
- Проверка устойчивости: ЦТ каждой паллеты; предупреждение при
  смещении > ±25 % (`packer3d.COG_WARN_FRACTION`)

### v1.2
- QSplitter, CollapsibleBox, «Настройки паллет» с чекбоксами
- Импорт спецификаций Excel
- Сохранение/загрузка заказа в JSON
- Экспорт Excel-отчёта (4 листа), PDF-отчёта, скриншот 3D
- Редактор справочника, группировка по моделям, боковой слой и т.п.

## Сборка релиза (v1.4)

```bat
:: 1. Иконка
pip install pillow
python make_icon.py

:: 2. PyInstaller
pyinstaller --noconfirm --windowed --name PalletPacker ^
  --icon=icon.ico ^
  --hidden-import=pyqtgraph.opengl ^
  --hidden-import=OpenGL.platform.win32 ^
  --hidden-import=PySide6.QtPrintSupport ^
  --hidden-import=openpyxl ^
  --collect-submodules=openpyxl ^
  --collect-data=pyqtgraph ^
  main.py

:: 3. Копируем данные рядом с exe
copy devices.json dist\PalletPacker\
copy icon.ico    dist\PalletPacker\

:: 4. Inno Setup
iscc installer.iss