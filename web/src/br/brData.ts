import {
  type LensMetadata,
  type PositionalLensData,
  type UfGridDataset,
  parseUfGridDataset,
} from "../data";

export interface BrUfSummary {
  readonly uf: string;
  readonly nome: string;
  readonly mun_count: number;
  readonly hex_count: number;
  readonly pop: number;
  readonly pib_mil: number;
  readonly area_km2: number;
  readonly cx: number;
  readonly cy: number;
}

export interface BrOverviewDataset {
  readonly grid: UfGridDataset;
  readonly ufDom: readonly string[];
  readonly ufs: readonly BrUfSummary[];
  readonly lenses: Readonly<Record<string, PositionalLensData>>;
}

export const BR_UF_NAMES: Readonly<Record<string, string>> = {
  AC: "Acre",
  AL: "Alagoas",
  AM: "Amazonas",
  AP: "Amapá",
  BA: "Bahia",
  CE: "Ceará",
  DF: "Distrito Federal",
  ES: "Espírito Santo",
  GO: "Goiás",
  MA: "Maranhão",
  MG: "Minas Gerais",
  MS: "Mato Grosso do Sul",
  MT: "Mato Grosso",
  PA: "Pará",
  PB: "Paraíba",
  PE: "Pernambuco",
  PI: "Piauí",
  PR: "Paraná",
  RJ: "Rio de Janeiro",
  RN: "Rio Grande do Norte",
  RO: "Rondônia",
  RR: "Roraima",
  RS: "Rio Grande do Sul",
  SC: "Santa Catarina",
  SE: "Sergipe",
  SP: "São Paulo",
  TO: "Tocantins",
};

export const BR_BASE_LENSES: readonly LensMetadata[] = [
  {
    id: "ouro",
    civ_name: "Ouro",
    br_name: "PIB per capita",
    source_id: "ibge_pib",
    source_label: "IBGE PIB dos Municípios 2021 + Censo 2022",
    ano_ref: 2021,
    kind: "rate",
    unit: "R$/hab",
    scale: "quantile",
    palette: "gold",
    note: "PIB municipal distribuído dasimetricamente via Grade Estatística 1 km.",
  },
  {
    id: "populacao",
    civ_name: "Cidadãos",
    br_name: "População",
    source_id: "ibge_censo",
    source_label: "IBGE Censo 2022 + Grade Estatística 1 km",
    ano_ref: 2022,
    kind: "sum",
    unit: "hab",
    scale: "quantile",
    palette: "citizens",
    note: "Conservação estrita por UF e município sobre a Grade 1 km do IBGE.",
  },
  {
    id: "producao",
    civ_name: "Produção",
    br_name: "PIB Total",
    source_id: "ibge_pib",
    source_label: "IBGE PIB dos Municípios 2021",
    ano_ref: 2021,
    kind: "sum",
    unit: "R$ mil",
    scale: "quantile",
    palette: "production",
    note: "PIB total municipal em R$ mil conciliado para a malha hexagonal H3.",
  },
  {
    id: "densidade",
    civ_name: "Densidade",
    br_name: "Densidade Demográfica",
    source_id: "ibge_censo",
    source_label: "IBGE Censo 2022 + Malha Municipal",
    ano_ref: 2022,
    kind: "rate",
    unit: "hab/km²",
    scale: "quantile",
    palette: "food",
    note: "Habitantes por km² calculados sobre projeção equivalente de área.",
  },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseCompactBrLens(
  raw: unknown,
  meta: LensMetadata,
  expectedHexCount: number,
): PositionalLensData {
  if (!isRecord(raw) || !Array.isArray(raw.values) || !Array.isArray(raw.breaks)) {
    throw new Error(`Lente compacta inválida para ${meta.id}`);
  }
  const values: (number | null)[] = raw.values.map((v) => {
    if (v === null) return null;
    if (typeof v === "number" && Number.isFinite(v)) return v;
    throw new Error(`Valor inválido na lente ${meta.id}`);
  });
  if (values.length !== expectedHexCount) {
    throw new Error(`Lente ${meta.id} tem ${values.length} valores, esperado ${expectedHexCount}`);
  }
  const breaks = raw.breaks.map((b) => {
    if (typeof b !== "number" || !Number.isFinite(b)) {
      throw new Error(`Quebra inválida na lente ${meta.id}`);
    }
    return b;
  });
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  let sum = 0;
  for (const v of values) {
    if (v === null) continue;
    if (v < min) min = v;
    if (v > max) max = v;
    sum += v;
  }
  if (!Number.isFinite(min)) min = 0;
  if (!Number.isFinite(max)) max = 0;
  return {
    id: meta.id,
    unit: meta.unit,
    kind: meta.kind,
    total: meta.kind === "sum" ? sum : null,
    min,
    max,
    breaks,
    values,
  };
}

export function parseBrOverview(raw: unknown): BrOverviewDataset {
  if (!isRecord(raw)) {
    throw new Error("br_res3.json deve ser um objeto JSON");
  }
  const grid = parseUfGridDataset(raw);
  if (!Array.isArray(raw.uf_dom) || raw.uf_dom.length !== grid.hex_count) {
    throw new Error("Campo 'uf_dom' inválido em br_res3.json");
  }
  const ufDom = raw.uf_dom.map((u) => {
    if (typeof u !== "string" || u.length !== 2) {
      throw new Error("UF inválida em 'uf_dom'");
    }
    return u;
  });
  if (!Array.isArray(raw.ufs)) {
    throw new Error("Campo 'ufs' inválido em br_res3.json");
  }
  const ufs: BrUfSummary[] = raw.ufs.map((entry) => {
    if (!isRecord(entry) || typeof entry.uf !== "string" || typeof entry.nome !== "string") {
      throw new Error("Resumo de UF inválido em br_res3.json");
    }
    return {
      uf: entry.uf,
      nome: entry.nome,
      mun_count: Number(entry.mun_count ?? 0),
      hex_count: Number(entry.hex_count ?? 0),
      pop: Number(entry.pop ?? 0),
      pib_mil: Number(entry.pib_mil ?? 0),
      area_km2: Number(entry.area_km2 ?? 0),
      cx: Number(entry.cx ?? 500),
      cy: Number(entry.cy ?? 350),
    };
  });
  if (!isRecord(raw.lenses)) {
    throw new Error("Campo 'lenses' inválido em br_res3.json");
  }
  const lenses: Record<string, PositionalLensData> = {};
  for (const meta of BR_BASE_LENSES) {
    const rawLens = raw.lenses[meta.id];
    if (rawLens !== undefined) {
      lenses[meta.id] = parseCompactBrLens(rawLens, meta, grid.hex_count);
    }
  }
  return { grid, ufDom, ufs, lenses };
}
