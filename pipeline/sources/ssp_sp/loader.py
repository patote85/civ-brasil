from __future__ import annotations

import contextlib
import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.sources._common import (
    ArtifactSync,
    StreamDownloader,
    atomic_write_bytes,
    default_fetcher,
    ensure_raw_artifact_stream,
    normalize_pt_name,
)
from pipeline.types import CdMun

SSP_SP_MUNICIPIOS_URL = "https://www.ssp.sp.gov.br/v1/Municipios/RecuperaMunicipios"
SSP_SP_OCORRENCIAS_URL = (
    "https://www.ssp.sp.gov.br/v1/OcorrenciasAnuais/recuperaDadosMunicipio?idMunicipio="
)
LOW_POPULATION_THRESHOLD = 20_000

SSP_NAME_ALIASES: dict[str, str] = {
    "moji mirim": "mogi mirim",
    "moji guacu": "mogi guacu",
    "sao luis do paraitinga": "sao luiz do paraitinga",
    "embu": "embu das artes",
    "florinia": "florinea",
    "brodosqui": "brodowski",
}


@dataclass(frozen=True, slots=True)
class SspSpRecord:
    cd_mun: CdMun
    ano: int
    homicidio: int
    furto: int
    roubo: int
    furto_veiculo: int
    roubo_veiculo: int
    homicidio_100k: float
    roubo_100k: float
    baixa_populacao: bool


def _fetch_ssp_sp_bundle(ano: int = 2025) -> bytes:
    import http.client
    import threading

    raw_muns = json.loads(default_fetcher(SSP_SP_MUNICIPIOS_URL).decode("utf-8"))
    mun_list = raw_muns.get("data", [])
    if not isinstance(mun_list, list) or not mun_list:
        raise ValueError("Lista de municípios da SSP-SP vazia")

    local_state = threading.local()

    def _get_json(path: str) -> dict[str, Any]:
        for attempt in range(3):
            conn: http.client.HTTPSConnection | None = getattr(local_state, "conn", None)
            if conn is None:
                conn = http.client.HTTPSConnection("www.ssp.sp.gov.br", timeout=20)
                local_state.conn = conn
            try:
                conn.request(
                    "GET",
                    path,
                    headers={"User-Agent": "civ-brasil/0.4", "Connection": "keep-alive"},
                )
                resp = conn.getresponse()
                body = resp.read()
                if resp.status == 200 and body:
                    return dict(json.loads(body.decode("utf-8")))
            except (OSError, http.client.HTTPException, json.JSONDecodeError):
                with contextlib.suppress(OSError):
                    conn.close()
                local_state.conn = None
                if attempt == 2:
                    raise
        return {"data": []}

    def _fetch_one(entry: dict[str, Any]) -> dict[str, Any]:
        mun_id = int(entry["idMunicipio"])
        nome = str(entry.get("nome") or "").strip()
        payload = _get_json(f"/v1/OcorrenciasAnuais/recuperaDadosMunicipio?idMunicipio={mun_id}")
        rows = payload.get("data", [])
        chosen: dict[str, Any] | None = None
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and int(row.get("ano", 0)) == ano:
                    chosen = row
                    break
            if chosen is None and rows and isinstance(rows[0], dict):
                chosen = rows[0]
        chosen = chosen or {}
        return {
            "idMunicipio": mun_id,
            "nome": nome,
            "ano": int(chosen.get("ano", ano)),
            "homicidio": int(chosen.get("homicidio", 0) or 0),
            "furto": int(chosen.get("furto", 0) or 0),
            "roubo": int(chosen.get("roubo", 0) or 0),
            "furtoVeiculo": int(chosen.get("furtoVeiculo", 0) or 0),
            "rouboVeiculo": int(chosen.get("rouboVeiculo", 0) or 0),
        }

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_fetch_one, mun_list))
    results.sort(key=lambda item: (str(item["nome"]), int(item["idMunicipio"])))
    bundle = {"ano": ano, "municipios": results}
    return json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _ssp_stream_downloader(_url: str, dest: Path) -> None:
    payload = _fetch_ssp_sp_bundle(ano=2025)
    atomic_write_bytes(dest, payload)


def _resolve_cd_mun(raw_name: str, lookup: Mapping[str, CdMun]) -> CdMun | None:
    norm = normalize_pt_name(raw_name)
    if norm in lookup:
        return lookup[norm]
    alias = SSP_NAME_ALIASES.get(norm)
    if alias and alias in lookup:
        return lookup[alias]
    compact = "".join(ch for ch in norm if ch.isalnum())
    for key, cd in lookup.items():
        if "".join(ch for ch in key if ch.isalnum()) == compact:
            return cd
    return None


def load_ssp_sp_from_file(
    path: Path,
    mun_names_by_cd: Mapping[CdMun, str],
    pop_by_mun: Mapping[CdMun, int],
) -> dict[CdMun, SspSpRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ano = int(payload.get("ano", 2025))
    rows = payload.get("municipios", [])
    if not isinstance(rows, list):
        raise ValueError(f"Formato inválido em {path}")

    lookup: dict[str, CdMun] = {normalize_pt_name(n): cd for cd, n in mun_names_by_cd.items()}
    by_cd: dict[CdMun, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cd = _resolve_cd_mun(str(row.get("nome") or ""), lookup)
        if cd is not None:
            by_cd[cd] = row

    records: dict[CdMun, SspSpRecord] = {}
    for cd in sorted(mun_names_by_cd.keys()):
        row = by_cd.get(cd, {})
        pop = max(1, int(pop_by_mun.get(cd, 0)))
        hom = max(0, int(row.get("homicidio", 0) or 0))
        furto = max(0, int(row.get("furto", 0) or 0))
        roubo = max(0, int(row.get("roubo", 0) or 0))
        f_veic = max(0, int(row.get("furtoVeiculo", 0) or 0))
        r_veic = max(0, int(row.get("rouboVeiculo", 0) or 0))
        records[cd] = SspSpRecord(
            cd_mun=cd,
            ano=int(row.get("ano", ano)),
            homicidio=hom,
            furto=furto,
            roubo=roubo,
            furto_veiculo=f_veic,
            roubo_veiculo=r_veic,
            homicidio_100k=round(100_000.0 * hom / pop, 2),
            roubo_100k=round(100_000.0 * roubo / pop, 2),
            baixa_populacao=pop < LOW_POPULATION_THRESHOLD,
        )
    return records


def ensure_ssp_sp_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    downloader: StreamDownloader | None = None,
) -> ArtifactSync:
    from pipeline.sources._common import upsert_manifest_entry

    sync = ensure_raw_artifact_stream(
        source_id="ssp_sp",
        filename="sp_ocorrencias_anuais_2025.json",
        url=SSP_SP_MUNICIPIOS_URL,
        downloader=downloader or _ssp_stream_downloader,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    upsert_manifest_entry(
        manifest_path,
        sync,
        {
            "orgao": "SSP-SP",
            "ano_ref": 2025,
            "licenca": "Dados Abertos SSP-SP",
            "cobertura": "SP",
        },
    )
    return sync
