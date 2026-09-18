# Pallet Packer

Программа для расчёта укладки коробок на паллеты с 3D-визуализацией,
экспортом в Excel/PDF и отправкой отчёта через Outlook.

## Требования

- Python 3.11+
- Windows 10/11 или macOS 10.15+
- Inno Setup 6 (только для сборки установщика Windows)
- Microsoft Outlook (только для функции отправки на Windows)

## Быстрый старт

### 1. Виртуальное окружение

    python -m venv venv

### 2. Активация

Windows (CMD):

    venv\Scripts\activate

macOS / Linux:

    source venv/bin/activate

### 3. Зависимости

Windows:

    pip install PySide6 pyqtgraph PyOpenGL numpy openpyxl pillow pywin32 pyinstaller

macOS:

    pip install PySide6 pyqtgraph PyOpenGL numpy openpyxl pillow py2app

### 4. Иконка

    python make_icon.py

### 5. Запуск

    python main.py

## Структура проекта

| Файл | Назначение |
|------|-----------|
| main.py | Главное окно, UI |
| packer3d.py | Упаковщик + 3D-визуализация |
| exporter.py | Экспорт в Excel и PDF |
| settings.py | Сохранение/загрузка настроек |
| platform_utils.py | Кроссплатформенные пути |
| spec_parser.py | Парсер спецификаций Excel |
| spec_import_dialog.py | Диалог импорта спецификаций |
| order_import.py | Парсер заказов из Excel |
| order_import_dialog.py | Диалог импорта заказов |
| order_export.py | Экспорт заказов в Excel |
| device_editor.py | Редактор справочника коробок |
| devices_io.py | Импорт/экспорт справочника |
| mailer.py | Отправка через Outlook (Windows) |
| email_dialog.py | Диалог отправки письма |
| make_icon.py | Генератор icon.ico |
| make_icns.py | Генератор icon.icns (macOS) |
| parse_excel.py | Excel -> devices.json |
| installer.iss | Inno Setup (Windows) |
| setup.py | py2app (macOS) |

## Сборка

См. BUILD.md.

## Различия Windows / macOS

| Функция | Windows | macOS |
|---------|---------|-------|
| Расчёт укладки | да | да |
| 3D-визуализация | да | да |
| Excel / PDF экспорт | да | да |
| Импорт заказов и спецификаций | да | да |
| Редактор справочника | да | да |
| Отправка через Outlook | да | нет (кнопка скрыта) |

## Частые проблемы

ModuleNotFoundError: PySide6 — активируй venv.

devices.json не найден — см. шаг про иконку/данные.

Outlook не открывается — нужен классический Outlook из Office,
не «Почта Windows».