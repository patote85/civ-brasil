import { describe, expect, it } from "vitest";

import {
  bucketIndexForValue,
  colorForValue,
  formatPtBrCompact,
  NO_DATA_COLOR,
  parseLensIndex,
  parsePositionalLens,
  parseUfGridDataset,
  searchMunicipalities,
  type LensMetadata,
  type PositionalLensData,
  type UfGridDataset,
} from "./data";
import { computeMinimapViewportRect } from "./renderer";
import { buildTooltipHtml, renderLegend, renderYieldsBar } from "./ui";

const SAMPLE_GRID: UfGridDataset = {
  uf: "SP",
  resolution: 5,
  hex_count: 2,
  mun_count: 2,
  total_area_km2: 410.5,
  hex_offsets: [
    [5, 8],
    [10, 0],
    [5, -8],
    [-5, -8],
    [-10, 0],
    [-5, 8],
  ],
  yields: {
    pop: 44411238,
    pib_mil: 2719751231,
    vab_ind_mil: 520000000,
    vab_agro_mil: 68000000,
    vab_serv_mil: 1600000000,
    vab_adm_mil: 240000000,
  },
  hubs: [{ cd_mun: "3550308", nome: "São Paulo", x: 700, y: 460, pop: 11451999, pib_mil: 828980747 }],
  municipios: ["Campinas", "São José dos Campos"],
  h3: ["85a80043fffffff", "85a80047fffffff"],
  cx: [660, 780],
  cy: [390, 420],
  area_km2: [200.5, 210.0],
  mun_idx: [[0], [1]],
};

const SAMPLE_LENS_META: LensMetadata = {
  id: "ouro",
  civ_name: "Ouro",
  br_name: "PIB Municipal",
  source_id: "ibge_pib",
  source_label: "IBGE · PIB dos Municípios",
  ano_ref: 2021,
  kind: "sum",
  unit: "R$ mil",
  scale: "quantile",
  palette: "gold",
  note: "Valores correntes.",
};

const SAMPLE_LENS_DATA: PositionalLensData = {
  id: "ouro",
  unit: "R$ mil",
  kind: "sum",
  total: 1500000,
  min: 100000,
  max: 1400000,
  breaks: [200000, 500000, 900000, 1200000],
  values: [1400000, null],
};

describe("data parsers and formatting", () => {
  it("parses valid grid, lens index, and positional lens payloads", () => {
    const parsedGrid = parseUfGridDataset(SAMPLE_GRID);
    expect(parsedGrid.hex_count).toBe(2);

    const parsedIndex = parseLensIndex({ uf: "SP", lenses: [SAMPLE_LENS_META] });
    expect(parsedIndex.lenses[0]?.ano_ref).toBe(2021);

    const parsedLens = parsePositionalLens(SAMPLE_LENS_DATA, 2);
    expect(parsedLens.values).toEqual([1400000, null]);
  });

  it("rejects mismatched positional lens length", () => {
    expect(() => parsePositionalLens(SAMPLE_LENS_DATA, 3)).toThrow("esperado 3");
  });

  it("formats pt-BR currency and population values and handles no-data color", () => {
    expect(formatPtBrCompact(2719751231, "R$ mil")).toBe("R$ 2,72 tri");
    expect(formatPtBrCompact(44411238, "habitantes")).toBe("44,41M");
    expect(bucketIndexForValue(null, SAMPLE_LENS_DATA.breaks)).toBe(-1);
    expect(colorForValue(null, SAMPLE_LENS_DATA.breaks, "gold", "atlas")).toBe(NO_DATA_COLOR);
  });

  it("finds municipalities without accents", () => {
    const matches = searchMunicipalities(SAMPLE_GRID, "sao jose");
    expect(matches).toEqual([{ nome: "São José dos Campos", hexIndex: 1, x: 780, y: 420 }]);
  });

  it("picks representative hub or centroid hex instead of first edge fragment", () => {
    const multiHexGrid: UfGridDataset = {
      ...SAMPLE_GRID,
      hex_count: 6,
      mun_count: 2,
      hubs: [
        { cd_mun: "3550308", nome: "São Paulo", x: 700, y: 460, pop: 11451999, pib_mil: 828980747 },
      ],
      municipios: ["Iguape", "São Paulo"],
      h3: [
        "85a80003fffffff",
        "85a80007fffffff",
        "85a8000bfffffff",
        "85a8000ffffffff",
        "85a80013fffffff",
        "85a80017fffffff",
      ],
      cx: [500, 600, 700, 620, 702, 780],
      cy: [500, 500, 500, 420, 458, 520],
      area_km2: [200, 200, 200, 200, 200, 200],
      mun_idx: [[0], [0], [0], [1], [1], [1]],
    };

    const spMatch = searchMunicipalities(multiHexGrid, "sao paulo");
    expect(spMatch).toEqual([{ nome: "São Paulo", hexIndex: 4, x: 700, y: 460 }]);

    const iguapeMatch = searchMunicipalities(multiHexGrid, "iguape");
    expect(iguapeMatch).toEqual([{ nome: "Iguape", hexIndex: 1, x: 600, y: 500 }]);
  });
});

describe("minimap viewport clipping", () => {
  it("clips viewport rectangle accurately against minimap bounds", () => {
    expect(computeMinimapViewportRect(-200, -100, 800, 600, 180, 126)).toEqual({
      x: 0,
      y: 0,
      w: 144,
      h: 108,
    });
    expect(computeMinimapViewportRect(500, 350, 1400, 1000, 180, 126)).toEqual({
      x: 90,
      y: 63,
      w: 90,
      h: 63,
    });
    expect(computeMinimapViewportRect(-500, -500, 1500, 1200, 180, 126)).toEqual({
      x: 0,
      y: 0,
      w: 180,
      h: 126,
    });
    expect(computeMinimapViewportRect(1100, 100, 1500, 400, 180, 126)).toBeNull();
  });
});

describe("ui rendering", () => {
  it("renders source, reference year, no-data swatch, yields bar, and escaped tooltip", () => {
    const legendEl = document.createElement("aside");
    renderLegend(legendEl, SAMPLE_LENS_META, SAMPLE_LENS_DATA, "atlas", null, () => {});
    expect(legendEl.textContent).toContain("IBGE · PIB dos Municípios");
    expect(legendEl.textContent).toContain("2021");
    expect(legendEl.textContent).toContain("Sem dado");

    const yieldsEl = document.createElement("div");
    renderYieldsBar(yieldsEl, SAMPLE_GRID);
    expect(yieldsEl.textContent).toContain("44,41M");
    expect(yieldsEl.textContent).toContain("R$ 2,72 tri");

    const html = buildTooltipHtml(SAMPLE_GRID, 1, SAMPLE_LENS_META, SAMPLE_LENS_DATA);
    expect(html).toContain("Sem dado");
    expect(html).toContain("São José dos Campos");
  });
});
