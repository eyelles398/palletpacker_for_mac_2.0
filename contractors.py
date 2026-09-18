"""
Справочник контрагентов (получателей).

Хранится в contractors.json. При создании новой отправки можно
выбрать контрагента из списка — поля заполнятся автоматически.
"""
from __future__ import annotations

import json
from pathlib import Path

import platform_utils


CONTRACTORS_FILE = platform_utils.app_dir() / "contractors.json"


def load_contractors() -> list[dict]:
    if not CONTRACTORS_FILE.exists():
        return []
    try:
        with open(CONTRACTORS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def save_contractors(records: list[dict]) -> None:
    try:
        with open(CONTRACTORS_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise RuntimeError(f"Не удалось сохранить contractors.json: {e}")


def _key(name: str, inn: str = "") -> str:
    """Ключ для дедупликации: имя + ИНН."""
    return (name or "").strip().lower() + "|" + (inn or "").strip()


def find_contractor(name: str, inn: str = "") -> dict | None:
    key = _key(name, inn)
    for c in load_contractors():
        if _key(c.get("entity_name", ""), c.get("inn", "")) == key:
            return c
    return None


def upsert_contractor(record: dict) -> None:
    """
    Сохраняет контрагента в справочник. Если такой уже есть
    (по имени + ИНН) — обновляет данные.
    Ожидаемые поля: entity_type, entity_name, inn, address,
    contact_person, contact_phone, work_hours, has_break,
    break_time, call_before_30min, need_pass, comment.
    """
    if not record.get("entity_name"):
        return

    fields = [
        "entity_type", "entity_name", "inn", "address",
        "contact_person", "contact_phone", "work_hours",
        "has_break", "break_time", "call_before_30min",
        "need_pass", "comment",
    ]
    snapshot = {k: record.get(k, "") for k in fields}

    records = load_contractors()
    key = _key(record.get("entity_name", ""), record.get("inn", ""))

    for i, c in enumerate(records):
        if _key(c.get("entity_name", ""), c.get("inn", "")) == key:
            records[i] = snapshot
            save_contractors(records)
            return

    records.append(snapshot)
    save_contractors(records)


def delete_contractor(entity_name: str, inn: str = "") -> None:
    key = _key(entity_name, inn)
    records = [c for c in load_contractors()
               if _key(c.get("entity_name", ""), c.get("inn", "")) != key]
    save_contractors(records)


def search_contractors(query: str) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return load_contractors()
    result = []
    for c in load_contractors():
        haystack = " ".join([
            str(c.get("entity_name", "")),
            str(c.get("inn", "")),
            str(c.get("contact_person", "")),
            str(c.get("contact_phone", "")),
            str(c.get("address", "")),
        ]).lower()
        if q in haystack:
            result.append(c)
    return result