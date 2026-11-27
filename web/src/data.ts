export type VisualMode = "atlas" | "civ";

export interface UfYields {
  readonly pop: number;
  readonly pib_mil: number;
  readonly vab_ind_mil: number;
  readonly vab_agro_mil: number;
  readonly vab_serv_mil: number;
  readonly vab_adm_mil: number;
}

export interface CityHub {
  readonly cd_mun: string;
  readonly nome: string;
  readonly x: number;
  readonly y: number;
  readonly pop: number;
  readonly pib_mil: number;
}

export interface UfGridDataset {
  readonly uf: string;
  readonly resolution: number;
  readonly hex_count: number;
  readonly mun_count: number;
  readonly total_area_km2: number;
  readonly hex_offsets: readonly (readonly [number, number])[];
  readonly yields: UfYields;
  readonly hubs: readonly CityHub[];
  readonly municipios: readonly string[];
  readonly h3: readonly string[];
  readonly cx: readonly number[];
  readonly cy: readonly number[];
  readonly area_km2: readonly number[];
  readonly mun_idx: readonly (readonly number[])[];
}

export interface LensMetadata {
  readonly id: string;
  readonly civ_name: string;
  readonly br_name: string;
  readonly source_id: string;
  readonly source_label: string;
  readonly ano_ref: number;
  readonly kind: "sum" | "rate";
  readonly unit: string;
  readonly scale: "quantile" | "linear";
  readonly palette: string;
  readonly note: string;
}

export interface LensIndex {
  readonly uf: string;
  readonly lenses: readonly LensMetadata[];
}

export interface PositionalLensData {
  readonly id: string;
  readonly unit: string;
  readonly kind: "sum" | "rate";
  readonly total: number | null;
  readonly min: number;
  readonly max: number;
  readonly breaks: readonly number[];
  readonly values: readonly (number | null)[];
}

export interface PaletteStop {
  readonly label: string;
  readonly color: string;
}

export const NO_DATA_COLOR = "#334155";

const PALETTES: Record<string, { atlas: readonly string[]; civ: readonly string[] }> = {
  gold: {
    atlas: ["#1e293b", "#4a4326", "#997321", "#d4a226", "#fde047"],
    civ: ["#293845", "#6b5b2a", "#b5892a", "#dfb038", "#ffe066"],
  },
  production: {
    atlas: ["#1b2430", "#4c3d34", "#8f4e28", "#cf6a23", "#fb923c"],
    civ: ["#2d343d", "#5c4a3d", "#9e5c34", "#d47330", "#f59c42"],
  },
  food: {
    atlas: ["#1a2b24", "#284d37", "#3d7a4a", "#6ca148", "#b9cc52"],
    civ: ["#263b2a", "#3d6b3b", "#659442", "#99b848", "#d6cf5c"],
  },
  citizens: {
    atlas: ["#172536", "#1e4a6d", "#2076a8", "#38bdf8", "#a5f3fc"],
    civ: ["#1f2e3d", "#254d6e", "#2b7aa8", "#48b5e0", "#9ee7ff"],
  },
};

export function getPaletteColors(palette: string, mode: VisualMode): readonly string[] {
  const entry = PALETTES[palette] ?? PALETTES.gold;
  if (!entry) {
    return ["#1e293b", "#4a4326", "#997321", "#d4a226", "#fde047"];
  }
  return mode === "civ" ? entry.civ : entry.atlas;
}

export function bucketIndexForValue(value: number | null, breaks: readonly number[]): number {
  if (value === null || !Number.isFinite(value)) {
    return -1;
  }
  for (let i = 0; i < breaks.length; i++) {
    const threshold = breaks[i];
    if (threshold !== undefined && value <= threshold) {
      return i;
    }
  }
  return breaks.length;
}

export function colorForValue(
  value: number | null,
  breaks: readonly number[],
  palette: string,
  mode: VisualMode,
): string {
  const idx = bucketIndexForValue(value, breaks);
  if (idx < 0) {
    return NO_DATA_COLOR;
  }
  const colors = getPaletteColors(palette, mode);
  return colors[Math.min(idx, colors.length - 1)] ?? NO_DATA_COLOR;
}

export function formatPtBrCompact(value: number, unit: string): string {
  if (unit === "R$ mil") {
    const reais = value * 1000;
    if (reais >= 1e12) {
      return `R$ ${(reais / 1e12).toFixed(2).replace(".", ",")} tri`;
    }
    if (reais >= 1e9) {
      return `R$ ${(reais / 1e9).toFixed(1).replace(".", ",")} bi`;
    }
    if (reais >= 1e6) {
      return `R$ ${(reais / 1e6).toFixed(1).replace(".", ",")} mi`;
    }
    return `R$ ${Math.round(reais).toLocaleString("pt-BR")}`;
  }
  if (value >= 1e6) {
    return `${(value / 1e6).toFixed(2).replace(".", ",")}M`;
  }
  if (value >= 1e3) {
    return `${(value / 1e3).toFixed(1).replace(".", ",")}k`;
  }
  return Math.round(value).toLocaleString("pt-BR");
}

export function buildLegendBuckets(
  lens: PositionalLensData,
  palette: string,
  mode: VisualMode,
): PaletteStop[] {
  const colors = getPaletteColors(palette, mode);
  const stops: PaletteStop[] = [];
  for (let i = 0; i < colors.length; i++) {
    const prev = i === 0 ? lens.min : (lens.breaks[i - 1] ?? lens.min);
    const next = i < lens.breaks.length ? (lens.breaks[i] ?? lens.max) : lens.max;
    const label = `${formatPtBrCompact(prev, lens.unit)} – ${formatPtBrCompact(next, lens.unit)}`;
    stops.push({ label, color: colors[i] ?? NO_DATA_COLOR });
  }
  return stops;
}

export function normalizeSearchText(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

export interface MunicipalityMatch {
  readonly nome: string;
  readonly hexIndex: number;
}

export function searchMunicipalities(
  grid: UfGridDataset,
  query: string,
  limit = 20,
): MunicipalityMatch[] {
  const needle = normalizeSearchText(query);
  const matches: MunicipalityMatch[] = [];
  for (let mIdx = 0; mIdx < grid.municipios.length; mIdx++) {
    const nome = grid.municipios[mIdx];
    if (!nome) continue;
    if (needle && !normalizeSearchText(nome).includes(needle)) continue;
    const hexIndex = grid.mun_idx.findIndex((ids) => ids.includes(mIdx));
    if (hexIndex >= 0) {
      matches.push({ nome, hexIndex });
      if (matches.length >= limit) break;
    }
  }
  return matches;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((x) => typeof x === "number" && Number.isFinite(x));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((x) => typeof x === "string");
}

export function parseUfGridDataset(raw: unknown): UfGridDataset {
  if (!isRecord(raw)) {
    throw new Error("grid.json deve ser um objeto JSON");
  }
  const {
    uf,
    resolution,
    hex_count,
    mun_count,
    total_area_km2,
    hex_offsets,
    yields,
    hubs,
    municipios,
    h3,
    cx,
    cy,
    area_km2,
    mun_idx,
  } = raw;

  if (typeof uf !== "string" || uf.length !== 2) throw new Error("Campo 'uf' inválido");
  if (typeof resolution !== "number" || !Number.isInteger(resolution)) {
    throw new Error("Campo 'resolution' inválido");
  }
  if (typeof hex_count !== "number" || !Number.isInteger(hex_count) || hex_count < 1) {
    throw new Error("Campo 'hex_count' inválido");
  }
  if (typeof mun_count !== "number" || !Number.isInteger(mun_count) || mun_count < 1) {
    throw new Error("Campo 'mun_count' inválido");
  }
  if (typeof total_area_km2 !== "number" || !Number.isFinite(total_area_km2)) {
    throw new Error("Campo 'total_area_km2' inválido");
  }
  if (!Array.isArray(hex_offsets) || hex_offsets.length !== 6) {
    throw new Error("Campo 'hex_offsets' inválido");
  }
  const parsedOffsets: [number, number][] = hex_offsets.map((pair) => {
    if (!Array.isArray(pair) || pair.length !== 2 || typeof pair[0] !== "number" || typeof pair[1] !== "number") {
      throw new Error("Offset hexagonal inválido");
    }
    return [pair[0], pair[1]];
  });

  if (!isRecord(yields)) throw new Error("Campo 'yields' inválido");
  const parsedYields: UfYields = {
    pop: Number(yields.pop ?? 0),
    pib_mil: Number(yields.pib_mil ?? 0),
    vab_ind_mil: Number(yields.vab_ind_mil ?? 0),
    vab_agro_mil: Number(yields.vab_agro_mil ?? 0),
    vab_serv_mil: Number(yields.vab_serv_mil ?? 0),
    vab_adm_mil: Number(yields.vab_adm_mil ?? 0),
  };

  if (!Array.isArray(hubs)) throw new Error("Campo 'hubs' inválido");
  const parsedHubs: CityHub[] = hubs.map((entry) => {
    if (!isRecord(entry) || typeof entry.nome !== "string" || typeof entry.cd_mun !== "string") {
      throw new Error("Hub urbano inválido");
    }
    return {
      cd_mun: entry.cd_mun,
      nome: entry.nome,
      x: Number(entry.x),
      y: Number(entry.y),
      pop: Number(entry.pop),
      pib_mil: Number(entry.pib_mil),
    };
  });

  if (!isStringArray(municipios) || !isStringArray(h3)) {
    throw new Error("Listas 'municipios' ou 'h3' inválidas");
  }
  if (!isNumberArray(cx) || !isNumberArray(cy) || !isNumberArray(area_km2)) {
    throw new Error("Vetores numéricos do grid inválidos");
  }
  if (!Array.isArray(mun_idx)) throw new Error("Campo 'mun_idx' inválido");
  const parsedMunIdx: number[][] = mun_idx.map((row) => {
    if (!isNumberArray(row)) throw new Error("Linha inválida em 'mun_idx'");
    return row;
  });

  if (
    h3.length !== hex_count ||
    cx.length !== hex_count ||
    cy.length !== hex_count ||
    area_km2.length !== hex_count ||
    parsedMunIdx.length !== hex_count
  ) {
    throw new Error("Vetores do grid com tamanhos divergentes de hex_count");
  }

  return {
    uf,
    resolution,
    hex_count,
    mun_count,
    total_area_km2,
    hex_offsets: parsedOffsets,
    yields: parsedYields,
    hubs: parsedHubs,
    municipios,
    h3,
    cx,
    cy,
    area_km2,
    mun_idx: parsedMunIdx,
  };
}

export function parseLensIndex(raw: unknown): LensIndex {
  if (!isRecord(raw) || typeof raw.uf !== "string" || !Array.isArray(raw.lenses)) {
    throw new Error("lentes/index.json inválido");
  }
  const lenses: LensMetadata[] = raw.lenses.map((entry) => {
    if (!isRecord(entry)) throw new Error("Metadado de lente inválido");
    const kind = entry.kind === "rate" ? "rate" : "sum";
    const scale = entry.scale === "linear" ? "linear" : "quantile";
    if (
      typeof entry.id !== "string" ||
      typeof entry.civ_name !== "string" ||
      typeof entry.br_name !== "string" ||
      typeof entry.source_id !== "string" ||
      typeof entry.source_label !== "string" ||
      typeof entry.ano_ref !== "number" ||
      typeof entry.unit !== "string" ||
      typeof entry.palette !== "string" ||
      typeof entry.note !== "string"
    ) {
      throw new Error(`Lente sem metadados obrigatórios: ${String(entry.id)}`);
    }
    return {
      id: entry.id,
      civ_name: entry.civ_name,
      br_name: entry.br_name,
      source_id: entry.source_id,
      source_label: entry.source_label,
      ano_ref: entry.ano_ref,
      kind,
      unit: entry.unit,
      scale,
      palette: entry.palette,
      note: entry.note,
    };
  });
  return { uf: raw.uf, lenses };
}

export function parsePositionalLens(raw: unknown, expectedHexCount: number): PositionalLensData {
  if (!isRecord(raw) || typeof raw.id !== "string" || !Array.isArray(raw.values)) {
    throw new Error("Arquivo de lente posicional inválido");
  }
  if (!isNumberArray(raw.breaks)) {
    throw new Error("Campo 'breaks' inválido na lente");
  }
  const values: (number | null)[] = raw.values.map((v) => {
    if (v === null) return null;
    if (typeof v === "number" && Number.isFinite(v)) return v;
    throw new Error("Valor inválido no vetor posicional da lente");
  });
  if (values.length !== expectedHexCount) {
    throw new Error(`Lente ${raw.id} tem ${values.length} valores, esperado ${expectedHexCount}`);
  }
  return {
    id: raw.id,
    unit: String(raw.unit ?? ""),
    kind: raw.kind === "rate" ? "rate" : "sum",
    total: typeof raw.total === "number" ? raw.total : null,
    min: Number(raw.min ?? 0),
    max: Number(raw.max ?? 0),
    breaks: raw.breaks,
    values,
  };
}
