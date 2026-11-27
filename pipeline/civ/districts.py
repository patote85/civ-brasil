from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from pipeline.sources.rais import RaisDivisionRecord
from pipeline.types import CdMun

CNAE_DIV_DISTRICT_NAMES: dict[str, str] = {
    "01": "Agropecuária",
    "02": "Silvicultura e Madeira",
    "03": "Pesca e Aquicultura",
    "05": "Extração Mineral",
    "06": "Petróleo e Gás",
    "07": "Mineração Metálica",
    "08": "Mineração Não Metálica",
    "09": "Apoio à Extração e Pré-Sal",
    "10": "Agroindústria Alimentar",
    "11": "Indústria de Bebidas",
    "13": "Polo Têxtil",
    "14": "Polo de Confecções",
    "15": "Polo Calçadista e Couro",
    "16": "Indústria Madeireira",
    "17": "Papel e Celulose",
    "18": "Indústria Gráfica",
    "19": "Refino e Biocombustíveis",
    "20": "Polo Químico",
    "21": "Polo Farmacêutico",
    "22": "Borracha e Plástico",
    "23": "Cerâmica e Minerais",
    "24": "Metalurgia",
    "25": "Metalmecânica",
    "26": "Eletroeletrônica",
    "27": "Máquinas Elétricas",
    "28": "Máquinas e Equipamentos",
    "29": "Polo Automotivo",
    "30": "Aeroespacial e Transporte",
    "31": "Polo Moveleiro",
    "32": "Manufatura Diversa",
    "33": "Manutenção Industrial",
    "35": "Energia e Eletricidade",
    "36": "Saneamento e Água",
    "41": "Construção Civil",
    "42": "Obras de Infraestrutura",
    "45": "Comércio Automotivo",
    "46": "Comércio Atacadista",
    "47": "Comércio Varejista",
    "49": "Logística Terrestre",
    "50": "Transporte Aquaviário",
    "51": "Aviação",
    "52": "Logística Portuária e Armazenagem",
    "55": "Hotelaria e Turismo",
    "56": "Alimentação e Gastronomia",
    "58": "Mídia e Editorial",
    "61": "Telecomunicações",
    "62": "Tecnologia da Informação",
    "63": "Dados e Serviços Digitais",
    "64": "Centro Financeiro",
    "65": "Seguros e Previdência",
    "66": "Serviços Financeiros",
    "68": "Mercado Imobiliário",
    "69": "Serviços Jurídicos e Contábeis",
    "70": "Sedes e Consultoria",
    "71": "Engenharia e Arquitetura",
    "72": "Campus e Pesquisa (P&D)",
    "73": "Publicidade e Mercado",
    "74": "Design e Serviços Técnicos",
    "82": "Serviços Empresariais",
    "84": "Administração Pública",
    "85": "Educação e Universidades",
    "86": "Polo de Saúde",
    "92": "Loterias e Jogos",
    "99": "Organismos Internacionais",
}

CITIZEN_MACRO_SECTORS: dict[str, str] = {
    "A": "Agropecuária",
    "B": "Indústria",
    "C": "Indústria",
    "D": "Infraestrutura",
    "E": "Infraestrutura",
    "F": "Construção",
    "G": "Comércio",
    "H": "Logística",
    "I": "Serviços",
    "J": "TI & Finanças",
    "K": "TI & Finanças",
    "L": "Serviços",
    "M": "Serviços",
    "N": "Serviços",
    "O": "Setor Público",
    "P": "Educação & Saúde",
    "Q": "Educação & Saúde",
    "R": "Serviços",
    "S": "Serviços",
    "T": "Serviços",
    "U": "Serviços",
    "Z": "Outros",
}


@dataclass(frozen=True, slots=True)
class DistrictScore:
    cd_mun: CdMun
    cnae_div: str
    cnae_secao: str
    district_name: str
    vinculos: int
    share_mun: float
    share_uf: float
    ql: float


def district_label_for_division(cnae_div: str) -> str:
    return CNAE_DIV_DISTRICT_NAMES.get(cnae_div, f"CNAE {cnae_div}")


def compute_location_quotients(
    records: list[RaisDivisionRecord],
    all_cd_muns: list[CdMun],
) -> tuple[list[DistrictScore], dict[str, float]]:
    mun_totals: dict[CdMun, int] = defaultdict(int)
    div_totals: dict[str, int] = defaultdict(int)
    by_mun_div: dict[tuple[CdMun, str], tuple[int, str]] = {}

    for rec in records:
        mun_totals[rec.cd_mun] += rec.vinculos
        if rec.cnae_div != "00":
            div_totals[rec.cnae_div] += rec.vinculos
            prev_v, _ = by_mun_div.get((rec.cd_mun, rec.cnae_div), (0, rec.cnae_secao))
            by_mun_div[(rec.cd_mun, rec.cnae_div)] = (prev_v + rec.vinculos, rec.cnae_secao)

    uf_total = sum(mun_totals.values())
    active_divs = sorted(div for div, tot in div_totals.items() if tot > 0)

    uf_ql: dict[str, float] = {}
    for div in active_divs:
        share_uf = div_totals[div] / uf_total if uf_total > 0 else 0.0
        uf_ql[div] = (share_uf / share_uf) if share_uf > 0.0 else 0.0

    scores: list[DistrictScore] = []
    for cd in sorted(all_cd_muns):
        m_tot = mun_totals.get(cd, 0)
        if m_tot <= 0 or uf_total <= 0:
            scores.append(
                DistrictScore(
                    cd_mun=cd,
                    cnae_div="00",
                    cnae_secao="Z",
                    district_name="Sem vínculo formal",
                    vinculos=0,
                    share_mun=0.0,
                    share_uf=0.0,
                    ql=0.0,
                )
            )
            continue

        for div in active_divs:
            vinc, secao = by_mun_div.get((cd, div), (0, "Z"))
            if vinc <= 0:
                continue
            share_mun = vinc / m_tot
            share_uf = div_totals[div] / uf_total
            ql = (share_mun / share_uf) if share_uf > 0.0 else 0.0
            scores.append(
                DistrictScore(
                    cd_mun=cd,
                    cnae_div=div,
                    cnae_secao=secao,
                    district_name=district_label_for_division(div),
                    vinculos=vinc,
                    share_mun=round(share_mun, 6),
                    share_uf=round(share_uf, 6),
                    ql=round(ql, 4),
                )
            )

    scores.sort(key=lambda s: (s.cd_mun, -s.ql, -s.vinculos, s.cnae_div))
    return scores, uf_ql


def select_city_districts(
    scores: list[DistrictScore],
    min_ql: float = 2.0,
    min_vinculos: int = 150,
    max_per_city: int = 4,
) -> dict[CdMun, list[DistrictScore]]:
    by_mun: dict[CdMun, list[DistrictScore]] = defaultdict(list)
    for sc in scores:
        if sc.cnae_div == "00":
            continue
        if sc.ql >= min_ql and sc.vinculos >= min_vinculos:
            by_mun[sc.cd_mun].append(sc)

    # Fallback for small cities: top QL >= min_ql with at least 25 jobs.
    by_mun_small: dict[CdMun, list[DistrictScore]] = defaultdict(list)
    for sc in scores:
        if sc.cnae_div == "00":
            continue
        if sc.ql >= min_ql and sc.vinculos >= 25:
            by_mun_small[sc.cd_mun].append(sc)

    result: dict[CdMun, list[DistrictScore]] = {}
    all_muns = set(by_mun.keys()) | set(by_mun_small.keys())
    for cd in all_muns:
        chosen = by_mun.get(cd) or by_mun_small.get(cd) or []
        chosen.sort(key=lambda s: (-s.ql, -s.vinculos))
        result[cd] = chosen[:max_per_city]
    return result


def compute_citizen_sector_shares(
    records: list[RaisDivisionRecord],
) -> dict[CdMun, list[dict[str, object]]]:
    by_mun: dict[CdMun, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rec in records:
        macro = CITIZEN_MACRO_SECTORS.get(rec.cnae_secao, "Serviços")
        by_mun[rec.cd_mun][macro] += rec.vinculos

    profiles: dict[CdMun, list[dict[str, object]]] = {}
    for cd, counts in by_mun.items():
        total = sum(counts.values())
        if total <= 0:
            profiles[cd] = []
            continue
        items = [
            {
                "sector": sector,
                "vinculos": vinc,
                "pct": round(100.0 * vinc / total, 1),
            }
            for sector, vinc in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            if vinc > 0
        ]
        profiles[cd] = items[:6]
    return profiles
