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
  districts: {
    atlas: ["#1c1e2e", "#433163", "#7042a3", "#a855f7", "#e9d5ff"],
    civ: ["#262436", "#503978", "#7d4eb5", "#b26af7", "#edd9ff"],
  },
  science: {
    atlas: ["#142436", "#1d4e89", "#2563eb", "#60a5fa", "#dbeafe"],
    civ: ["#1d2c3f", "#235391", "#2e6ee6", "#6cb0ff", "#e0efff"],
  },
  health: {
    atlas: ["#231820", "#5b1f32", "#9f2241", "#e11d48", "#fda4af"],
    civ: ["#2d2028", "#6b263c", "#b02b4c", "#eb365c", "#ffb3be"],
  },
  infra: {
    atlas: ["#1e2524", "#334d47", "#0f766e", "#14b8a6", "#99f6e4"],
    civ: ["#28302e", "#3d5e57", "#188a80", "#22c7b4", "#a8faf0"],
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
  if (unit === "QL") {
    return `${value.toFixed(1).replace(".", ",")}x QL`;
  }
  if (unit === "MW") {
    if (value >= 1e3) {
      return `${(value / 1e3).toFixed(2).replace(".", ",")} GW`;
    }
    return `${value.toFixed(1).replace(".", ",")} MW`;
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
  readonly x: number;
  readonly y: number;
}

export function searchMunicipalities(
  grid: UfGridDataset,
  query: string,
  limit = 20,
): MunicipalityMatch[] {
  const needle = normalizeSearchText(query);
  const hubByName = new Map(grid.hubs.map((hub) => [normalizeSearchText(hub.nome), hub]));
  const matches: MunicipalityMatch[] = [];
  for (let mIdx = 0; mIdx < grid.municipios.length; mIdx++) {
    const nome = grid.municipios[mIdx];
    if (!nome) continue;
    const normalizedName = normalizeSearchText(nome);
    if (needle && !normalizedName.includes(needle)) continue;

    const hexIndices: number[] = [];
    for (let hIdx = 0; hIdx < grid.mun_idx.length; hIdx++) {
      const ids = grid.mun_idx[hIdx];
      if (ids?.includes(mIdx)) {
        hexIndices.push(hIdx);
      }
    }
    if (hexIndices.length === 0) continue;

    const hub = hubByName.get(normalizedName);
    let targetX = 0;
    let targetY = 0;
    if (hub) {
      targetX = hub.x;
      targetY = hub.y;
    } else {
      for (const hIdx of hexIndices) {
        targetX += grid.cx[hIdx] ?? 0;
        targetY += grid.cy[hIdx] ?? 0;
      }
      targetX /= hexIndices.length;
      targetY /= hexIndices.length;
    }

    let bestHex = hexIndices[0] ?? 0;
    let bestDistSq = Number.POSITIVE_INFINITY;
    for (const hIdx of hexIndices) {
      const dx = (grid.cx[hIdx] ?? 0) - targetX;
      const dy = (grid.cy[hIdx] ?? 0) - targetY;
      const distSq = dx * dx + dy * dy;
      if (distSq < bestDistSq) {
        bestDistSq = distSq;
        bestHex = hIdx;
      }
    }

    matches.push({
      nome,
      hexIndex: bestHex,
      x: hub ? hub.x : (grid.cx[bestHex] ?? 500),
      y: hub ? hub.y : (grid.cy[bestHex] ?? 350),
    });
    if (matches.length >= limit) break;
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

export interface PointFeature {
  readonly name: string;
  readonly cat: string;
  readonly val: number;
  readonly unit: string;
  readonly x: number;
  readonly y: number;
  readonly hex_idx: number;
}

export interface PointsDataset {
  readonly uf: string;
  readonly rejected_count: number;
  readonly usinas: readonly PointFeature[];
  readonly portos: readonly PointFeature[];
  readonly hospitais: readonly PointFeature[];
}

function parsePointList(raw: unknown, label: string): PointFeature[] {
  if (!Array.isArray(raw)) {
    throw new Error(`Lista '${label}' inválida em pontos.json`);
  }
  return raw.map((item) => {
    if (!isRecord(item) || typeof item.name !== "string") {
      throw new Error(`Ponto inválido em '${label}'`);
    }
    return {
      name: item.name,
      cat: String(item.cat ?? ""),
      val: Number(item.val ?? 0),
      unit: String(item.unit ?? ""),
      x: Number(item.x ?? 0),
      y: Number(item.y ?? 0),
      hex_idx: Number(item.hex_idx ?? -1),
    };
  });
}

export function parsePointsDataset(raw: unknown): PointsDataset {
  if (!isRecord(raw) || typeof raw.uf !== "string") {
    throw new Error("pontos.json inválido");
  }
  return {
    uf: raw.uf,
    rejected_count: Number(raw.rejected_count ?? 0),
    usinas: parsePointList(raw.usinas, "usinas"),
    portos: parsePointList(raw.portos, "portos"),
    hospitais: parsePointList(raw.hospitais, "hospitais"),
  };
}

export interface CityDistrict {
  readonly div: string;
  readonly name: string;
  readonly ql: number;
  readonly vinculos: number;
}

export interface CityCitizenSector {
  readonly sector: string;
  readonly vinculos: number;
  readonly pct: number;
}

export interface CityEducation {
  readonly escolas: number;
  readonly matriculas_basica: number;
  readonly ies: number;
  readonly matriculas_superior: number;
  readonly ideb_ai: number | null;
  readonly ideb_af: number | null;
  readonly ideb_em: number | null;
  readonly ideb_medio: number | null;
}

export interface CityHealth {
  readonly estabelecimentos: number;
  readonly hospitais: number;
  readonly leitos: number;
}

export interface CityInfra {
  readonly usinas: number;
  readonly potencia_mw: number;
  readonly portos: number;
}

export interface CityProfile {
  readonly cd_mun: string;
  readonly nome: string;
  readonly pop: number;
  readonly pib_mil: number;
  readonly vinculos: number;
  readonly estabelecimentos_rais: number;
  readonly x: number;
  readonly y: number;
  readonly hex_idx: number;
  readonly districts: readonly CityDistrict[];
  readonly citizens: readonly CityCitizenSector[];
  readonly education: CityEducation;
  readonly health: CityHealth;
  readonly infra: CityInfra;
}

export interface CitiesDataset {
  readonly uf: string;
  readonly cities: readonly CityProfile[];
}

function nullableNumber(val: unknown): number | null {
  return typeof val === "number" && Number.isFinite(val) ? val : null;
}

export function parseCitiesDataset(raw: unknown): CitiesDataset {
  if (!isRecord(raw) || typeof raw.uf !== "string" || !Array.isArray(raw.cities)) {
    throw new Error("cities.json inválido");
  }
  const cities: CityProfile[] = raw.cities.map((entry) => {
    if (!isRecord(entry) || typeof entry.cd_mun !== "string" || typeof entry.nome !== "string") {
      throw new Error("Perfil de cidade inválido em cities.json");
    }
    const rawDistricts = Array.isArray(entry.districts) ? entry.districts : [];
    const districts: CityDistrict[] = rawDistricts
      .filter((d): d is Record<string, unknown> => isRecord(d))
      .map((d) => ({
        div: String(d.div ?? ""),
        name: String(d.name ?? ""),
        ql: Number(d.ql ?? 0),
        vinculos: Number(d.vinculos ?? 0),
      }));

    const rawCitizens = Array.isArray(entry.citizens) ? entry.citizens : [];
    const citizens: CityCitizenSector[] = rawCitizens
      .filter((c): c is Record<string, unknown> => isRecord(c))
      .map((c) => ({
        sector: String(c.sector ?? ""),
        vinculos: Number(c.vinculos ?? 0),
        pct: Number(c.pct ?? 0),
      }));

    const ed = isRecord(entry.education) ? entry.education : {};
    const hl = isRecord(entry.health) ? entry.health : {};
    const inf = isRecord(entry.infra) ? entry.infra : {};

    return {
      cd_mun: entry.cd_mun,
      nome: entry.nome,
      pop: Number(entry.pop ?? 0),
      pib_mil: Number(entry.pib_mil ?? 0),
      vinculos: Number(entry.vinculos ?? 0),
      estabelecimentos_rais: Number(entry.estabelecimentos_rais ?? 0),
      x: Number(entry.x ?? 500),
      y: Number(entry.y ?? 350),
      hex_idx: Number(entry.hex_idx ?? -1),
      districts,
      citizens,
      education: {
        escolas: Number(ed.escolas ?? 0),
        matriculas_basica: Number(ed.matriculas_basica ?? 0),
        ies: Number(ed.ies ?? 0),
        matriculas_superior: Number(ed.matriculas_superior ?? 0),
        ideb_ai: nullableNumber(ed.ideb_ai),
        ideb_af: nullableNumber(ed.ideb_af),
        ideb_em: nullableNumber(ed.ideb_em),
        ideb_medio: nullableNumber(ed.ideb_medio),
      },
      health: {
        estabelecimentos: Number(hl.estabelecimentos ?? 0),
        hospitais: Number(hl.hospitais ?? 0),
        leitos: Number(hl.leitos ?? 0),
      },
      infra: {
        usinas: Number(inf.usinas ?? 0),
        potencia_mw: Number(inf.potencia_mw ?? 0),
        portos: Number(inf.portos ?? 0),
      },
    };
  });
  return { uf: raw.uf, cities };
}

