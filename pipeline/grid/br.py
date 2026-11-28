from __future__ import annotations

import json
import math
import os
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h3

from pipeline.grid.h3_grid import H3_RESOLUTION, MunicipioHexRow
from pipeline.sources.ibge_malhas import Municipio
from pipeline.types import CdMun, UfCode

BR_OFFICIAL_AREA_KM2 = 8_510_417.771
BR_OFFICIAL_POP_2022 = 203_080_756
H3_BR_OVERVIEW_RESOLUTION = 3

UF_NAMES: dict[UfCode, str] = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AM": "Amazonas",
    "AP": "Amapá",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso",
    "PA": "Pará",
    "PB": "Paraíba",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "PR": "Paraná",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RO": "Rondônia",
    "RR": "Roraima",
    "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina",
    "SE": "Sergipe",
    "SP": "São Paulo",
    "TO": "Tocantins",
}


@dataclass(frozen=True, slots=True)
class UfHexRecord:
    uf: UfCode
    h3: str
    area_km2: float
    pop: float
    pib_mil: float
    pib_agro_mil: float
    pib_ind_mil: float
    pib_serv_mil: float
    pib_adm_mil: float
    mun_count: int


@dataclass(frozen=True, slots=True)
class BrRes3Hex:
    h3: str
    uf_dom: UfCode
    ufs: tuple[UfCode, ...]
    area_km2: float
    pop: float
    pib_mil: float
    pib_agro_mil: float
    pib_ind_mil: float
    pib_serv_mil: float
    pib_adm_mil: float
    mun_count: int


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _compact_num(val: float, digits: int = 1) -> int | float:
    rounded = round(val, digits)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def _quantile_breaks(values: Sequence[float | None], k: int = 5) -> list[float]:
    positives = sorted(v for v in values if v is not None and math.isfinite(v) and v > 0.0)
    if not positives:
        return [0.0] * (k - 1)
    n = len(positives)
    breaks: list[float] = []
    for step in range(1, k):
        pos = min(n - 1, int(math.floor((n * step) / k)))
        breaks.append(round(positives[pos], 2))
    return breaks


def aggregate_res5_to_res3(records: Sequence[UfHexRecord]) -> list[BrRes3Hex]:
    grouped: dict[str, list[UfHexRecord]] = defaultdict(list)
    for rec in records:
        parent = h3.cell_to_parent(rec.h3, H3_BR_OVERVIEW_RESOLUTION)
        grouped[parent].append(rec)

    result: list[BrRes3Hex] = []
    for parent in sorted(grouped):
        items = grouped[parent]
        area_by_uf: dict[UfCode, float] = defaultdict(float)
        for item in items:
            area_by_uf[item.uf] += item.area_km2

        uf_dom = min(area_by_uf.keys(), key=lambda u: (-area_by_uf[u], u))
        ufs = tuple(sorted(area_by_uf.keys()))
        result.append(
            BrRes3Hex(
                h3=parent,
                uf_dom=uf_dom,
                ufs=ufs,
                area_km2=sum(i.area_km2 for i in items),
                pop=sum(i.pop for i in items),
                pib_mil=sum(i.pib_mil for i in items),
                pib_agro_mil=sum(i.pib_agro_mil for i in items),
                pib_ind_mil=sum(i.pib_ind_mil for i in items),
                pib_serv_mil=sum(i.pib_serv_mil for i in items),
                pib_adm_mil=sum(i.pib_adm_mil for i in items),
                mun_count=sum(i.mun_count for i in items),
            )
        )
    return result


def _project_cells_equirectangular(
    cells: Sequence[str],
) -> tuple[list[float], list[float], list[list[float]], Any]:
    centers_latlng = [h3.cell_to_latlng(c) for c in cells]
    mean_lat = sum(lat for lat, _ in centers_latlng) / max(1, len(centers_latlng))
    cos_lat = math.cos(math.radians(mean_lat))

    raw_boundaries: list[list[tuple[float, float]]] = []
    raw_centers: list[tuple[float, float]] = []
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    for cell, (clat, clon) in zip(cells, centers_latlng, strict=True):
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
    sum_offs = [[0.0, 0.0] for _ in range(6)]
    for (rcx, rcy), bpts in zip(raw_centers, raw_boundaries, strict=True):
        px = (rcx - min_x) * scale + off_x
        py = (rcy - min_y) * scale + off_y
        cx_list.append(round(px, 1))
        cy_list.append(round(py, 1))
        if len(bpts) == 6:
            for i in range(6):
                vx = (bpts[i][0] - min_x) * scale + off_x
                vy = (bpts[i][1] - min_y) * scale + off_y
                sum_offs[i][0] += vx - px
                sum_offs[i][1] += vy - py

    n_hex6 = max(1, sum(1 for b in raw_boundaries if len(b) == 6))
    hex_offsets = [
        [round(sum_offs[i][0] / n_hex6, 2), round(sum_offs[i][1] / n_hex6, 2)]
        for i in range(6)
    ]
    return cx_list, cy_list, hex_offsets, project_xy


def export_br_res3_web_bundle(
    hexes: Sequence[BrRes3Hex],
    uf_summaries: Sequence[Mapping[str, Any]],
    output_path: Path,
) -> None:
    cells = [h.h3 for h in hexes]
    cx_list, cy_list, hex_offsets, _project_xy = _project_cells_equirectangular(cells)

    uf_cx_acc: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for h, cx, cy in zip(hexes, cx_list, cy_list, strict=True):
        uf_cx_acc[h.uf_dom].append((cx, cy))

    sorted_summaries = sorted(uf_summaries, key=lambda s: str(s["uf"]))
    enriched_ufs: list[dict[str, Any]] = []
    hubs: list[dict[str, Any]] = []
    uf_labels: list[str] = []
    uf_to_idx: dict[str, int] = {}

    for idx, summary in enumerate(sorted_summaries):
        uf_code = str(summary["uf"])
        uf_nome = str(summary.get("nome", uf_code))
        uf_labels.append(f"{uf_nome} ({uf_code})")
        uf_to_idx[uf_code] = idx
        pts = uf_cx_acc.get(uf_code, [])
        cx = round(sum(p[0] for p in pts) / len(pts), 1) if pts else 500.0
        cy = round(sum(p[1] for p in pts) / len(pts), 1) if pts else 350.0
        enriched_ufs.append({**dict(summary), "cx": cx, "cy": cy})
        hubs.append(
            {
                "cd_mun": uf_code,
                "nome": uf_code,
                "x": cx,
                "y": cy,
                "pop": int(round(float(summary.get("pop", 0)))),
                "pib_mil": round(float(summary.get("pib_mil", 0.0)), 1),
            }
        )

    mun_idx = [[uf_to_idx[u] for u in h.ufs if u in uf_to_idx] for h in hexes]
    pib_pc_vals = [
        round((h.pib_mil * 1000.0) / h.pop, 1) if h.pop > 0.0 else None for h in hexes
    ]
    pop_vals = [round(h.pop, 1) for h in hexes]
    pib_vals = [round(h.pib_mil, 1) for h in hexes]
    dens_vals = [round(h.pop / h.area_km2, 2) if h.area_km2 > 0.0 else None for h in hexes]

    total_pop = int(round(sum(h.pop for h in hexes)))
    total_pib_mil = round(sum(h.pib_mil for h in hexes), 1)
    total_area_km2 = round(sum(h.area_km2 for h in hexes), 2)
    total_muns = sum(int(s.get("mun_count", 0)) for s in sorted_summaries)

    payload: dict[str, Any] = {
        "uf": "BR",
        "resolution": H3_BR_OVERVIEW_RESOLUTION,
        "hex_count": len(hexes),
        "mun_count": total_muns,
        "total_area_km2": total_area_km2,
        "hex_offsets": hex_offsets,
        "yields": {
            "pop": total_pop,
            "pib_mil": total_pib_mil,
            "pib_pc": round((total_pib_mil * 1000.0) / total_pop, 1) if total_pop > 0 else 0.0,
        },
        "hubs": hubs,
        "municipios": uf_labels,
        "ufs": enriched_ufs,
        "h3": cells,
        "cx": cx_list,
        "cy": cy_list,
        "area_km2": [_compact_num(h.area_km2, 1) for h in hexes],
        "mun_idx": mun_idx,
        "uf_dom": [h.uf_dom for h in hexes],
        "lenses": {
            "ouro": {
                "id": "ouro",
                "values": pib_pc_vals,
                "breaks": _quantile_breaks(pib_pc_vals),
            },
            "populacao": {
                "id": "populacao",
                "values": pop_vals,
                "breaks": _quantile_breaks(pop_vals),
            },
            "producao": {
                "id": "producao",
                "values": pib_vals,
                "breaks": _quantile_breaks(pib_vals),
            },
            "densidade": {
                "id": "densidade",
                "values": dens_vals,
                "breaks": _quantile_breaks(dens_vals),
            },
        },
    }
    _atomic_write_json(output_path, payload)


def export_uf_compact_grid_and_base_lenses(
    uf: UfCode,
    municipios: Sequence[Municipio],
    mun_hex_rows: Sequence[MunicipioHexRow],
    pop_by_hex: Mapping[str, float],
    pib_by_hex: Mapping[str, float],
    pop_by_mun: Mapping[CdMun, float],
    pib_by_mun: Mapping[CdMun, float],
    out_dir: Path,
) -> dict[str, Path]:
    grouped_rows: dict[str, list[MunicipioHexRow]] = defaultdict(list)
    for row in mun_hex_rows:
        grouped_rows[row.h3].append(row)

    ordered_cells = sorted(grouped_rows.keys())
    nomes_by_cd = {m.cd_mun: m.nome for m in municipios}
    unique_muns = sorted({nomes_by_cd[r.cd_mun] for r in mun_hex_rows})
    mun_to_idx = {name: i for i, name in enumerate(unique_muns)}

    cx_list, cy_list, hex_offsets, project_xy = _project_cells_equirectangular(ordered_cells)
    area_list: list[int | float] = []
    mun_idx_list: list[list[int]] = []
    area_exact: list[float] = []
    for cell in ordered_cells:
        rows = sorted(grouped_rows[cell], key=lambda item: item.cd_mun)
        a_sum = sum(r.area_km2 for r in rows)
        area_exact.append(a_sum)
        area_list.append(_compact_num(a_sum, 1))
        mun_idx_list.append([mun_to_idx[nomes_by_cd[r.cd_mun]] for r in rows])

    ranked_muns = sorted(
        municipios,
        key=lambda m: (-pop_by_mun.get(CdMun(m.cd_mun), 0.0), m.cd_mun),
    )
    hubs: list[dict[str, Any]] = []
    for mun in ranked_muns:
        if len(hubs) >= 9:
            break
        pt = mun.geometry.representative_point()
        hx, hy = project_xy(pt.x, pt.y)
        if any(math.hypot(hx - s["x"], hy - s["y"]) < 48.0 for s in hubs):
            continue
        cd = CdMun(mun.cd_mun)
        hubs.append(
            {
                "cd_mun": mun.cd_mun,
                "nome": mun.nome,
                "x": round(hx, 1),
                "y": round(hy, 1),
                "pop": int(round(pop_by_mun.get(cd, 0.0))),
                "pib_mil": round(pib_by_mun.get(cd, 0.0), 1),
            }
        )

    total_pop = int(round(sum(pop_by_hex.get(c, 0.0) for c in ordered_cells)))
    total_pib_mil = round(sum(pib_by_hex.get(c, 0.0) for c in ordered_cells), 1)
    total_area_km2 = round(sum(area_exact), 2)

    uf_slug = uf.lower()
    grid_path = out_dir / f"{uf_slug}_grid.json"
    _atomic_write_json(
        grid_path,
        {
            "uf": uf,
            "resolution": H3_RESOLUTION,
            "hex_count": len(ordered_cells),
            "mun_count": len(municipios),
            "total_area_km2": total_area_km2,
            "hex_offsets": hex_offsets,
            "yields": {
                "pop": total_pop,
                "pib_mil": total_pib_mil,
                "pib_pc": round((total_pib_mil * 1000.0) / total_pop, 1) if total_pop > 0 else 0.0,
            },
            "hubs": hubs,
            "municipios": unique_muns,
            "h3": ordered_cells,
            "cx": cx_list,
            "cy": cy_list,
            "area_km2": area_list,
            "mun_idx": mun_idx_list,
        },
    )

    lenses_dir = out_dir / f"{uf_slug}_lenses"
    pop_vals = [_compact_num(pop_by_hex.get(c, 0.0), 1) for c in ordered_cells]
    pib_vals = [_compact_num(pib_by_hex.get(c, 0.0), 1) for c in ordered_cells]
    pib_pc_vals = [
        _compact_num((pib_by_hex.get(c, 0.0) * 1000.0) / pop_by_hex.get(c, 0.0), 1)
        if pop_by_hex.get(c, 0.0) > 0.0
        else None
        for c in ordered_cells
    ]
    dens_vals = [
        _compact_num(pop_by_hex.get(c, 0.0) / a, 2) if a > 0.0 else None
        for c, a in zip(ordered_cells, area_exact, strict=True)
    ]

    written: dict[str, Path] = {"grid": grid_path}
    for lens_id, vals in (
        ("ouro", pib_pc_vals),
        ("populacao", pop_vals),
        ("producao", pib_vals),
        ("densidade", dens_vals),
    ):
        l_path = lenses_dir / f"{lens_id}.json"
        _atomic_write_json(
            l_path,
            {
                "id": lens_id,
                "values": vals,
                "breaks": _quantile_breaks([float(v) if v is not None else None for v in vals]),
            },
        )
        written[f"lens_{lens_id}"] = l_path
    return written
