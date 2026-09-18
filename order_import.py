"""
Импорт заказа из Excel.

Ожидаемый формат первого листа:
    A — модель (название из справочника)
    B — количество
    C — паллета № (необязательно, по умолчанию 1)

Строка-заголовок и строки «ИТОГО …» распознаются и пропускаются.
"""
from __future__ import annotations

import openpyxl


HEADER_WORDS = {
    "модель", "название", "артикул", "наименование", "модель/артикул",
    "кол-во", "количество", "qty", "шт", "шт.",
    "паллета", "паллета №", "паллет", "pallet", "№", "номер",
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


def _to_int(v) -> int | None:
    try:
        return int(round(float(str(v).replace(",", "."))))
    except (ValueError, TypeError):
        return None


def _is_header_row(row) -> bool:
    if not row:
        return False
    a = row[0] if len(row) > 0 else None
    b = row[1] if len(row) > 1 else None
    if not isinstance(a, str):
        return False
    a_low = a.strip().lower()
    # строки-итоги вида "ИТОГО: ..." / "Total: ..." — пропускаем
    if a_low.startswith(("итого", "total")):
        return True
    if _is_number(b):
        return False
    return a_low in HEADER_WORDS


def parse_order(path: str) -> dict:
    """
    Возвращает:
      {
        "items": [{"name": str, "qty": int, "pallet_group": int}, ...],
        "skipped": int,
      }
    """
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    items = []
    skipped = 0

    for row in rows:
        if not row:
            continue

        a = row[0] if len(row) > 0 else None
        b = row[1] if len(row) > 1 else None
        c = row[2] if len(row) > 2 else None

        if _is_header_row(row):
            continue

        if a is None or not isinstance(a, str):
            continue
        name = a.strip()
        if not name:
            continue

        if not _is_number(b):
            skipped += 1
            continue
        qty = _to_int(b)
        if qty is None or qty <= 0:
            skipped += 1
            continue

        pallet_group = 1
        if c is not None and _is_number(c):
            pg = _to_int(c)
            if pg is not None and pg > 0:
                pallet_group = pg

        items.append({
            "name": name,
            "qty": qty,
            "pallet_group": pallet_group,
        })

    return {"items": items, "skipped": skipped}