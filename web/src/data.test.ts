import { describe, expect, it } from "vitest";

import { renderCityView } from "./city-view/cityView";
import {
  bucketIndexForValue,
  colorForValue,
  formatPtBrCompact,
  NO_DATA_COLOR,
  parseCitiesDataset,
  parseExplorerDataset,
  parseLensIndex,
  parsePointsDataset,
  parsePositionalLens,
  parseUfGridDataset,
  searchMunicipalities,
  tryParseOptional,
  type CityProfile,
  type LensMetadata,
  type PositionalLensData,
  type UfGridDataset,
} from "./data";
import { mountExplorer, safeLog10 } from "./explorer/explorer";
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

describe("PR 3 points, cities, and City View", () => {
  it("formats QL and MW units and parses pontos.json and cities.json", () => {
    expect(formatPtBrCompact(12.34, "QL")).toBe("12,3x QL");
    expect(formatPtBrCompact(450.2, "MW")).toBe("450,2 MW");
    expect(formatPtBrCompact(1520, "MW")).toBe("1,52 GW");

    const parsedPoints = parsePointsDataset({
      uf: "SP",
      rejected_count: 2,
      usinas: [{ name: "UHE Ilha Solteira", cat: "UHE", val: 3444, unit: "MW", x: 120, y: 180, hex_idx: 0 }],
      portos: [{ name: "Porto de Santos", cat: "Porto Organizado", val: 1, unit: "instalação", x: 740, y: 520, hex_idx: 1 }],
      hospitais: [{ name: "Hospital Municipal", cat: "Hospital Geral", val: 320, unit: "leitos", x: 700, y: 460, hex_idx: 0 }],
    });
    expect(parsedPoints.usinas).toHaveLength(1);
    expect(parsedPoints.portos[0]?.name).toBe("Porto de Santos");

    const sjcProfile: CityProfile = {
      cd_mun: "3549904",
      nome: "São José dos Campos",
      pop: 697054,
      pib_mil: 47200000,
      vinculos: 245000,
      estabelecimentos_rais: 22000,
      x: 780,
      y: 420,
      hex_idx: 1,
      districts: [{ div: "30", name: "Distrito Aeroespacial e Naval", ql: 14.5, vinculos: 18500 }],
      citizens: [
        { sector: "Serviços", vinculos: 110000, pct: 44.9 },
        { sector: "Indústria", vinculos: 75000, pct: 30.6 },
      ],
      education: {
        escolas: 310,
        matriculas_basica: 132000,
        ies: 14,
        matriculas_superior: 42000,
        ideb_ai: 6.8,
        ideb_af: 5.9,
        ideb_em: 5.1,
        ideb_medio: 5.9,
      },
      health: { estabelecimentos: 1450, hospitais: 14, leitos: 1420 },
      infra: { usinas: 4, potencia_mw: 182.5, portos: 0 },
    };

    const parsedCities = parseCitiesDataset({ uf: "SP", cities: [sjcProfile] });
    expect(parsedCities.cities[0]?.districts[0]?.ql).toBe(14.5);

    const drawer = document.createElement("aside");
    let closed = false;
    renderCityView(drawer, sjcProfile, () => {
      closed = true;
    });
    expect(drawer.textContent).toContain("São José dos Campos");
    expect(drawer.textContent).toContain("Distrito Aeroespacial e Naval");
    expect(drawer.textContent).toContain("14,5x QL");
    expect(drawer.textContent).toContain("Serviços");
    expect(drawer.textContent).toContain("MTE RAIS 2025");

    const closeBtn = drawer.querySelector("button");
    closeBtn?.click();
    expect(closed).toBe(true);
  });

  it("degrades gracefully when optional pontos.json or cities.json is malformed", () => {
    expect(tryParseOptional({ broken: true }, parsePointsDataset)).toBeNull();
    expect(tryParseOptional({ broken: true }, parseCitiesDataset)).toBeNull();
    expect(tryParseOptional(null, parsePointsDataset)).toBeNull();
  });
});

describe("PR 4 Explorer and sensitive lens formatting", () => {
  it("formats %, índice, /100k and computes zero-safe log10", () => {
    expect(formatPtBrCompact(76.42, "%")).toBe("76,4%");
    expect(formatPtBrCompact(0.805, "índice")).toBe("0,805");
    expect(formatPtBrCompact(5.46, "/100k")).toBe("5,5/100k");
    expect(Number.isFinite(safeLog10(0))).toBe(true);
    expect(Number.isFinite(safeLog10(-5))).toBe(true);
  });

  it("parses explorer.json, filters without accents, and invokes selection callback", () => {
    const parsed = parseExplorerDataset({
      uf: "SP",
      municipios: [
        {
          cd_mun: "3549904",
          nome: "São José dos Campos",
          x: 780,
          y: 420,
          hex_idx: 1,
          pop: 697054,
          pib_mil: 47200000,
          pib_pc: 67713.5,
          vinculos: 228391,
          ideb_medio: 5.73,
          leitos: 1932,
          idhm: 0.807,
          gini: 0.52,
          participacao_pct: 77.2,
          homicidio_100k: 5.4,
          roubo_100k: 210.5,
          baixa_populacao: false,
        },
        {
          cd_mun: "3507209",
          nome: "Borá",
          x: 320,
          y: 350,
          hex_idx: 0,
          pop: 907,
          pib_mil: 52000,
          pib_pc: 57331.9,
          vinculos: 310,
          ideb_medio: 6.1,
          leitos: 0,
          idhm: 0.746,
          gini: 0.41,
          participacao_pct: 84.5,
          homicidio_100k: 0,
          roubo_100k: 0,
          baixa_populacao: true,
        },
      ],
    });
    expect(parsed.municipios).toHaveLength(2);

    const host = document.createElement("div");
    let pickedName = "";
    mountExplorer(
      host,
      parsed,
      (row) => {
        pickedName = row.nome;
      },
      () => {},
    );
    expect(host.querySelectorAll('[data-testid="explorer-row"]')).toHaveLength(2);
    expect(host.textContent).toContain("Borá (<20k)");

    const input = host.querySelector<HTMLInputElement>(".explorer-search");
    expect(input).not.toBeNull();
    if (input) {
      input.value = "sao jose";
      input.dispatchEvent(new Event("input"));
    }
    const filtered = host.querySelectorAll<HTMLTableRowElement>('[data-testid="explorer-row"]');
    expect(filtered).toHaveLength(1);
    filtered[0]?.click();
    expect(pickedName).toBe("São José dos Campos");
  });
});


