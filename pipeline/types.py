from __future__ import annotations

from typing import Literal, NewType

import h3

CdMun = NewType("CdMun", str)
H3Index = NewType("H3Index", str)

UfCode = Literal[
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

UF_IBGE_CODES: dict[UfCode, str] = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}

_SIDRA_MISSING = frozenset({"", "-", "..", "...", "X", "x"})


def parse_cd_mun(raw: object) -> CdMun:
    code = str(raw).strip()
    if len(code) != 7 or not code.isdigit():
        raise ValueError(f"Código IBGE de município inválido: {raw!r}")
    return CdMun(code)


def parse_h3_index(raw: object) -> H3Index:
    cell = str(raw).strip()
    if not h3.is_valid_cell(cell):
        raise ValueError(f"Índice H3 inválido: {raw!r}")
    return H3Index(cell)


def parse_uf_code(raw: str) -> UfCode:
    normalized = raw.strip().upper()
    for code in UF_IBGE_CODES:
        if code == normalized:
            return code
    raise ValueError(f"UF inválida: {raw!r}")


def parse_sidra_number(raw: object) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text in _SIDRA_MISSING:
        return None
    normalized = text.replace(",", ".")
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"Valor numérico SIDRA inválido: {raw!r}") from exc
