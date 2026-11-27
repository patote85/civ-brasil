export type RgbaColor = readonly [number, number, number, number];

export interface HexDatum {
  readonly h3: string;
  readonly municipios: readonly string[];
  readonly cd_muns: readonly string[];
  readonly municipio_count: number;
  readonly area_km2: number;
}

export interface SpHexDataset {
  readonly resolution: number;
  readonly state: string;
  readonly hex_count: number;
  readonly total_area_km2: number;
  readonly hexes: readonly HexDatum[];
}

export interface LegendBucket {
  readonly label: string;
  readonly minCount: number;
  readonly maxCount: number | null;
  readonly color: RgbaColor;
}

export interface ViewStateConfig {
  readonly latitude: number;
  readonly longitude: number;
  readonly zoom: number;
  readonly pitch: number;
  readonly bearing: number;
}

export const LEGEND_BUCKETS: readonly LegendBucket[] = [
  { label: "1 município", minCount: 1, maxCount: 1, color: [43, 108, 176, 225] },
  { label: "2 municípios", minCount: 2, maxCount: 2, color: [56, 161, 105, 225] },
  { label: "3–4 municípios", minCount: 3, maxCount: 4, color: [214, 158, 46, 230] },
  { label: "5–7 municípios", minCount: 5, maxCount: 7, color: [221, 107, 32, 235] },
  { label: "8+ municípios", minCount: 8, maxCount: null, color: [197, 48, 48, 240] },
];

export function colorForMunicipioCount(count: number): [number, number, number, number] {
  for (const bucket of LEGEND_BUCKETS) {
    if (count >= bucket.minCount && (bucket.maxCount === null || count <= bucket.maxCount)) {
      return [bucket.color[0], bucket.color[1], bucket.color[2], bucket.color[3]];
    }
  }
  const fallback = LEGEND_BUCKETS[0];
  if (!fallback) {
    return [43, 108, 176, 225];
  }
  return [fallback.color[0], fallback.color[1], fallback.color[2], fallback.color[3]];
}

export function initialViewStateForWidth(viewportWidth: number): ViewStateConfig {
  const isCompact = viewportWidth <= 480;
  return {
    latitude: -22.25,
    longitude: -48.65,
    zoom: isCompact ? 5.2 : 6.4,
    pitch: 0,
    bearing: 0,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function parseSpHexDataset(raw: unknown): SpHexDataset {
  if (!isRecord(raw)) {
    throw new Error("Dataset SP H3 deve ser um objeto JSON");
  }
  const { resolution, state, hex_count, total_area_km2, hexes } = raw;
  if (typeof resolution !== "number" || !Number.isInteger(resolution)) {
    throw new Error("Campo 'resolution' inválido");
  }
  if (typeof state !== "string" || state.length === 0) {
    throw new Error("Campo 'state' inválido");
  }
  if (typeof hex_count !== "number" || !Number.isInteger(hex_count)) {
    throw new Error("Campo 'hex_count' inválido");
  }
  if (typeof total_area_km2 !== "number" || !Number.isFinite(total_area_km2)) {
    throw new Error("Campo 'total_area_km2' inválido");
  }
  if (!Array.isArray(hexes)) {
    throw new Error("Campo 'hexes' inválido");
  }

  const parsedHexes: HexDatum[] = hexes.map((entry, idx) => {
    if (!isRecord(entry)) {
      throw new Error(`Entrada hexes[${idx}] inválida`);
    }
    const { h3, municipios, cd_muns, municipio_count, area_km2 } = entry;
    if (typeof h3 !== "string" || h3.length === 0) {
      throw new Error(`Campo 'h3' inválido em hexes[${idx}]`);
    }
    if (!isStringArray(municipios) || !isStringArray(cd_muns)) {
      throw new Error(`Listas de municípios inválidas em hexes[${idx}]`);
    }
    if (typeof municipio_count !== "number" || municipio_count !== municipios.length) {
      throw new Error(`Contagem de municípios inconsistente em hexes[${idx}]`);
    }
    if (typeof area_km2 !== "number" || !Number.isFinite(area_km2) || area_km2 <= 0) {
      throw new Error(`Área inválida em hexes[${idx}]`);
    }
    return {
      h3,
      municipios,
      cd_muns,
      municipio_count,
      area_km2,
    };
  });

  if (parsedHexes.length !== hex_count) {
    throw new Error(`hex_count (${hex_count}) diverge de hexes.length (${parsedHexes.length})`);
  }

  return {
    resolution,
    state,
    hex_count,
    total_area_km2,
    hexes: parsedHexes,
  };
}
