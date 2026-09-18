"""
Модуль упаковки коробок на паллеты и 3D-визуализации.
Поддерживает:
- индивидуальные параметры для каждой паллеты;
- пост-оптимизацию свободного места мелкими коробками;
- прижимание коробок к соседним (prefer_tight);
- переупаковку паллеты в конце (repack).
"""
import time as _time

import numpy as np
import pyqtgraph.opengl as gl
from PySide6.QtGui import (
    QVector3D, QPainter, QColor, QPen, QBrush, QFont, QImage
)
from PySide6.QtCore import Qt, QRectF, QTimer


OVERHANG_MM      = 10.0
MIN_SUPPORT      = 0.5
FULL_SUPPORT     = 0.98
SMALL_MAX_DIM    = 450.0
PALLET_GAP_MM    = 300.0
STICK_OUT_RATIO  = 1.0 / 3.0
ADJ_TOL_MM       = 2.0
MAX_PALLETS_PER_GROUP = 50

COG_WARN_FRACTION = 0.25
POST_OPT_TIME_LIMIT = 2.0


# ---------- геометрия ----------

def _xy_overlap(x1, y1, dx1, dy1, x2, y2, dx2, dy2):
    return not (
        x1 + dx1 <= x2 + 1e-6 or x2 + dx2 <= x1 + 1e-6 or
        y1 + dy1 <= y2 + 1e-6 or y2 + dy2 <= y1 + 1e-6
    )


def _adjacent(x, y, dx, dy, p, tol=ADJ_TOL_MM):
    px1, py1 = p["x"] - tol, p["y"] - tol
    px2, py2 = p["x"] + p["dx"] + tol, p["y"] + p["dy"] + tol
    return not (x + dx <= px1 or px2 <= x or y + dy <= py1 or py2 <= y)


def _collides_3d(x, y, z, dx, dy, dz, placed):
    for p in placed:
        if not (
            x + dx <= p["x"] + 1e-6 or p["x"] + p["dx"] <= x + 1e-6 or
            y + dy <= p["y"] + 1e-6 or p["y"] + p["dy"] <= y + 1e-6 or
            z + dz <= p["z"] + 1e-6 or p["z"] + p["dz"] <= z + 1e-6
        ):
            return True
    return False


def _support_area(x, y, dx, dy, z, placed):
    if z < 1e-6:
        return dx * dy
    area = 0.0
    for p in placed:
        if abs(p["z"] + p["dz"] - z) > 1e-6:
            continue
        ox1 = max(x, p["x"]); ox2 = min(x + dx, p["x"] + p["dx"])
        oy1 = max(y, p["y"]); oy2 = min(y + dy, p["y"] + p["dy"])
        if ox2 > ox1 and oy2 > oy1:
            area += (ox2 - ox1) * (oy2 - oy1)
    return area


def _support_region(x, y, dx, dy, z, placed):
    if z < 1e-6:
        return None
    min_x = max_x = min_y = max_y = None
    for p in placed:
        if abs(p["z"] + p["dz"] - z) > 1e-6:
            continue
        ox1 = max(x, p["x"]); ox2 = min(x + dx, p["x"] + p["dx"])
        oy1 = max(y, p["y"]); oy2 = min(y + dy, p["y"] + p["dy"])
        if ox2 > ox1 and oy2 > oy1:
            if min_x is None or p["x"] < min_x:
                min_x = p["x"]
            if max_x is None or p["x"] + p["dx"] > max_x:
                max_x = p["x"] + p["dx"]
            if min_y is None or p["y"] < min_y:
                min_y = p["y"]
            if max_y is None or p["y"] + p["dy"] > max_y:
                max_y = p["y"] + p["dy"]
    if min_x is None:
        return None
    return (min_x, max_x, min_y, max_y)


def _overhang_ok(x, y, dx, dy, z, placed, max_overhang_mm):
    if z < 1e-6:
        return True
    region = _support_region(x, y, dx, dy, z, placed)
    if region is None:
        return True
    rx1, rx2, ry1, ry2 = region
    tol = max_overhang_mm + 1e-6
    if x < rx1 - tol:
        return False
    if x + dx > rx2 + tol:
        return False
    if y < ry1 - tol:
        return False
    if y + dy > ry2 + tol:
        return False
    return True


def _contact_area(x, y, dx, dy, z, dz, placed):
    """
    Площадь бокового контакта новой коробки с уже уложенными.
    Считаются вертикальные стенки (боковые касания).
    """
    area = 0.0
    x2 = x + dx
    y2 = y + dy
    z2 = z + dz
    for p in placed:
        px1, py1, pz1 = p["x"], p["y"], p["z"]
        px2 = px1 + p["dx"]
        py2 = py1 + p["dy"]
        pz2 = pz1 + p["dz"]

        # касание по X (стенка коробки к стенке соседа)
        if abs(x2 - px1) < 1e-3 or abs(px2 - x) < 1e-3:
            oy1 = max(y, py1); oy2 = min(y2, py2)
            oz1 = max(z, pz1); oz2 = min(z2, pz2)
            if oy2 > oy1 and oz2 > oz1:
                area += (oy2 - oy1) * (oz2 - oz1)

        # касание по Y
        if abs(y2 - py1) < 1e-3 or abs(py2 - y) < 1e-3:
            ox1 = max(x, px1); ox2 = min(x2, px2)
            oz1 = max(z, pz1); oz2 = min(z2, pz2)
            if ox2 > ox1 and oz2 > oz1:
                area += (ox2 - ox1) * (oz2 - oz1)

    return area


def _find_drop_position(dx, dy, dz, placed, Lmin, Lmax, Wmin, Wmax, H,
                        min_z=0.0, max_stick_ratio=None,
                        max_overhang_mm=0.0,
                        min_support_ratio=MIN_SUPPORT,
                        force_ground=False,
                        prefer_tight=False):
    """
    force_ground=True — только на полу паллеты (z=0).
    prefer_tight=True — выбираем позицию с максимальным боковым
    контактом с уже уложенными коробками.
    """
    x_set = {Lmin, 0.0}
    y_set = {Wmin, 0.0}
    for p in placed:
        x_set.add(p["x"]);  x_set.add(p["x"] + p["dx"])
        y_set.add(p["y"]);  y_set.add(p["y"] + p["dy"])
    x_cands = sorted(x_set)
    y_cands = sorted(y_set)

    best = None
    for y in y_cands:
        if y + dy > Wmax + 1e-6:
            continue
        for x in x_cands:
            if x + dx > Lmax + 1e-6:
                continue
            z = 0.0
            for p in placed:
                if _xy_overlap(x, y, dx, dy, p["x"], p["y"], p["dx"], p["dy"]):
                    z = max(z, p["z"] + p["dz"])
            if force_ground and z > 1e-6:
                continue
            if z < min_z - 1e-6:
                continue
            if z + dz > H + 1e-6:
                continue
            if _collides_3d(x, y, z, dx, dy, dz, placed):
                continue

            sup = _support_area(x, y, dx, dy, z, placed)
            if sup < dx * dy * min_support_ratio - 1e-6:
                continue

            if not _overhang_ok(x, y, dx, dy, z, placed, max_overhang_mm):
                continue

            if max_stick_ratio is not None:
                nb_tops = [
                    p["z"] + p["dz"] for p in placed
                    if _adjacent(x, y, dx, dy, p)
                ]
                if nb_tops:
                    top_ref = max(nb_tops)
                    if (z + dz) - top_ref > dz * max_stick_ratio + 1e-6:
                        continue

            if prefer_tight:
                contact = _contact_area(x, y, dx, dy, z, dz, placed)
                key = (-contact, z, y, x)
            else:
                key = (z, y, x)

            if best is None or key < best[0]:
                best = (key, (x, y, z))
    return best[1] if best else None


def _orientations(it):
    a, b, c = it["a"], it["b"], it["c"]
    return [(a, b, c), (b, a, c), (a, c, b), (c, a, b)]


def _pack_one_pallet(items, L, W, H, max_w, overhang,
                     allow_small_on_floor,
                     max_overhang_mm=0.0,
                     min_support_ratio=MIN_SUPPORT,
                     prefer_flat_first=True,
                     side_first_layer=False,
                     prefer_tight=False):
    Lmin, Lmax = -overhang, L + overhang
    Wmin, Wmax = -overhang, W + overhang
    placed = []
    remaining = []
    total_w = 0.0
    for it in items:
        min_z = 1.0 if (it["is_small"] and not allow_small_on_floor) else 0.0
        best = None

        if side_first_layer:
            for oi, (dx, dy, dz) in enumerate(_orientations(it)):
                if oi < 2:
                    continue
                pos = _find_drop_position(
                    dx, dy, dz, placed,
                    Lmin, Lmax, Wmin, Wmax, H, min_z,
                    max_stick_ratio=STICK_OUT_RATIO,
                    max_overhang_mm=max_overhang_mm,
                    min_support_ratio=min_support_ratio,
                    force_ground=True,
                    prefer_tight=prefer_tight,
                )
                if pos is None:
                    continue
                key = (pos[2], oi, pos[1], pos[0])
                if best is None or key < best[0]:
                    best = (key, pos, (dx, dy, dz))

        if best is None:
            for oi, (dx, dy, dz) in enumerate(_orientations(it)):
                is_side = oi >= 2
                stick = STICK_OUT_RATIO if is_side else None
                pos = _find_drop_position(
                    dx, dy, dz, placed,
                    Lmin, Lmax, Wmin, Wmax, H, min_z,
                    max_stick_ratio=stick,
                    max_overhang_mm=max_overhang_mm,
                    min_support_ratio=min_support_ratio,
                    prefer_tight=prefer_tight,
                )
                if pos is None:
                    continue
                if prefer_flat_first:
                    key = (oi // 2, pos[2], oi, pos[1], pos[0])
                else:
                    key = (pos[2], oi, pos[1], pos[0])
                if best is None or key < best[0]:
                    best = (key, pos, (dx, dy, dz))

        if best is None:
            remaining.append(it)
            continue
        _, (x, y, z), (dx, dy, dz) = best
        if total_w + it["weight"] > max_w + 1e-6:
            remaining.append(it)
            continue
        placed.append({
            "name": it["name"],
            "x": float(x), "y": float(y), "z": float(z),
            "dx": float(dx), "dy": float(dy), "dz": float(dz),
            "weight": float(it["weight"]),
        })
        total_w += it["weight"]
    return placed, remaining, total_w


def _prepare_flat(items, group_by_model=False):
    flat = []
    for it in items:
        L, W, H = it["dims"]
        a, b, c = sorted([L, W, H], reverse=True)
        w = it.get("weight_kg") or 0.0
        vol = a * b * c
        fp = a * b
        is_small = a <= SMALL_MAX_DIM
        for i in range(it["qty"]):
            flat.append({
                "name": f"{it['name']}#{i + 1}",
                "model": it["name"],
                "a": a, "b": b, "c": c,
                "weight": w,
                "volume": vol,
                "footprint": fp,
                "is_small": is_small,
            })

    if group_by_model:
        by_model = {}
        for x in flat:
            by_model.setdefault(x["model"], []).append(x)
        model_vol = {m: sum(x["volume"] for x in lst)
                     for m, lst in by_model.items()}
        sorted_models = sorted(model_vol, key=lambda m: -model_vol[m])
        result = []
        for m in sorted_models:
            group = sorted(by_model[m],
                           key=lambda x: (-x["volume"], -x["weight"]))
            result.extend(group)
        return result

    bigs = [x for x in flat if not x["is_small"]]
    smalls = [x for x in flat if x["is_small"]]
    bigs.sort(key=lambda x: (-x["footprint"], -x["volume"]))
    smalls.sort(key=lambda x: -x["volume"])
    return bigs + smalls


def _bbox(placed):
    if not placed:
        return 0.0, (0.0, 0.0, 0.0)
    min_x = min(b["x"] for b in placed)
    max_x = max(b["x"] + b["dx"] for b in placed)
    min_y = min(b["y"] for b in placed)
    max_y = max(b["y"] + b["dy"] for b in placed)
    max_z = max(b["z"] + b["dz"] for b in placed)
    L = max_x - min_x
    W = max_y - min_y
    H = max_z
    return L * W * H / 1e9, (L, W, H)


def _bbox_volume(placed):
    if not placed:
        return 0.0
    min_x = min(b["x"] for b in placed)
    max_x = max(b["x"] + b["dx"] for b in placed)
    min_y = min(b["y"] for b in placed)
    max_y = max(b["y"] + b["dy"] for b in placed)
    max_z = max(b["z"] + b["dz"] for b in placed)
    return (max_x - min_x) * (max_y - min_y) * max_z / 1e9


def _compute_cog(placed):
    if not placed:
        return (0.0, 0.0, 0.0)

    total_w = sum(b["weight"] for b in placed)
    if total_w <= 1e-9:
        n = float(len(placed))
        cx = sum(b["x"] + b["dx"] / 2 for b in placed) / n
        cy = sum(b["y"] + b["dy"] / 2 for b in placed) / n
        cz = sum(b["z"] + b["dz"] / 2 for b in placed) / n
    else:
        cx = sum((b["x"] + b["dx"] / 2) * b["weight"] for b in placed) / total_w
        cy = sum((b["y"] + b["dy"] / 2) * b["weight"] for b in placed) / total_w
        cz = sum((b["z"] + b["dz"] / 2) * b["weight"] for b in placed) / total_w
    return (float(cx), float(cy), float(cz))


# ============================================================
#      Пост-оптимизация: заполнение пустот мелкими коробками
# ============================================================

def _find_gap_positions(placed, L, W, H):
    xs = {0.0, float(L)}
    ys = {0.0, float(W)}
    zs = {0.0}
    for p in placed:
        xs.add(p["x"]);              xs.add(p["x"] + p["dx"])
        ys.add(p["y"]);              ys.add(p["y"] + p["dy"])
        zs.add(p["z"]);              zs.add(p["z"] + p["dz"])
    return [(x, y, z) for x in sorted(xs)
            for y in sorted(ys) for z in sorted(zs)]


def _try_place_small_box(it, placed, L, W, H, max_w,
                         current_weight,
                         min_support_ratio=MIN_SUPPORT,
                         max_overhang_mm=0.0):
    a, b, c = it["a"], it["b"], it["c"]
    smallest = min(a, b, c)
    if smallest > H:
        return None

    candidates = _find_gap_positions(placed, L, W, H)
    candidates.sort(key=lambda c: (c[2], c[1], c[0]))

    best = None
    for oi, (dx, dy, dz) in enumerate(_orientations(it)):
        if oi >= 2:
            continue
        for (cx, cy, cz) in candidates:
            if cx + dx > L + OVERHANG_MM + 1e-6:
                continue
            if cy + dy > W + OVERHANG_MM + 1e-6:
                continue
            if cz + dz > H + 1e-6:
                continue

            if _collides_3d(cx, cy, cz, dx, dy, dz, placed):
                continue

            sup = _support_area(cx, cy, dx, dy, cz, placed)
            if sup < dx * dy * min_support_ratio - 1e-6:
                continue

            if not _overhang_ok(cx, cy, dx, dy, cz, placed,
                                max_overhang_mm):
                continue

            if current_weight + it["weight"] > max_w + 1e-6:
                continue

            key = (cz, cy, cx, oi)
            if best is None or key < best[0]:
                best = (key, (cx, cy, cz), (dx, dy, dz))

    if best is None:
        return None
    _, (x, y, z), (dx, dy, dz) = best
    return (x, y, z, dx, dy, dz)


def _optimize_pallet_with_small_boxes(placed, small_pool,
                                      L, W, H, max_w,
                                      min_support_ratio=MIN_SUPPORT,
                                      max_overhang_mm=0.0,
                                      time_limit=POST_OPT_TIME_LIMIT):
    if not small_pool:
        return placed, small_pool, 0

    pool = sorted(small_pool, key=lambda x: -x["volume"])
    current_weight = sum(b["weight"] for b in placed)
    added = 0
    t_start = _time.monotonic()

    progress = True
    while progress and pool:
        if _time.monotonic() - t_start > time_limit:
            break
        progress = False
        i = 0
        while i < len(pool):
            if _time.monotonic() - t_start > time_limit:
                break
            it = pool[i]
            result = _try_place_small_box(
                it, placed, L, W, H, max_w,
                current_weight,
                min_support_ratio=min_support_ratio,
                max_overhang_mm=max_overhang_mm,
            )
            if result is not None:
                x, y, z, dx, dy, dz = result
                placed.append({
                    "name": it["name"],
                    "x": float(x), "y": float(y), "z": float(z),
                    "dx": float(dx), "dy": float(dy), "dz": float(dz),
                    "weight": float(it["weight"]),
                })
                current_weight += it["weight"]
                pool.pop(i)
                added += 1
                progress = True
            else:
                i += 1

    return placed, pool, added


def _try_repack(placed, remaining, L, W, H, max_w, overhang,
                max_overhang_mm=0.0,
                min_support_ratio=MIN_SUPPORT,
                prefer_flat_first=True,
                side_first_layer=False,
                prefer_tight=False,
                max_passes=3):
    """
    Пробует переупаковать заново (placed + remaining) и оставить
    вариант с меньшим габаритным объёмом.
    """
    def _box_to_item(b):
        """placed-коробка (dx/dy/dz) → item (a/b/c)."""
        dims = sorted([b["dx"], b["dy"], b["dz"]], reverse=True)
        return {
            "name": b["name"],
            "model": b["name"].split("#")[0],
            "a": dims[0], "b": dims[1], "c": dims[2],
            "weight": b["weight"],
            "volume": dims[0] * dims[1] * dims[2],
            "footprint": dims[0] * dims[1],
            "is_small": dims[0] <= SMALL_MAX_DIM,
        }

    def _already_item(x):
        """remaining-элемент уже в формате item (a/b/c)."""
        # проверим, что у него есть нужные поля
        return ("a" in x and "b" in x and "c" in x
                and "volume" in x and "weight" in x)

    all_items = []
    for b in placed:
        all_items.append(_box_to_item(b))
    for r in remaining:
        if _already_item(r):
            all_items.append(r)
        else:
            # на всякий случай — если формат другой,
            # пробуем вытащить размеры
            try:
                dims = sorted([r["dx"], r["dy"], r["dz"]], reverse=True)
                all_items.append({
                    "name": r["name"],
                    "model": r["name"].split("#")[0],
                    "a": dims[0], "b": dims[1], "c": dims[2],
                    "weight": r["weight"],
                    "volume": dims[0] * dims[1] * dims[2],
                    "footprint": dims[0] * dims[1],
                    "is_small": dims[0] <= SMALL_MAX_DIM,
                })
            except (KeyError, TypeError):
                continue

    all_items.sort(key=lambda x: (-x["volume"], -x["weight"]))

    best_placed = list(placed)
    best_remaining = list(remaining)
    best_vol = _bbox_volume(placed)
    best_weight = sum(b["weight"] for b in best_placed)

    tight = prefer_tight
    for _pass in range(max_passes):
        allow_small_on_floor = not any(not x["is_small"] for x in all_items)
        new_placed, new_rem, new_w = _pack_one_pallet(
            all_items, L, W, H, max_w, overhang,
            allow_small_on_floor,
            max_overhang_mm=max_overhang_mm,
            min_support_ratio=min_support_ratio,
            prefer_flat_first=prefer_flat_first,
            side_first_layer=side_first_layer,
            prefer_tight=tight,
        )
        new_vol = _bbox_volume(new_placed)
        # принимаем, если стало плотнее и уложили не меньше
        if new_vol < best_vol - 1e-6 and len(new_placed) >= len(best_placed):
            best_vol = new_vol
            best_placed = new_placed
            best_remaining = new_rem
            best_weight = new_w
        tight = not tight  # чередуем приоритеты

    return best_placed, best_remaining, best_weight, best_vol


def pack_items(pallet_L, pallet_W, pallet_H, pallet_max_weight, items,
               overhang=OVERHANG_MM, max_per_group=MAX_PALLETS_PER_GROUP,
               max_overhang_mm=0.0,
               require_full_support=False,
               prefer_flat_first=True,
               group_by_model=False,
               side_first_layer_groups=None,
               pallet_overrides=None,
               post_optimize=False,
               prefer_tight=False,
               repack=False):
    """
    prefer_tight: True — прижимаем коробки к соседним при укладке.
    repack: True — после укладки пробуем переупаковать паллету
                   с меньшим габаритным объёмом.
    """
    if side_first_layer_groups is None:
        side_first_layer_groups = set()
    side_first_layer_groups = set(int(g) for g in side_first_layer_groups)

    if pallet_overrides is None:
        pallet_overrides = {}

    min_support_ratio = FULL_SUPPORT if require_full_support else MIN_SUPPORT

    groups = {}
    for it in items:
        g = int(it.get("pallet_group", 1) or 1)
        groups.setdefault(g, []).append(it)

    pallets = []
    unpacked_all = []
    for g in sorted(groups.keys()):
        ov = pallet_overrides.get(g) or {}
        try:
            L_g = float(ov.get("L", pallet_L))
            W_g = float(ov.get("W", pallet_W))
            H_g = float(ov.get("H", pallet_H))
            MW_g = float(ov.get("max_weight", pallet_max_weight))
        except (TypeError, ValueError):
            L_g, W_g, H_g, MW_g = (pallet_L, pallet_W,
                                   pallet_H, pallet_max_weight)

        flat = _prepare_flat(groups[g], group_by_model=group_by_model)
        if not flat:
            continue
        side_first = g in side_first_layer_groups
        remaining = flat
        attempt = 0
        while remaining and attempt < max_per_group:
            attempt += 1
            allow_small_on_floor = not any(not x["is_small"] for x in remaining)
            placed, new_remaining, weight = _pack_one_pallet(
                remaining, L_g, W_g, H_g, MW_g,
                overhang, allow_small_on_floor,
                max_overhang_mm=max_overhang_mm,
                min_support_ratio=min_support_ratio,
                prefer_flat_first=prefer_flat_first,
                side_first_layer=side_first,
                prefer_tight=prefer_tight,
            )
            if not placed:
                break

            # Переупаковка в конце
            if repack:
                placed2, new_remaining2, weight2, _vol2 = _try_repack(
                    placed, new_remaining,
                    L_g, W_g, H_g, MW_g, overhang,
                    max_overhang_mm=max_overhang_mm,
                    min_support_ratio=min_support_ratio,
                    prefer_flat_first=prefer_flat_first,
                    side_first_layer=side_first,
                    prefer_tight=prefer_tight,
                )
                if len(placed2) >= len(placed):
                    placed = placed2
                    new_remaining = new_remaining2
                    weight = weight2

            # Пост-оптимизация мелкими коробками
            if post_optimize and new_remaining:
                small_pool = [r for r in new_remaining
                              if r.get("is_small")]
                if small_pool:
                    placed, remaining_small, added_small = \
                        _optimize_pallet_with_small_boxes(
                            placed, small_pool,
                            L_g, W_g, H_g, MW_g,
                            min_support_ratio=min_support_ratio,
                            max_overhang_mm=max_overhang_mm,
                        )
                    if added_small:
                        placed_names = {b["name"] for b in placed}
                        new_remaining = [r for r in new_remaining
                                         if r["name"] not in placed_names]
                        weight = sum(b["weight"] for b in placed)

            vol = sum(b["dx"] * b["dy"] * b["dz"] / 1e9 for b in placed)
            h = max((b["z"] + b["dz"] for b in placed), default=0.0)
            bbox_vol, bbox_size = _bbox(placed)

            cx, cy, cz = _compute_cog(placed)
            off_x = cx - L_g / 2.0
            off_y = cy - W_g / 2.0
            cog_stable = (
                abs(off_x) <= L_g * COG_WARN_FRACTION + 1e-6 and
                abs(off_y) <= W_g * COG_WARN_FRACTION + 1e-6
            )

            pallets.append({
                "group": int(g),
                "attempt": attempt,
                "placed": placed,
                "weight_kg": float(weight),
                "volume_m3": float(vol),
                "height_mm": float(h),
                "bbox_volume_m3": float(bbox_vol),
                "bbox_size_mm": bbox_size,
                "side_first_layer": side_first,
                "cog_mm": (cx, cy, cz),
                "cog_offset_mm": (off_x, off_y),
                "cog_stable": bool(cog_stable),
                "L": float(L_g),
                "W": float(W_g),
                "H": float(H_g),
                "max_weight": float(MW_g),
            })
            if len(new_remaining) == len(remaining):
                remaining = new_remaining
                break
            remaining = new_remaining
        for r in remaining:
            unpacked_all.append({
                "name": r["name"],
                "dims": (r["a"], r["b"], r["c"]),
                "weight": r["weight"],
                "group": int(g),
            })
    return pallets, unpacked_all


# ---------- 3D ----------

def _make_box_mesh(x, y, z, sx, sy, sz):
    v = np.array([
        [x,      y,      z     ],
        [x + sx, y,      z     ],
        [x + sx, y + sy, z     ],
        [x,      y + sy, z     ],
        [x,      y,      z + sz],
        [x + sx, y,      z + sz],
        [x + sx, y + sy, z + sz],
        [x,      y + sy, z + sz],
    ], dtype=float)
    faces = np.array([
        [0, 1, 2], [0, 2, 3],
        [4, 6, 5], [4, 7, 6],
        [0, 4, 5], [0, 5, 1],
        [1, 5, 6], [1, 6, 2],
        [2, 6, 7], [2, 7, 3],
        [3, 7, 4], [3, 4, 0],
    ], dtype=int)
    return gl.MeshData(vertexes=v, faces=faces)


PALETTE = [
    (0.90, 0.30, 0.30, 0.90),
    (0.30, 0.75, 0.35, 0.90),
    (0.30, 0.55, 0.95, 0.90),
    (0.95, 0.80, 0.25, 0.90),
    (0.85, 0.40, 0.85, 0.90),
    (0.35, 0.85, 0.85, 0.90),
    (0.95, 0.55, 0.20, 0.90),
    (0.55, 0.35, 0.85, 0.90),
]


def _mat_to_np(m):
    if m is None:
        return None
    try:
        arr = np.asarray(m, dtype=float)
        if arr.size == 16:
            return arr.reshape(4, 4)
    except Exception:
        pass
    try:
        data = m.data()
        arr = np.array(list(data), dtype=float)
        if arr.size == 16:
            return arr.reshape(4, 4).T
    except Exception:
        pass
    try:
        rows = []
        for i in range(4):
            row = m[i]
            rows.append([row.x(), row.y(), row.z(), row.w()])
        return np.array(rows, dtype=float)
    except Exception:
        pass
    return None


class Viewer3D(gl.GLViewWidget):
    def __init__(self):
        super().__init__()
        self.setBackgroundColor("#1e1e1e")
        self._box_items = []
        self._pallet_items = []
        self._labels = []
        self._fallback_list = []
        self._use_fallback = False
        self._show_labels = True
        self._model_colors = {}

        grid = gl.GLGridItem()
        grid.setSize(15000, 15000)
        grid.setSpacing(200, 200)
        grid.setColor((100, 100, 100, 80))
        self.addItem(grid)

        self._t = QTimer(self)
        self._t.timeout.connect(self.update)
        self._t.start(50)

    def _clear(self):
        for it in self._box_items + self._pallet_items:
            self.removeItem(it)
        self._box_items.clear()
        self._pallet_items.clear()
        self._labels.clear()
        self._fallback_list.clear()
        self._model_colors.clear()

    def clear_view(self):
        self._clear()

    def render_screenshot(self, scale=3):
        base_w = max(self.width(), 1)
        base_h = max(self.height(), 1)
        target_w = max(int(base_w * scale), 1600)
        target_h = max(int(target_w * base_h / base_w), 900)

        img = None
        try:
            arr = self.renderToArray((target_w, target_h))
            if arr is not None and arr.size > 0:
                arr = np.ascontiguousarray(arr)
                hh, ww, _ = arr.shape
                img = QImage(
                    arr.tobytes(), ww, hh, ww * 4,
                    QImage.Format_RGBA8888
                ).copy()
        except Exception:
            img = None

        if img is None or img.isNull():
            try:
                img = self.grabFramebuffer()
            except Exception:
                return None
            if img is None or img.isNull():
                return None

        self._draw_labels_on_image(img, scale)
        return img

    def _draw_labels_on_image(self, img, scale=1.0):
        if not self._show_labels:
            return
        w = img.width()
        h = img.height()

        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        base_size = max(int(9 * scale), 9)
        font = QFont("Arial", base_size, QFont.Bold)
        painter.setFont(font)

        if self._use_fallback or not self._labels:
            if self._fallback_list:
                fm = painter.fontMetrics()
                line_h = fm.height() + 4
                text_w = max(fm.horizontalAdvance(t) for t in self._fallback_list)
                pad = 10
                box_w = text_w + pad * 2
                box_h = line_h * len(self._fallback_list) + pad * 2
                rect = QRectF(14, 14, box_w, box_h)
                painter.setBrush(QBrush(QColor(0, 0, 0, 200)))
                painter.setPen(QPen(QColor(255, 220, 0), 2))
                painter.drawRoundedRect(rect, 8, 8)
                painter.setPen(QColor(255, 220, 0))
                y = 14 + pad
                for txt in self._fallback_list:
                    painter.drawText(
                        QRectF(14 + pad, y, text_w, line_h),
                        Qt.AlignLeft | Qt.AlignVCenter, txt
                    )
                    y += line_h
        else:
            proj, view = self._get_matrices()
            if proj is not None and view is not None:
                fm = painter.fontMetrics()
                for text, pos3 in self._labels:
                    p = np.array([pos3[0], pos3[1], pos3[2], 1.0], dtype=float)
                    clip = proj @ (view @ p)
                    if abs(clip[3]) < 1e-6:
                        continue
                    ndc = clip[:3] / clip[3]
                    sx = (ndc[0] * 0.5 + 0.5) * w
                    sy = (1.0 - (ndc[1] * 0.5 + 0.5)) * h

                    tw = fm.horizontalAdvance(text)
                    th = fm.height()
                    pad = int(5 * scale)
                    rect = QRectF(sx - tw / 2.0 - pad,
                                  sy - th / 2.0 - pad,
                                  tw + pad * 2.0,
                                  th + pad * 2.0)
                    painter.setBrush(QBrush(QColor(0, 0, 0, 220)))
                    painter.setPen(QPen(QColor(255, 220, 0),
                                        max(2, int(2 * scale))))
                    painter.drawRoundedRect(rect, 6, 6)
                    painter.setPen(QColor(255, 220, 0))
                    painter.drawText(rect, Qt.AlignCenter, text)

        if self._model_colors:
            fm = painter.fontMetrics()
            legend_pad = int(10 * scale)
            swatch_w = int(28 * scale)
            swatch_h = fm.height()
            gap = int(8 * scale)
            line_h = max(swatch_h, fm.height()) + int(6 * scale)
            text_w = max(fm.horizontalAdvance(n) for n in self._model_colors)
            box_w = legend_pad * 2 + swatch_w + gap + text_w
            box_h = legend_pad * 2 + line_h * len(self._model_colors)
            margin = int(14 * scale)
            rx = w - box_w - margin
            ry = h - box_h - margin

            painter.setBrush(QBrush(QColor(0, 0, 0, 210)))
            painter.setPen(QPen(QColor(255, 220, 0), max(2, int(2 * scale))))
            painter.drawRoundedRect(QRectF(rx, ry, box_w, box_h),
                                    int(6 * scale), int(6 * scale))
            y = ry + legend_pad
            for name, (r, g, b) in self._model_colors.items():
                painter.setBrush(QBrush(QColor(r, g, b)))
                painter.setPen(QPen(QColor(255, 255, 255, 180),
                                    max(1, int(scale))))
                painter.drawRect(QRectF(rx + legend_pad, y, swatch_w, swatch_h))
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(
                    QRectF(rx + legend_pad + swatch_w + gap, y,
                           text_w, swatch_h),
                    Qt.AlignLeft | Qt.AlignVCenter, name
                )
                y += line_h

        painter.end()

    def set_show_labels(self, value: bool):
        self._show_labels = bool(value)
        self.update()

    def _get_matrices(self):
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        vp = (0, 0, w, h)
        proj = None
        for args in [(vp, vp), (vp,), (), (vp, vp, 0.1, 100000.0)]:
            try:
                proj = self.projectionMatrix(*args)
                break
            except Exception:
                continue
        view = None
        for name in ("viewMatrix", "getViewMatrix"):
            fn = getattr(self, name, None)
            if fn is None:
                continue
            for args in [(), (vp,), (vp, vp)]:
                try:
                    view = fn(*args)
                    break
                except Exception:
                    continue
            if view is not None:
                break
        return _mat_to_np(proj), _mat_to_np(view)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._show_labels:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Arial", 9, QFont.Bold)
        painter.setFont(font)

        if self._use_fallback or not self._labels:
            if self._fallback_list:
                painter.setBrush(QBrush(QColor(0, 0, 0, 200)))
                painter.setPen(QPen(QColor(255, 220, 0), 2))
                fm = painter.fontMetrics()
                line_h = fm.height() + 4
                text_w = max(fm.horizontalAdvance(t) for t in self._fallback_list)
                pad = 8
                box_w = text_w + pad * 2
                box_h = line_h * len(self._fallback_list) + pad * 2
                rect = QRectF(10, 10, box_w, box_h)
                painter.drawRoundedRect(rect, 6, 6)
                painter.setPen(QColor(255, 220, 0))
                y = 10 + pad
                for txt in self._fallback_list:
                    painter.drawText(
                        QRectF(10 + pad, y, text_w, line_h),
                        Qt.AlignLeft | Qt.AlignVCenter, txt
                    )
                    y += line_h
            painter.end()
            return

        proj, view = self._get_matrices()
        if proj is None or view is None:
            self._use_fallback = True
            painter.end()
            self.update()
            return

        w, h = self.width(), self.height()
        fm = painter.fontMetrics()
        for text, pos3 in self._labels:
            p = np.array([pos3[0], pos3[1], pos3[2], 1.0], dtype=float)
            clip = proj @ (view @ p)
            if abs(clip[3]) < 1e-6:
                continue
            ndc = clip[:3] / clip[3]
            sx = (ndc[0] * 0.5 + 0.5) * w
            sy = (1.0 - (ndc[1] * 0.5 + 0.5)) * h
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            pad = 4
            rect = QRectF(sx - tw / 2.0 - pad,
                          sy - th / 2.0 - pad,
                          tw + pad * 2.0,
                          th + pad * 2.0)
            painter.setBrush(QBrush(QColor(0, 0, 0, 215)))
            painter.setPen(QPen(QColor(255, 220, 0), 2))
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(QColor(255, 220, 0))
            painter.drawText(rect, Qt.AlignCenter, text)
        painter.end()

    def show_layout(self, pallet_L, pallet_W, pallet_H, pallets,
                    pallet_thickness=150, overhang=OVERHANG_MM,
                    show_labels=True):
        self._clear()
        self._use_fallback = False
        self._show_labels = bool(show_labels)

        all_names = set()
        for p in pallets:
            for b in p["placed"]:
                all_names.add(b["name"].split("#")[0])
        model_names = sorted(all_names)
        name_to_color = {
            n: PALETTE[i % len(PALETTE)] for i, n in enumerate(model_names)
        }
        self._model_colors = {
            n: (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))
            for n, c in name_to_color.items()
        }

        current_x = 0.0
        max_W = float(pallet_W)
        max_H = float(pallet_H)

        for i, pallet in enumerate(pallets):
            pl_L = float(pallet.get("L", pallet_L))
            pl_W = float(pallet.get("W", pallet_W))
            pl_H = float(pallet.get("H", pallet_H))
            offset_x = current_x

            base_mesh = _make_box_mesh(
                offset_x, 0, -pallet_thickness,
                pl_L, pl_W, pallet_thickness
            )
            base = gl.GLMeshItem(
                meshdata=base_mesh, smooth=False,
                color=(0.55, 0.40, 0.25, 0.95),
                drawEdges=True, edgeColor=(0.25, 0.18, 0.10, 1.0),
            )
            self.addItem(base)
            self._pallet_items.append(base)

            zone_mesh = _make_box_mesh(
                offset_x - overhang, -overhang, 0,
                pl_L + 2 * overhang, pl_W + 2 * overhang, pl_H
            )
            zone = gl.GLMeshItem(
                meshdata=zone_mesh, smooth=False,
                drawFaces=False, drawEdges=True,
                edgeColor=(0.55, 0.85, 1.0, 0.85),
            )
            self.addItem(zone)
            self._pallet_items.append(zone)

            for b in pallet["placed"]:
                model = b["name"].split("#")[0]
                color = name_to_color[model]
                mesh = _make_box_mesh(
                    offset_x + b["x"], b["y"], b["z"],
                    b["dx"], b["dy"], b["dz"]
                )
                item = gl.GLMeshItem(
                    meshdata=mesh, smooth=False, color=color,
                    drawEdges=True, edgeColor=(0, 0, 0, 0.7),
                )
                self.addItem(item)
                self._box_items.append(item)

            bx, by, bz = pallet["bbox_size_mm"]
            if bx > 0 and by > 0 and bz > 0:
                min_x = min(b["x"] for b in pallet["placed"])
                min_y = min(b["y"] for b in pallet["placed"])
                bbox_mesh = _make_box_mesh(
                    offset_x + min_x, min_y, 0, bx, by, bz
                )
                bbox_item = gl.GLMeshItem(
                    meshdata=bbox_mesh, smooth=False,
                    drawFaces=False, drawEdges=True,
                    edgeColor=(1.0, 0.55, 0.1, 0.9),
                )
                self.addItem(bbox_item)
                self._pallet_items.append(bbox_item)

            label_text = f"Паллет №{pallet['group']}"
            if pallet["attempt"] > 1:
                label_text += f" (+{pallet['attempt'] - 1})"
            if pallet.get("side_first_layer"):
                label_text += " [1-й слой: бок]"
            max_h = max(
                (b["z"] + b["dz"] for b in pallet["placed"]),
                default=0.0
            )
            self._labels.append((
                label_text,
                (offset_x + pl_L / 2.0,
                 pl_W / 2.0,
                 max_h + pl_H * 0.12)
            ))
            self._fallback_list.append(
                f"{label_text} — {len(pallet['placed'])} кор."
            )

            current_x += pl_L + PALLET_GAP_MM
            if pl_W > max_W:
                max_W = pl_W
            if pl_H > max_H:
                max_H = pl_H

        total_w = max(current_x - PALLET_GAP_MM, 1.0)
        cx = total_w / 2.0
        cy = max_W / 2.0
        cz = max(max_H / 2.0, pallet_thickness)
        diag = max(total_w, max_W, max_H)
        self.setCameraPosition(
            pos=QVector3D(cx, cy, cz),
            distance=diag * 1.6,
            elevation=25,
            azimuth=-45,
        )
        self.update()

    def get_legend(self, pallets):
        names = set()
        if isinstance(pallets, list):
            for p in pallets:
                if isinstance(p, dict) and "placed" in p:
                    for b in p["placed"]:
                        names.add(b["name"].split("#")[0])
                else:
                    names.add(p["name"].split("#")[0])
        model_names = sorted(names)
        legend = {}
        for i, n in enumerate(model_names):
            c = PALETTE[i % len(PALETTE)]
            legend[n] = (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))
        return legend