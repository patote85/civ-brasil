from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h3

from pipeline.civ.rules import LensRule
from pipeline.grid.h3_grid import H3_RESOLUTION, MunicipioHexRow
from pipeline.reconcile.points import AssignedPoint
from pipeline.sources._common import atomic_write_bytes
from pipeline.sources.ibge_malhas import Municipio
from pipeline.types import CdMun, H3Index, UfCode


def _compute_quantile_breaks(values: Sequence[float | None], k: int = 5) -> list[float]:
    positives = sorted(v for v in values if v is not None and v > 0.0)
    if not positives:
        return [0.0] * (k - 1)
    n = len(positives)
    breaks: list[float] = []
    for step in range(1, k):
        pos = min(n - 1, int(math.floor((n * step) / k)))
        breaks.append(round(positives[pos], 2))
    return breaks


def _select_hubs(
    municipios: Sequence[Municipio],
    pop_by_mun: Mapping[CdMun, float] | None,
    pib_by_mun: Mapping[CdMun, float] | None,
    project_xy: Any,
    max_hubs: int = 9,
    min_dist: float = 48.0,
) -> list[dict[str, Any]]:
    if not pop_by_mun:
        return []
    ranked = sorted(
        municipios,
        key=lambda m: (-pop_by_mun.get(CdMun(m.cd_mun), 0.0), m.cd_mun),
    )
    selected: list[dict[str, Any]] = []
    for mun in ranked:
        if len(selected) >= max_hubs:
            break
        pt = mun.geometry.representative_point()
        hx, hy = project_xy(pt.x, pt.y)
        if any(math.hypot(hx - s["x"], hy - s["y"]) < min_dist for s in selected):
            continue
        cd = CdMun(mun.cd_mun)
        selected.append(
            {
                "cd_mun": mun.cd_mun,
                "nome": mun.nome,
                "x": round(hx, 1),
                "y": round(hy, 1),
                "pop": int(round(pop_by_mun.get(cd, 0.0))),
                "pib_mil": round(pib_by_mun.get(cd, 0.0), 1) if pib_by_mun else 0.0,
            }
        )
    return selected


def export_uf_web_bundle(
    uf: UfCode,
    municipios: Sequence[Municipio],
    mun_hex_rows: Sequence[MunicipioHexRow],
    hex_metrics: Mapping[str, Mapping[H3Index, float | None]],
    rules: Sequence[LensRule],
    output_dir: Path,
    pop_by_mun: Mapping[CdMun, float] | None = None,
    pib_by_mun: Mapping[CdMun, float] | None = None,
    points: Sequence[AssignedPoint] | None = None,
    rejected_points_count: int = 0,
    city_profiles: Sequence[dict[str, Any]] | None = None,
) -> dict[str, int]:
    grouped_rows: dict[str, list[MunicipioHexRow]] = defaultdict(list)
    for row in mun_hex_rows:
        grouped_rows[row.h3].append(row)

    ordered_cells = sorted(grouped_rows.keys())
    nomes_by_cd = {m.cd_mun: m.nome for m in municipios}
    unique_muns = sorted({nomes_by_cd[r.cd_mun] for r in mun_hex_rows})
    mun_to_idx = {name: i for i, name in enumerate(unique_muns)}

    centers_latlng = [h3.cell_to_latlng(c) for c in ordered_cells]
    mean_lat = sum(lat for lat, _ in centers_latlng) / max(1, len(centers_latlng))
    cos_lat = math.cos(math.radians(mean_lat))

    raw_boundaries: list[list[tuple[float, float]]] = []
    raw_centers: list[tuple[float, float]] = []
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    for cell, (clat, clon) in zip(ordered_cells, centers_latlng, strict=True):
        pts = [(lon * cos_lat, -lat) for lat, lon in h3.cell_to_boundary(cell)]
        for x, y in pts:
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
        raw_boundaries.append(pts)
        raw_centers.append((clon * cos_lat, -clat))

    span_x = max(1e-9, max_x - min_x)
    span_y = max(1e-9, max_y - min_y)
    scale = min(920.0 / span_x, 640.0 / span_y)
    off_x = (1000.0 - span_x * scale) / 2.0
    off_y = (700.0 - span_y * scale) / 2.0

    def project_xy(lon: float, lat: float) -> tuple[float, float]:
        return ((lon * cos_lat - min_x) * scale + off_x, (-lat - min_y) * scale + off_y)

    cx_list: list[float] = []
    cy_list: list[float] = []
    area_list: list[float] = []
    mun_idx_list: list[list[int]] = []
    sum_offs = [[0.0, 0.0] for _ in range(6)]

    for cell, (rcx, rcy), bpts in zip(ordered_cells, raw_centers, raw_boundaries, strict=True):
        px = (rcx - min_x) * scale + off_x
        py = (rcy - min_y) * scale + off_y
        cx_list.append(round(px, 1))
        cy_list.append(round(py, 1))
        for i in range(6):
            vx = (bpts[i][0] - min_x) * scale + off_x
            vy = (bpts[i][1] - min_y) * scale + off_y
            sum_offs[i][0] += vx - px
            sum_offs[i][1] += vy - py

        rows = sorted(grouped_rows[cell], key=lambda item: item.cd_mun)
        area_list.append(round(sum(r.area_km2 for r in rows), 1))
        mun_idx_list.append([mun_to_idx[nomes_by_cd[r.cd_mun]] for r in rows])

    n_cells = max(1, len(ordered_cells))
    hex_offsets = [[round(a / n_cells, 2), round(b / n_cells, 2)] for a, b in sum_offs]

    def _sum_metric(col: str) -> float:
        m = hex_metrics.get(col)
        if not m:
            return 0.0
        return round(sum(v for v in m.values() if v is not None), 1)

    yields_summary = {
        "pop": int(round(_sum_metric("pop"))),
        "pib_mil": _sum_metric("pib"),
        "vab_ind_mil": _sum_metric("vab_ind"),
        "vab_agro_mil": _sum_metric("vab_agro"),
        "vab_serv_mil": _sum_metric("vab_serv"),
        "vab_adm_mil": _sum_metric("vab_adm"),
    }

    hubs = _select_hubs(municipios, pop_by_mun, pib_by_mun, project_xy)

    grid_payload = {
        "uf": uf,
        "resolution": H3_RESOLUTION,
        "hex_count": len(ordered_cells),
        "mun_count": len(municipios),
        "total_area_km2": round(sum(r.area_km2 for r in mun_hex_rows), 2),
        "hex_offsets": hex_offsets,
        "yields": yields_summary,
        "hubs": hubs,
        "municipios": unique_muns,
        "h3": ordered_cells,
        "cx": cx_list,
        "cy": cy_list,
        "area_km2": area_list,
        "mun_idx": mun_idx_list,
    }

    written_bytes: dict[str, int] = {}
    grid_bytes = json.dumps(grid_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    grid_path = output_dir / "grid.json"
    atomic_write_bytes(grid_path, grid_bytes)
    written_bytes["grid.json"] = len(grid_bytes)

    lentes_dir = output_dir / "lentes"
    index_entries: list[dict[str, Any]] = []

    for rule in rules:
        metric_map = hex_metrics.get(rule.column)
        if metric_map is None:
            raise ValueError(
                f"Coluna {rule.column!r} exigida pela lente {rule.id!r} não encontrada"
            )
        values: list[float | None] = []
        for cell in ordered_cells:
            raw_val = metric_map.get(H3Index(cell))
            values.append(None if raw_val is None else round(raw_val, 2))
        non_null = [v for v in values if v is not None]
        total_val = round(sum(non_null), 2) if rule.kind == "sum" else None
        min_val = min(non_null) if non_null else 0.0
        max_val = max(non_null) if non_null else 0.0
        breaks = _compute_quantile_breaks(values, k=5)

        lens_payload = {
            "id": rule.id,
            "unit": rule.unit,
            "kind": rule.kind,
            "total": total_val,
            "min": min_val,
            "max": max_val,
            "breaks": breaks,
            "values": values,
        }
        lens_bytes = json.dumps(
            lens_payload,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        atomic_write_bytes(lentes_dir / f"{rule.id}.json", lens_bytes)
        written_bytes[f"lentes/{rule.id}.json"] = len(lens_bytes)

        index_entries.append(
            {
                "id": rule.id,
                "civ_name": rule.civ_name,
                "br_name": rule.br_name,
                "source_id": rule.source_id,
                "source_label": rule.source_label,
                "ano_ref": rule.ano_ref,
                "kind": rule.kind,
                "unit": rule.unit,
                "scale": rule.scale,
                "palette": rule.palette,
                "note": rule.note,
            }
        )

    index_payload = {"uf": uf, "lenses": index_entries}
    index_bytes = json.dumps(
        index_payload,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    atomic_write_bytes(lentes_dir / "index.json", index_bytes)
    written_bytes["lentes/index.json"] = len(index_bytes)

    cell_to_idx = {cell: i for i, cell in enumerate(ordered_cells)}
    mun_by_cd = {CdMun(m.cd_mun): m for m in municipios}

    if points is not None:
        usinas_out: list[dict[str, Any]] = []
        portos_out: list[dict[str, Any]] = []
        hospitais_raw: list[dict[str, Any]] = []
        for pt in points:
            px, py = project_xy(pt.lon, pt.lat)
            entry: dict[str, Any] = {
                "name": pt.name,
                "cat": pt.category,
                "val": round(pt.value, 2),
                "unit": pt.unit,
                "x": round(px, 1),
                "y": round(py, 1),
                "hex_idx": cell_to_idx.get(str(pt.h3), -1),
            }
            if pt.kind == "usina":
                usinas_out.append(entry)
            elif pt.kind == "porto":
                portos_out.append(entry)
            else:
                hospitais_raw.append(entry)
        hospitais_raw.sort(key=lambda h: (-float(h["val"]), str(h["name"])))
        hospitais_out = hospitais_raw[:250]

        pontos_payload = {
            "uf": uf,
            "rejected_count": rejected_points_count,
            "usinas": usinas_out,
            "portos": portos_out,
            "hospitais": hospitais_out,
        }
        pontos_bytes = json.dumps(
            pontos_payload,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        atomic_write_bytes(output_dir / "pontos.json", pontos_bytes)
        written_bytes["pontos.json"] = len(pontos_bytes)

    if city_profiles is not None:
        enriched_cities: list[dict[str, Any]] = []
        for city in city_profiles:
            cd = CdMun(str(city["cd_mun"]))
            mun = mun_by_cd.get(cd)
            if mun is None:
                continue
            rep = mun.geometry.representative_point()
            cx_city, cy_city = project_xy(rep.x, rep.y)
            m_name = mun.nome
            m_idx = mun_to_idx.get(m_name, -1)
            hex_candidates = [i for i, ids in enumerate(mun_idx_list) if m_idx in ids]
            best_hex = (
                min(
                    hex_candidates,
                    key=lambda i: (cx_list[i] - cx_city) ** 2 + (cy_list[i] - cy_city) ** 2,
                )
                if hex_candidates
                else -1
            )
            enriched = dict(city)
            enriched["x"] = round(cx_city, 1)
            enriched["y"] = round(cy_city, 1)
            enriched["hex_idx"] = best_hex
            enriched_cities.append(enriched)

        cities_payload = {"uf": uf, "cities": enriched_cities}
        cities_bytes = json.dumps(
            cities_payload,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        atomic_write_bytes(output_dir / "cities.json", cities_bytes)
        written_bytes["cities.json"] = len(cities_bytes)

    return written_bytes
