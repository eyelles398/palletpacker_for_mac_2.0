"""
Парсер спецификаций оборудования из Excel.

Правила:
- Используется ТОЛЬКО первый лист файла.
- Строка данных = число в колонке A + текст в B + число в D.
- Сертификаты (STSC-, SPSC-) пропускаются.
- Строки-разделители секций пропускаются.
- Одинаковые модели в разных секциях суммируются.
- Файл читается в режиме read-only (работает и с файлами
  с атрибутом "только чтение").
"""
from __future__ import annotations

import openpyxl


CERT_PREFIXES = ("STSC-", "SPSC-")

# Заголовки шапки таблицы, которые надо молча пропустить
HEADER_TOKENS = {
    "артикул", "описание", "кол-во", "количество", "№ п/п",
}


def _is_number(v) -> bool:
    if v is None or isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", ".").strip())
        return True
    except (ValueError, TypeError):
        return False


def parse_spec(path: str) -> dict:
    """
    Читает Excel-спецификацию и возвращает:
      {
        "customer": str,
        "spec_number": str,
        "date": str,
        "items": [{"model": str, "qty": int}, ...],
        "skipped_certs": int,
        "skipped_sections": int,
      }
    """
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.worksheets[0]           # всегда первый лист
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    items = []
    customer = ""
    spec_number = ""
    date_str = ""
    skipped_certs = 0
    skipped_sections = 0

    for row in rows:
        if not row:
            continue

        # --- метаданные: "Заказчик | значение", "Номер спецификации | ..."
        for ci, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            key = cell.strip()
            if key not in ("Заказчик", "Номер спецификации",
                           "Дата расчета", "Срок действия"):
                continue
            val = ""
            for j in range(ci + 1, len(row)):
                v = row[j]
                if v is not None and str(v).strip():
                    val = str(v).strip()
                    break
            if key == "Заказчик":
                customer = val
            elif key == "Номер спецификации":
                spec_number = val
            elif key == "Дата расчета":
                date_str = val

        # --- данные ---
        a = row[0] if len(row) > 0 else None
        b = row[1] if len(row) > 1 else None
        d = row[3] if len(row) > 3 else None

        b_s = "" if b is None else str(b).strip()
        if not b_s:
            continue

        # сертификаты
        if any(b_s.startswith(p) for p in CERT_PREFIXES):
            skipped_certs += 1
            continue

        # шапка таблицы
        if b_s.lower() in HEADER_TOKENS:
            continue

        # полноценная строка данных
        if _is_number(a) and _is_number(d):
            try:
                qty = int(round(float(str(d).replace(",", "."))))
            except (ValueError, TypeError):
                continue
            if qty > 0:
                items.append({"model": b_s, "qty": qty})
            continue

        # всё остальное с текстом в B — разделитель секции
        skipped_sections += 1

    # объединяем одинаковые модели
    merged: dict[str, int] = {}
    for it in items:
        merged[it["model"]] = merged.get(it["model"], 0) + it["qty"]
    items = [{"model": m, "qty": q} for m, q in merged.items()]

    return {
        "customer": customer,
        "spec_number": spec_number,
        "date": date_str,
        "items": items,
        "skipped_certs": skipped_certs,
        "skipped_sections": skipped_sections,
    }