from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import h3

from pipeline.grid.h3_grid import H3_RESOLUTION
from pipeline.types import H3Index

PointKind = Literal["usina", "porto", "hospital"]


@dataclass(frozen=True, slots=True)
class AssignedPoint:
    kind: PointKind
    name: str
    category: str
    value: float
    unit: str
    h3: H3Index
    lat: float
    lon: float
    cd_mun: str


@dataclass(frozen=True, slots=True)
class RejectedPoint:
    source: str
    name: str
    reason: str
    raw_lat: str
    raw_lon: str


def assign_points_to_grid(
    items: list[tuple[PointKind, str, str, float, str, float, float, str]],
    valid_hexes: set[H3Index],
    source_name: str,
    resolution: int = H3_RESOLUTION,
) -> tuple[list[AssignedPoint], list[RejectedPoint]]:
    accepted: list[AssignedPoint] = []
    rejected: list[RejectedPoint] = []

    for kind, name, category, value, unit, lat, lon, cd_mun in items:
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            rejected.append(
                RejectedPoint(
                    source=source_name,
                    name=name,
                    reason="coordenada_fora_faixa_wgs84",
                    raw_lat=str(lat),
                    raw_lon=str(lon),
                )
            )
            continue

        cell = H3Index(h3.latlng_to_cell(lat, lon, resolution))
        if cell not in valid_hexes:
            rejected.append(
                RejectedPoint(
                    source=source_name,
                    name=name,
                    reason="fora_da_grade_uf",
                    raw_lat=f"{lat:.5f}",
                    raw_lon=f"{lon:.5f}",
                )
            )
            continue

        accepted.append(
            AssignedPoint(
                kind=kind,
                name=name,
                category=category,
                value=value,
                unit=unit,
                h3=cell,
                lat=lat,
                lon=lon,
                cd_mun=cd_mun,
            )
        )

    return accepted, rejected


def sum_point_values_by_hex(
    points: list[AssignedPoint],
    ordered_hexes: list[H3Index],
) -> dict[H3Index, float]:
    totals: dict[H3Index, float] = defaultdict(float)
    for pt in points:
        totals[pt.h3] += pt.value
    return {cell: round(totals.get(cell, 0.0), 4) for cell in ordered_hexes}
