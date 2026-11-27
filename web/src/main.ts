import "./styles.css";

import { Deck, type PickingInfo } from "@deck.gl/core";
import { H3HexagonLayer } from "@deck.gl/geo-layers";

import {
  colorForMunicipioCount,
  initialViewStateForWidth,
  parseSpHexDataset,
  type HexDatum,
} from "./data";
import { buildTooltipHtml, renderLegend, renderStatus } from "./ui";

const DATA_URL = "/data/sp_hex.json";

async function bootstrap(): Promise<void> {
  const mapContainer = document.getElementById("map-container");
  const legendContainer = document.getElementById("legend");
  const statusContainer = document.getElementById("status");

  if (!(mapContainer instanceof HTMLDivElement) || !legendContainer || !statusContainer) {
    throw new Error("Elementos raiz da aplicação não encontrados");
  }

  renderLegend(legendContainer);

  try {
    const response = await fetch(DATA_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} ao carregar ${DATA_URL}`);
    }
    const raw: unknown = await response.json();
    const dataset = parseSpHexDataset(raw);

    const layer = new H3HexagonLayer<HexDatum>({
      id: "sp-h3-res5",
      data: [...dataset.hexes],
      pickable: true,
      wireframe: false,
      filled: true,
      stroked: true,
      extruded: false,
      highPrecision: true,
      getHexagon: (d) => d.h3,
      getFillColor: (d) => colorForMunicipioCount(d.municipio_count),
      getLineColor: [18, 28, 40, 200],
      lineWidthMinPixels: 1,
    });

    new Deck({
      parent: mapContainer,
      initialViewState: initialViewStateForWidth(window.innerWidth),
      controller: true,
      layers: [layer],
      getTooltip: (info: PickingInfo<HexDatum>) => {
        if (!info.object) {
          return null;
        }
        return {
          html: buildTooltipHtml(info.object),
          style: {
            backgroundColor: "#131f2e",
            border: "1px solid #2d435e",
            borderRadius: "6px",
            color: "#edf2f7",
            padding: "8px 10px",
          },
        };
      },
    });

    const areaFormatted = Math.round(dataset.total_area_km2).toLocaleString("pt-BR");
    renderStatus(
      statusContainer,
      `${dataset.hex_count} hexágonos · ${areaFormatted} km² · Fonte: IBGE`,
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    renderStatus(statusContainer, `Falha ao carregar dados: ${message}`, true);
  }
}

void bootstrap();
