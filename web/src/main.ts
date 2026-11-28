import "./styles.css";

import { renderCityView } from "./city-view/cityView";
import {
  normalizeSearchText,
  parseCitiesDataset,
  parseExplorerDataset,
  parseLensIndex,
  parsePointsDataset,
  parsePositionalLens,
  parseUfGridDataset,
  searchMunicipalities,
  tryParseOptional,
  type CityProfile,
  type ExplorerDataset,
  type LensIndex,
  type LensMetadata,
  type PointsDataset,
  type PositionalLensData,
  type UfGridDataset,
  type VisualMode,
} from "./data";
import { mountExplorer } from "./explorer/explorer";
import { HexMapRenderer, type CameraState } from "./renderer";
import {
  buildTooltipHtml,
  renderLegend,
  renderLensButtons,
  renderStatus,
  renderYieldsBar,
} from "./ui";

const GRID_URL = "/data/sp/grid.json";
const LENS_INDEX_URL = "/data/sp/lentes/index.json";
const POINTS_URL = "/data/sp/pontos.json";
const CITIES_URL = "/data/sp/cities.json";
const EXPLORER_URL = "/data/sp/explorer.json";

type PointsMode = "auto" | "on" | "off";

async function fetchJson(url: string): Promise<unknown> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ao carregar ${url}`);
  }
  return (await response.json()) as unknown;
}

function readInitialLensId(index: LensIndex): string {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("lente");
  if (requested && index.lenses.some((l) => l.id === requested)) {
    return requested;
  }
  return index.lenses[0]?.id ?? "ouro";
}

function updateUrlLens(lensId: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set("lente", lensId);
  window.history.replaceState(null, "", url.toString());
}

async function bootstrap(): Promise<void> {
  const canvas = document.getElementById("map-canvas");
  const minimap = document.getElementById("minimap-canvas");
  const yieldsBar = document.getElementById("yields-bar");
  const lensButtons = document.getElementById("lens-buttons");
  const legend = document.getElementById("legend");
  const cityDrawer = document.getElementById("city-drawer");
  const status = document.getElementById("status");
  const tooltip = document.getElementById("tooltip");
  const btnMode = document.getElementById("btn-mode");
  const btnBanners = document.getElementById("btn-banners");
  const btnPoints = document.getElementById("btn-points");
  const btnExplorer = document.getElementById("btn-explorer");
  const btnPng = document.getElementById("btn-png");
  const btnReset = document.getElementById("btn-reset");
  const btnSearch = document.getElementById("btn-search");
  const btnCloseSearch = document.getElementById("btn-close-search");
  const searchModal = document.getElementById("search-modal");
  const explorerModal = document.getElementById("explorer-modal");
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");

  if (
    !(canvas instanceof HTMLCanvasElement) ||
    !(minimap instanceof HTMLCanvasElement) ||
    !yieldsBar ||
    !lensButtons ||
    !legend ||
    !cityDrawer ||
    !status ||
    !tooltip ||
    !btnMode ||
    !btnBanners ||
    !btnPoints ||
    !btnExplorer ||
    !btnPng ||
    !btnReset ||
    !btnSearch ||
    !btnCloseSearch ||
    !searchModal ||
    !explorerModal ||
    !(searchInput instanceof HTMLInputElement) ||
    !searchResults
  ) {
    throw new Error("Elementos raiz da aplicação não encontrados");
  }

  const renderer = new HexMapRenderer(canvas, minimap);
  const lensCache = new Map<string, PositionalLensData>();

  let grid: UfGridDataset;
  let lensIndex: LensIndex;
  let activeLensMeta: LensMetadata;
  let activeLensData: PositionalLensData;
  let pointsData: PointsDataset | null = null;
  let explorerData: ExplorerDataset | null = null;
  let explorerMounted = false;
  const cityByCd = new Map<string, CityProfile>();
  const cityByNormName = new Map<string, CityProfile>();

  let mode: VisualMode = "atlas";
  let showBanners = true;
  let pointsMode: PointsMode = "auto";
  let hoverIndex: number | null = null;
  let selectedIndex: number | null = null;
  let filterBucket: number | null = null;
  let dragging = false;
  let downX = 0;
  let downY = 0;
  let lastX = 0;
  let lastY = 0;

  const camera: CameraState = { x: 500, y: 350, zoom: 1.0 };

  const shouldRenderPoints = (): boolean => {
    if (!pointsData) return false;
    if (pointsMode === "on") return true;
    if (pointsMode === "off") return false;
    return activeLensMeta.id === "infra" || activeLensMeta.id === "saude";
  };

  const closeCityView = (): void => {
    cityDrawer.classList.add("hidden");
  };

  const openCityView = (city: CityProfile): void => {
    renderCityView(cityDrawer, city, closeCityView);
    cityDrawer.classList.remove("hidden");
  };

  const redraw = (): void => {
    const ms = renderer.render({
      grid,
      lensMeta: activeLensMeta,
      lensData: activeLensData,
      mode,
      showBanners,
      showPoints: shouldRenderPoints(),
      points: pointsData,
      camera,
      hoverIndex,
      selectedIndex,
      filterBucket,
    });
    renderStatus(
      status,
      `${grid.hex_count} hexes · ${activeLensMeta.source_label} (${activeLensMeta.ano_ref}) · ${ms.toFixed(1)} ms`,
    );
  };

  const syncLegend = (): void => {
    renderLegend(legend, activeLensMeta, activeLensData, mode, filterBucket, (bucketIdx) => {
      filterBucket = bucketIdx;
      redraw();
    });
  };

  const loadLens = async (lensId: string): Promise<void> => {
    const meta = lensIndex.lenses.find((item) => item.id === lensId);
    if (!meta) return;
    let data = lensCache.get(lensId);
    if (!data) {
      const raw = await fetchJson(`/data/sp/lentes/${lensId}.json`);
      data = parsePositionalLens(raw, grid.hex_count);
      lensCache.set(lensId, data);
    }
    activeLensMeta = meta;
    activeLensData = data;
    filterBucket = null;
    updateUrlLens(lensId);
    renderLensButtons(lensButtons, lensIndex.lenses, lensId, (nextId) => {
      void loadLens(nextId);
    });
    syncLegend();
    redraw();
  };

  try {
    const [rawGrid, rawIndex, rawPoints, rawCities, rawExplorer] = await Promise.all([
      fetchJson(GRID_URL),
      fetchJson(LENS_INDEX_URL),
      fetchJson(POINTS_URL).catch(() => null),
      fetchJson(CITIES_URL).catch(() => null),
      fetchJson(EXPLORER_URL).catch(() => null),
    ]);
    grid = parseUfGridDataset(rawGrid);
    lensIndex = parseLensIndex(rawIndex);
    pointsData = tryParseOptional(rawPoints, parsePointsDataset);
    const parsedCities = tryParseOptional(rawCities, parseCitiesDataset);
    if (parsedCities) {
      for (const c of parsedCities.cities) {
        cityByCd.set(c.cd_mun, c);
        cityByNormName.set(normalizeSearchText(c.nome), c);
      }
    }
    explorerData = tryParseOptional(rawExplorer, parseExplorerDataset);
    renderYieldsBar(yieldsBar, grid);
    renderer.resize();
    await loadLens(readInitialLensId(lensIndex));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    renderStatus(status, `Falha ao carregar dados: ${message}`, true);
    return;
  }

  canvas.addEventListener("pointerdown", (e) => {
    dragging = true;
    downX = e.clientX;
    downY = e.clientY;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });

  canvas.addEventListener("pointermove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    if (dragging) {
      const [, , scale] = renderer.worldToScreen(0, 0, camera);
      camera.x -= (e.clientX - lastX) / scale;
      camera.y -= (e.clientY - lastY) / scale;
      lastX = e.clientX;
      lastY = e.clientY;
      redraw();
      return;
    }
    const picked = renderer.pickHex(sx, sy, grid, camera);
    if (picked !== hoverIndex) {
      hoverIndex = picked;
      redraw();
    }
    if (picked !== null) {
      tooltip.classList.remove("hidden");
      tooltip.style.left = `${Math.min(window.innerWidth - 280, e.clientX + 14)}px`;
      tooltip.style.top = `${Math.min(window.innerHeight - 110, e.clientY + 14)}px`;
      tooltip.innerHTML = buildTooltipHtml(grid, picked, activeLensMeta, activeLensData);
    } else {
      tooltip.classList.add("hidden");
    }
  });

  canvas.addEventListener("pointerup", (e) => {
    const wasClick = Math.hypot(e.clientX - downX, e.clientY - downY) < 5;
    dragging = false;
    if (!wasClick) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (showBanners) {
      const hub = renderer.pickHubAtScreen(sx, sy, grid, camera);
      if (hub) {
        const profile = cityByCd.get(hub.cd_mun) ?? cityByNormName.get(normalizeSearchText(hub.nome));
        if (profile) {
          if (profile.hex_idx >= 0) selectedIndex = profile.hex_idx;
          openCityView(profile);
          redraw();
          return;
        }
      }
    }

    const pickedHex = renderer.pickHex(sx, sy, grid, camera);
    if (pickedHex !== null) {
      selectedIndex = pickedHex;
      const munIds = grid.mun_idx[pickedHex] ?? [];
      let bestCity: CityProfile | null = null;
      for (const mIdx of munIds) {
        const mName = grid.municipios[mIdx];
        if (!mName) continue;
        const candidate = cityByNormName.get(normalizeSearchText(mName));
        if (candidate && (!bestCity || candidate.pop > bestCity.pop)) {
          bestCity = candidate;
        }
      }
      if (bestCity) {
        openCityView(bestCity);
      }
      redraw();
    }
  });

  canvas.addEventListener("pointerleave", () => {
    dragging = false;
    hoverIndex = null;
    tooltip.classList.add("hidden");
    redraw();
  });

  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18;
      camera.zoom = Math.max(0.75, Math.min(7.0, camera.zoom * factor));
      redraw();
    },
    { passive: false },
  );

  minimap.addEventListener("click", (e) => {
    const rect = minimap.getBoundingClientRect();
    camera.x = ((e.clientX - rect.left) / minimap.width) * 1000;
    camera.y = ((e.clientY - rect.top) / minimap.height) * 700;
    redraw();
  });

  const toggleMode = (): void => {
    mode = mode === "atlas" ? "civ" : "atlas";
    btnMode.textContent = mode === "atlas" ? "Modo: Atlas" : "Modo: Civ";
    syncLegend();
    redraw();
  };

  btnMode.addEventListener("click", toggleMode);
  btnBanners.addEventListener("click", () => {
    showBanners = !showBanners;
    btnBanners.textContent = showBanners ? "Cidades: ON" : "Cidades: OFF";
    redraw();
  });
  btnPoints.addEventListener("click", () => {
    pointsMode = pointsMode === "auto" ? "on" : pointsMode === "on" ? "off" : "auto";
    btnPoints.textContent =
      pointsMode === "auto" ? "Pontos: AUTO" : pointsMode === "on" ? "Pontos: ON" : "Pontos: OFF";
    redraw();
  });
  btnReset.addEventListener("click", () => {
    camera.x = 500;
    camera.y = 350;
    camera.zoom = 1.0;
    selectedIndex = null;
    closeCityView();
    redraw();
  });
  btnPng.addEventListener("click", () => {
    const link = document.createElement("a");
    link.download = `civ-brasil-${grid.uf.toLowerCase()}-${activeLensMeta.id}.png`;
    link.href = renderer.exportPngDataUrl(activeLensMeta, grid);
    link.click();
  });

  const renderSearchList = (query: string): void => {
    const matches = searchMunicipalities(grid, query, 25);
    searchResults.replaceChildren();
    if (matches.length === 0) {
      const empty = document.createElement("li");
      empty.className = "search-result-item";
      empty.textContent = "Nenhum município encontrado.";
      searchResults.appendChild(empty);
      return;
    }
    for (const match of matches) {
      const li = document.createElement("li");
      li.className = "search-result-item";
      li.tabIndex = 0;
      const nameSpan = document.createElement("span");
      nameSpan.textContent = match.nome;
      const h3Span = document.createElement("span");
      h3Span.textContent = grid.h3[match.hexIndex] ?? "";
      li.append(nameSpan, h3Span);
      const selectMatch = (): void => {
        selectedIndex = match.hexIndex;
        camera.x = match.x;
        camera.y = match.y;
        camera.zoom = 2.8;
        searchModal.classList.add("hidden");
        const profile = cityByNormName.get(normalizeSearchText(match.nome));
        if (profile) {
          openCityView(profile);
        }
        redraw();
      };
      li.addEventListener("click", selectMatch);
      li.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") selectMatch();
      });
      searchResults.appendChild(li);
    }
  };

  const openSearch = (): void => {
    searchModal.classList.remove("hidden");
    searchInput.value = "";
    renderSearchList("");
    searchInput.focus();
  };

  const closeExplorer = (): void => {
    explorerModal.classList.add("hidden");
  };

  const openExplorer = (): void => {
    if (!explorerData) return;
    if (!explorerMounted) {
      mountExplorer(
        explorerModal,
        explorerData,
        (row) => {
          if (row.hex_idx >= 0) selectedIndex = row.hex_idx;
          camera.x = row.x;
          camera.y = row.y;
          camera.zoom = 2.8;
          closeExplorer();
          const profile = cityByCd.get(row.cd_mun) ?? cityByNormName.get(normalizeSearchText(row.nome));
          if (profile) {
            openCityView(profile);
          }
          redraw();
        },
        closeExplorer,
      );
      explorerMounted = true;
    }
    explorerModal.classList.remove("hidden");
  };

  btnExplorer.addEventListener("click", openExplorer);
  explorerModal.addEventListener("click", (e) => {
    if (e.target === explorerModal) closeExplorer();
  });

  btnSearch.addEventListener("click", openSearch);
  btnCloseSearch.addEventListener("click", () => searchModal.classList.add("hidden"));
  searchModal.addEventListener("click", (e) => {
    if (e.target === searchModal) searchModal.classList.add("hidden");
  });
  searchInput.addEventListener("input", () => renderSearchList(searchInput.value));

  window.addEventListener("keydown", (e) => {
    const target = e.target;
    const isInput =
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement;
    if (isInput) {
      if (e.key === "Escape") {
        searchModal.classList.add("hidden");
        closeExplorer();
      }
      return;
    }
    if (e.key === "/" || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) {
      e.preventDefault();
      openSearch();
    } else if (e.key.toLowerCase() === "e") {
      e.preventDefault();
      openExplorer();
    } else if (e.key.toLowerCase() === "m") {
      toggleMode();
    } else if (e.key.toLowerCase() === "l") {
      const idx = lensIndex.lenses.findIndex((l) => l.id === activeLensMeta.id);
      const step = e.shiftKey ? -1 : 1;
      const next = lensIndex.lenses[(idx + step + lensIndex.lenses.length) % lensIndex.lenses.length];
      if (next) void loadLens(next.id);
    } else if (e.key === "Escape") {
      if (!explorerModal.classList.contains("hidden")) {
        closeExplorer();
      } else if (!searchModal.classList.contains("hidden")) {
        searchModal.classList.add("hidden");
      } else {
        closeCityView();
      }
    }
  });

  window.addEventListener("resize", () => {
    renderer.resize();
    redraw();
  });
}

void bootstrap();
