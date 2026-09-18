"""
Хранилище отправок демо-оборудования (shipments.json).

Записи хранятся в JSON. Файл лежит рядом с программой
(на Windows) или в ~/Library/Application Support/PalletPacker/
(на macOS).
"""
from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path

import platform_utils


SHIPMENTS_FILE = platform_utils.app_dir() / "shipments.json"

# ---------- статусы ----------

STATUS_IN_TRANSIT = "in_transit"
STATUS_DELIVERED = "delivered"
STATUS_RETURNED = "returned"
STATUS_OVERDUE = "overdue"

STATUS_LABELS = {
    STATUS_IN_TRANSIT: "В пути",
    STATUS_DELIVERED: "Доставлено",
    STATUS_RETURNED: "Возвращено",
    STATUS_OVERDUE: "Просрочено",
}

STATUS_COLORS = {
    STATUS_IN_TRANSIT: "#ff9800",   # оранжевый
    STATUS_DELIVERED: "#4caf50",    # зелёный
    STATUS_RETURNED: "#2196f3",     # синий
    STATUS_OVERDUE: "#f44336",      # красный
}


# ---------- работа с датой ----------

def _today() -> date:
    return date.today()


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _date_to_str(d: date | None) -> str:
    if d is None:
        return ""
    return d.strftime("%Y-%m-%d")


# ---------- вычисление статуса ----------

def compute_status(record: dict) -> str:
    """
    Возвращает эффективный статус с учётом дат:
    - если стоит actual_return_date → returned
    - иначе если planned_return_date < сегодня → overdue
    - иначе оставляем сохранённый status (in_transit / delivered)
    """
    if record.get("actual_return_date"):
        return STATUS_RETURNED

    planned = _parse_date(record.get("planned_return_date", ""))
    if planned and planned < _today():
        return STATUS_OVERDUE

    st = record.get("status", STATUS_IN_TRANSIT)
    if st == STATUS_OVERDUE:
        # сбрасываем устаревший статус
        st = STATUS_IN_TRANSIT
    return st


def status_label(record: dict) -> str:
    return STATUS_LABELS.get(compute_status(record), "—")


def status_color(record: dict) -> str:
    return STATUS_COLORS.get(compute_status(record), "#888888")


# ---------- генерация id ----------

def _next_id(records: list[dict]) -> str:
    year = _today().year
    prefix = f"SHP-{year}-"
    max_n = 0
    for r in records:
        rid = r.get("id", "")
        if rid.startswith(prefix):
            try:
                n = int(rid[len(prefix):])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return f"{prefix}{max_n + 1:04d}"


# ---------- хранилище ----------

def load_shipments() -> list[dict]:
    if not SHIPMENTS_FILE.exists():
        return []
    try:
        with open(SHIPMENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def save_shipments(records: list[dict]) -> None:
    try:
        with open(SHIPMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise RuntimeError(f"Не удалось сохранить shipments.json: {e}")


# ---------- CRUD ----------

def new_record() -> dict:
    """Возвращает пустую заготовку новой отправки."""
    records = load_shipments()
    return {
        "id": _next_id(records),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": STATUS_IN_TRANSIT,

        "address": "",
        "entity_type": "legal",
        "entity_name": "",
        "inn": "",
        "contact_person": "",
        "contact_phone": "",
        "work_hours": "",
        "has_break": False,
        "break_time": "",
        "call_before_30min": False,
        "need_pass": False,
        "comment": "",

        "ship_date": _date_to_str(_today()),
        "planned_return_date": "",
        "actual_return_date": "",
        "shipped_by": "",
        "tracking_number": "",
        "delivery_cost": 0,

        # грузовые характеристики (снапшот из расчёта укладки
        # или введённые вручную)
        "cargo_weight_kg": 0.0,
        "cargo_volume_m3": 0.0,
        "cargo_bbox_volume_m3": 0.0,
        "cargo_pallets": 0,

        "items": [],
    }


def add_shipment(record: dict) -> None:
    records = load_shipments()
    records.append(record)
    save_shipments(records)


def update_shipment(record: dict) -> None:
    records = load_shipments()
    for i, r in enumerate(records):
        if r.get("id") == record.get("id"):
            records[i] = record
            break
    else:
        # не нашли — добавим
        records.append(record)
    save_shipments(records)


def delete_shipment(shipment_id: str) -> None:
    records = load_shipments()
    records = [r for r in records if r.get("id") != shipment_id]
    save_shipments(records)


def get_shipment(shipment_id: str) -> dict | None:
    for r in load_shipments():
        if r.get("id") == shipment_id:
            return r
    return None


# ---------- возврат ----------

def mark_returned(shipment_id: str,
                  return_date: date | None = None) -> bool:
    """Ставит фактическую дату возврата = сегодня (или указанную)."""
    records = load_shipments()
    for r in records:
        if r.get("id") == shipment_id:
            if return_date is None:
                return_date = _today()
            r["actual_return_date"] = _date_to_str(return_date)
            r["status"] = STATUS_RETURNED
            save_shipments(records)
            return True
    return False


# ---------- поиск / фильтры ----------

def filter_records(records: list[dict],
                   text: str = "",
                   status: str = "") -> list[dict]:
    """
    text — подстрока для поиска по id, адресу, получателю,
            контактному лицу, телефону.
    status — один из STATUS_* или пусто (все).
    """
    text = (text or "").strip().lower()
    result = []
    for r in records:
        if text:
            haystack = " ".join([
                str(r.get("id", "")),
                str(r.get("address", "")),
                str(r.get("entity_name", "")),
                str(r.get("contact_person", "")),
                str(r.get("contact_phone", "")),
                str(r.get("tracking_number", "")),
            ]).lower()
            if text not in haystack:
                continue
        if status:
            if compute_status(r) != status:
                continue
        result.append(r)
    return result


def overdue_records() -> list[dict]:
    """Возвращает список отправок со статусом overdue."""
    return [r for r in load_shipments()
            if compute_status(r) == STATUS_OVERDUE]


# ---------- сводка по составу ----------

def total_qty(record: dict) -> int:
    return sum(int(it.get("qty", 0)) for it in record.get("items", []))


def summary_text(record: dict) -> str:
    """Краткое описание состава для списка."""
    items = record.get("items", [])
    if not items:
        return "—"
    if len(items) == 1:
        it = items[0]
        return f"{it.get('model', '')} × {it.get('qty', 0)}"
    total = sum(int(it.get("qty", 0)) for it in items)
    return f"{len(items)} позиц., {total} шт"
    # ---------- пересчёт грузовых характеристик из состава ----------

def parse_dimensions(s: str) -> list:
    """
    Парсит строку вида «810×625×143», «810x625x143»,
    «810,625,143» → [810.0, 625.0, 143.0]. Или [0,0,0].
    """
    if not s:
        return [0.0, 0.0, 0.0]
    txt = str(s).strip().lower()
    for sep in ("×", "x", "х", "*", ";"):
        txt = txt.replace(sep, ",")
    parts = [p.strip() for p in txt.split(",") if p.strip()]
    nums = []
    for p in parts[:3]:
        try:
            nums.append(float(p.replace(",", ".")))
        except ValueError:
            nums.append(0.0)
    while len(nums) < 3:
        nums.append(0.0)
    return nums


def format_dimensions(dims) -> str:
    """[810, 625, 143] → '810×625×143'. Пропускает нули."""
    if not dims:
        return ""
    try:
        w, d, h = float(dims[0]), float(dims[1]), float(dims[2])
    except (TypeError, ValueError, IndexError):
        return ""
    if not (w or d or h):
        return ""
    return f"{w:.0f}×{d:.0f}×{h:.0f}"


def calc_weight_from_items(items: list) -> float:
    """Σ (qty × weight_kg). items — список dict."""
    total = 0.0
    for it in items:
        try:
            qty = int(it.get("qty", 0) or 0)
            w = float(it.get("weight_kg", 0) or 0)
        except (TypeError, ValueError):
            continue
        total += qty * w
    return total


def calc_volume_from_items(items: list) -> float:
    """Σ (qty × (Ш×Г×В / 1e9)). Результат в м³."""
    total = 0.0
    for it in items:
        try:
            qty = int(it.get("qty", 0) or 0)
        except (TypeError, ValueError):
            continue
        dims = it.get("dims_mm") or []
        if len(dims) < 3:
            continue
        try:
            w = float(dims[0]) or 0
            d = float(dims[1]) or 0
            h = float(dims[2]) or 0
        except (TypeError, ValueError):
            continue
        total += qty * (w * d * h) / 1e9
    return total