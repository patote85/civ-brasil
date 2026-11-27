import { describe, expect, it } from "vitest";

import {
  LEGEND_BUCKETS,
  colorForMunicipioCount,
  initialViewStateForWidth,
  parseSpHexDataset,
  type HexDatum,
} from "./data";
import { buildTooltipHtml, renderLegend, renderStatus } from "./ui";

describe("sp_hex dataset boundary validation", () => {
  it("parses valid payload", () => {
    const parsed = parseSpHexDataset({
      resolution: 5,
      state: "SP",
      hex_count: 1,
      total_area_km2: 245.5,
      hexes: [
        {
          h3: "85a81003fffffff",
          municipios: ["Adamantina", "Adolfo"],
          cd_muns: ["3500105", "3500204"],
          municipio_count: 2,
          area_km2: 245.5,
        },
      ],
    });
    expect(parsed.hex_count).toBe(1);
    expect(parsed.hexes[0]?.municipios).toEqual(["Adamantina", "Adolfo"]);
  });

  it("rejects corrupted or inconsistent payloads", () => {
    expect(() => parseSpHexDataset(null)).toThrow();
    expect(() =>
      parseSpHexDataset({
        resolution: 5,
        state: "SP",
        hex_count: 2,
        total_area_km2: 100,
        hexes: [],
      }),
    ).toThrow(/hex_count/);
  });
});

describe("color scale, tooltip and responsive UI (1280px and 375px)", () => {
  it("maps municipality counts across all legend buckets", () => {
    expect(colorForMunicipioCount(1)).toEqual([...(LEGEND_BUCKETS[0]?.color ?? [])]);
    expect(colorForMunicipioCount(2)).toEqual([...(LEGEND_BUCKETS[1]?.color ?? [])]);
    expect(colorForMunicipioCount(4)).toEqual([...(LEGEND_BUCKETS[2]?.color ?? [])]);
    expect(colorForMunicipioCount(6)).toEqual([...(LEGEND_BUCKETS[3]?.color ?? [])]);
    expect(colorForMunicipioCount(12)).toEqual([...(LEGEND_BUCKETS[4]?.color ?? [])]);
  });

  it("formats tooltip with h3 id, area and escaped municipality names", () => {
    const datum: HexDatum = {
      h3: "85a81003fffffff",
      municipios: ["São Paulo", "<script>alert(1)</script>"],
      cd_muns: ["3550308", "3500105"],
      municipio_count: 2,
      area_km2: 123.45,
    };
    const html = buildTooltipHtml(datum);
    expect(html).toContain("85a81003fffffff");
    expect(html).toContain("São Paulo");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("renders legend and adjusts initial zoom for desktop (1280) and mobile (375)", () => {
    const desktopView = initialViewStateForWidth(1280);
    const mobileView = initialViewStateForWidth(375);
    expect(desktopView.zoom).toBeGreaterThan(mobileView.zoom);

    const legend = document.createElement("aside");
    renderLegend(legend);
    const items = legend.querySelectorAll(".legend-item");
    expect(items.length).toBe(LEGEND_BUCKETS.length);

    const status = document.createElement("div");
    renderStatus(status, "Erro de rede", true);
    expect(status.textContent).toBe("Erro de rede");
    expect(status.classList.contains("error")).toBe(true);
  });
});
