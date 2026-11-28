import "./styles.css";

import {
  parseSourcesCatalog,
  renderAlmanac,
  type SourcesCatalog,
} from "./almanac/almanac";
import {
  BR_BASE_LENSES,
  BR_UF_NAMES,
  parseBrOverview,
  parseCompactBrLens,
  type BrOverviewDataset,
} from "./br/brData";
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
import { parseUrlState, serializeUrlState, type PointsMode } from "./url-state/urlState";

const GRID_URL = "/data/sp/grid.json";
const LENS_INDEX_URL = "/data/sp/lentes/index.json";
const POINTS_URL = "/data/sp/pontos.json";
const CITIES_URL = "/data/sp/cities.json";
const EXPLORER_URL = "/data/sp/explorer.json";
const SOURCES_URL = "/data/sp/sources.json";
const BR_OVERVIEW_URL = "/data/br/br_res3.json";

async function fetchJson(url: string): Promise<unknown> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ao carregar ${url}`);
  }
  return (await response.json()) as unknown;
}

async function bootstrap(): Promise<void> {
  const canvas = document.getElementById("map-canvas");
  const minimap = document.getElementById("minimap-canvas");
  const brandSubtitle = document.getElementById("brand-subtitle");
  const yieldsBar = document.getElementById("yields-bar");
  const lensButtons = document.getElementById("lens-buttons");
  const legend = document.getElementById("legend");
  const cityDrawer = document.getElementById("city-drawer");
  const status = document.getElementById("status");
  const tooltip = document.getElementById("tooltip");
  const btnScopeBr = document.getElementById("btn-scope-br");
  const btnMode = document.getElementById("btn-mode");
  const btnBanners = document.getElementById("btn-banners");
  const btnPoints = document.getElementById("btn-points");
  const btnExplorer = document.getElementById("btn-explorer");
  const btnAlmanac = document.getElementById("btn-almanac");
  const btnShare = document.getElementById("btn-share");
  const btnPng = document.getElementById("btn-png");
  const btnReset = document.getElementById("btn-reset");
  const btnSearch = document.getElementById("btn-search");
  const btnCloseSearch = document.getElementById("btn-close-search");
  const searchModal = document.getElementById("search-modal");
  const explorerModal = document.getElementById("explorer-modal");
  const almanacModal = document.getElementById("almanac-modal");
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");

  if (
    !(canvas instanceof HTMLCanvasElement) ||
    !(minimap instanceof HTMLCanvasElement) ||
    !brandSubtitle ||
    !yieldsBar ||
    !lensButtons ||
    !legend ||
    !cityDrawer ||
    !status ||
    !tooltip ||
    !btnScopeBr ||
    !btnMode ||
    !btnBanners ||
    !btnPoints ||
    !btnExplorer ||
    !btnAlmanac ||
    !btnShare ||
    !btnPng ||
    !btnReset ||
    !btnSearch ||
    !btnCloseSearch ||
    !searchModal ||
    !explorerModal ||
    !almanacModal ||
    !(searchInput instanceof HTMLInputElement) ||
    !searchResults
  ) {
    throw new Error("Elementos raiz da aplicação não encontrados");
  }

  const renderer = new HexMapRenderer(canvas, minimap);
  const lensCache = new Map<string, PositionalLensData>();
  const ufGridCache = new Map<string, UfGridDataset>();
  const initialUrlState = parseUrlState(window.location.search);

  let activeScope =
    initialUrlState.uf && (initialUrlState.uf === "BR" || initialUrlState.uf in BR_UF_NAMES)
      ? initialUrlState.uf
      : "SP";
  let grid: UfGridDataset;
  let lensIndex: LensIndex;
  let spGrid: UfGridDataset | null = null;
  let spLensIndex: LensIndex | null = null;
  let brOverview: BrOverviewDataset | null = null;
  let activeLensMeta: LensMetadata;
  let activeLensData: PositionalLensData;
  let pointsData: PointsDataset | null = null;
  let explorerData: ExplorerDataset | null = null;
  let sourcesCatalog: SourcesCatalog | null = null;
  let explorerMounted = false;
  let activeCityCd: string | null = null;
  const cityByCd = new Map<string, CityProfile>();
  const cityByNormName = new Map<string, CityProfile>();

  let mode: VisualMode = initialUrlState.mode ?? "atlas";
  let showBanners = true;
  let pointsMode: PointsMode = initialUrlState.pointsMode ?? "auto";
  let hoverIndex: number | null = null;
  let selectedIndex: number | null = null;
  let filterBucket: number | null = null;
  let dragging = false;
  let downX = 0;
  let downY = 0;
  let lastX = 0;
  let lastY = 0;

  const camera: CameraState = {
    x: initialUrlState.camX ?? 500,
    y: initialUrlState.camY ?? 350,
    zoom: initialUrlState.camZ ?? 1.0,
  };

  btnMode.textContent = mode === "atlas" ? "Modo: Atlas" : "Modo: Civ";
  btnPoints.textContent =
    pointsMode === "auto" ? "Pontos: AUTO" : pointsMode === "on" ? "Pontos: ON" : "Pontos: OFF";

  const syncUrl = (): void => {
    const nextHref = serializeUrlState(window.location.href, {
      uf: activeScope,
      lensId: activeLensMeta?.id ?? null,
      mode,
      pointsMode,
      cityCd: activeScope === "SP" ? activeCityCd : null,
      camX: camera.x,
      camY: camera.y,
      camZ: camera.zoom,
    });
    window.history.replaceState(null, "", nextHref);
  };

  const shouldRenderPoints = (): boolean => {
    if (activeScope !== "SP" || !pointsData) return false;
    if (pointsMode === "on") return true;
    if (pointsMode === "off") return false;
    return activeLensMeta.id === "infra" || activeLensMeta.id === "saude";
  };

  const closeCityView = (): void => {
    activeCityCd = null;
    cityDrawer.classList.add("hidden");
    syncUrl();
  };

  const openCityView = (city: CityProfile): void => {
    activeCityCd = city.cd_mun;
    renderCityView(cityDrawer, city, closeCityView);
    cityDrawer.classList.remove("hidden");
    syncUrl();
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

  let loadSeq = 0;

  const loadLens = async (lensId: string, expectedSeq?: number): Promise<void> => {
    const mySeq = expectedSeq ?? ++loadSeq;
    const targetScope = activeScope;
    const targetHexCount = grid.hex_count;
    const meta = lensIndex.lenses.find((item) => item.id === lensId);
    if (!meta) return;
    const cacheKey = `${targetScope}:${lensId}`;
    let data = lensCache.get(cacheKey);
    if (!data) {
      if (targetScope === "BR" && brOverview) {
        data = brOverview.lenses[lensId];
      } else if (targetScope === "SP") {
        const raw = await fetchJson(`/data/sp/lentes/${lensId}.json`);
        if (mySeq !== loadSeq) return;
        data = parsePositionalLens(raw, targetHexCount);
      } else {
        const raw = await fetchJson(`/data/br/${targetScope.toLowerCase()}_lenses/${lensId}.json`);
        if (mySeq !== loadSeq) return;
        data = parseCompactBrLens(raw, meta, targetHexCount);
      }
      if (!data) return;
      lensCache.set(cacheKey, data);
    }
    if (mySeq !== loadSeq) return;
    activeLensMeta = meta;
    activeLensData = data;
    filterBucket = null;
    syncUrl();
    renderLensButtons(lensButtons, lensIndex.lenses, lensId, (nextId) => {
      void loadLens(nextId);
    });
    syncLegend();
    redraw();
  };

  const ensureSpLoaded = async (): Promise<void> => {
    if (spGrid && spLensIndex) return;
    const [rawGrid, rawIndex, rawPoints, rawCities, rawExplorer, rawSources] = await Promise.all([
      fetchJson(GRID_URL),
      fetchJson(LENS_INDEX_URL),
      fetchJson(POINTS_URL).catch(() => null),
      fetchJson(CITIES_URL).catch(() => null),
      fetchJson(EXPLORER_URL).catch(() => null),
      fetchJson(SOURCES_URL).catch(() => null),
    ]);
    spGrid = parseUfGridDataset(rawGrid);
    spLensIndex = parseLensIndex(rawIndex);
    ufGridCache.set("SP", spGrid);
    pointsData = tryParseOptional(rawPoints, parsePointsDataset);
    const parsedCities = tryParseOptional(rawCities, parseCitiesDataset);
    if (parsedCities) {
      for (const c of parsedCities.cities) {
        cityByCd.set(c.cd_mun, c);
        cityByNormName.set(normalizeSearchText(c.nome), c);
      }
    }
    explorerData = tryParseOptional(rawExplorer, parseExplorerDataset);
    sourcesCatalog = tryParseOptional(rawSources, parseSourcesCatalog);
  };

  const loadScope = async (
    targetUf: string,
    preferredLensId: string | null = null,
    resetCamera = true,
  ): Promise<void> => {
    const mySeq = ++loadSeq;
    try {
      const normalized = targetUf.toUpperCase();
      renderStatus(status, `Carregando ${normalized}…`);
      explorerModal.classList.add("hidden");
      searchModal.classList.add("hidden");

      let nextGrid: UfGridDataset;
      let nextLensIndex: LensIndex;
      let nextSubtitle: string;
      let nextScopeBtnLabel: string;

      if (normalized === "BR") {
        if (!brOverview) {
          const rawBr = await fetchJson(BR_OVERVIEW_URL);
          if (mySeq !== loadSeq) return;
          brOverview = parseBrOverview(rawBr);
        }
        nextGrid = brOverview.grid;
        nextLensIndex = { uf: "BR", lenses: BR_BASE_LENSES };
        nextSubtitle = "Brasil · 27 UFs · H3 res 3";
        nextScopeBtnLabel = "Voltar p/ SP";
      } else if (normalized === "SP") {
        await ensureSpLoaded();
        if (mySeq !== loadSeq || !spGrid || !spLensIndex) return;
        nextGrid = spGrid;
        nextLensIndex = spLensIndex;
        nextSubtitle = "São Paulo · H3 res 5";
        nextScopeBtnLabel = "Brasil (27 UFs)";
      } else if (normalized in BR_UF_NAMES) {
        let ufGrid = ufGridCache.get(normalized);
        if (!ufGrid) {
          const rawUf = await fetchJson(`/data/br/${normalized.toLowerCase()}_grid.json`);
          if (mySeq !== loadSeq) return;
          ufGrid = parseUfGridDataset(rawUf);
          ufGridCache.set(normalized, ufGrid);
        }
        nextGrid = ufGrid;
        nextLensIndex = { uf: normalized, lenses: BR_BASE_LENSES };
        nextSubtitle = `${BR_UF_NAMES[normalized] ?? normalized} · H3 res 5`;
        nextScopeBtnLabel = "← Brasil (Res 3)";
      } else {
        return;
      }

      if (mySeq !== loadSeq) return;
      activeScope = normalized;
      grid = nextGrid;
      lensIndex = nextLensIndex;
      selectedIndex = null;
      hoverIndex = null;
      filterBucket = null;
      if (normalized !== "SP") {
        activeCityCd = null;
        cityDrawer.classList.add("hidden");
      }
      brandSubtitle.textContent = nextSubtitle;
      btnScopeBr.textContent = nextScopeBtnLabel;
      btnExplorer.classList.toggle("hidden", normalized !== "SP");

      if (resetCamera) {
        camera.x = 500;
        camera.y = 350;
        camera.zoom = 1.0;
      }

      renderYieldsBar(yieldsBar, grid);
      renderer.resize();

      const nextLens =
        preferredLensId && lensIndex.lenses.some((l) => l.id === preferredLensId)
          ? preferredLensId
          : (lensIndex.lenses[0]?.id ?? "ouro");
      await loadLens(nextLens, mySeq);
    } catch (err) {
      if (mySeq !== loadSeq) return;
      const message = err instanceof Error ? err.message : String(err);
      renderStatus(status, `Falha ao carregar ${targetUf}: ${message}`, true);
    }
  };

  try {
    await loadScope(activeScope, initialUrlState.lensId, false);
    if (activeScope === "SP" && initialUrlState.cityCd) {
      const restoredCity = cityByCd.get(initialUrlState.cityCd);
      if (restoredCity) {
        if (restoredCity.hex_idx >= 0) selectedIndex = restoredCity.hex_idx;
        openCityView(restoredCity);
        redraw();
      }
    }
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

    if (activeScope === "BR" && brOverview) {
      if (showBanners) {
        const hub = renderer.pickHubAtScreen(sx, sy, grid, camera);
        if (hub && hub.cd_mun in BR_UF_NAMES) {
          void loadScope(hub.cd_mun, activeLensMeta?.id ?? null);
          return;
        }
      }
      const pickedBrHex = renderer.pickHex(sx, sy, grid, camera);
      if (pickedBrHex !== null) {
        const ufTarget = brOverview.ufDom[pickedBrHex];
        if (ufTarget && ufTarget in BR_UF_NAMES) {
          void loadScope(ufTarget, activeLensMeta?.id ?? null);
          return;
        }
      }
      return;
    }

    if (showBanners && activeScope === "SP") {
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
      if (activeScope === "SP") {
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
    syncUrl();
    syncLegend();
    redraw();
  };

  btnScopeBr.addEventListener("click", () => {
    if (activeScope === "BR") {
      void loadScope("SP");
    } else {
      void loadScope("BR");
    }
  });
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
    syncUrl();
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
  const shareDefaultLabel = btnShare.textContent?.trim() || "Compartilhar";
  let shareResetTimer: number | null = null;
  const setShareFeedback = (label: string): void => {
    if (shareResetTimer !== null) {
      window.clearTimeout(shareResetTimer);
    }
    btnShare.textContent = label;
    shareResetTimer = window.setTimeout(() => {
      btnShare.textContent = shareDefaultLabel;
      shareResetTimer = null;
    }, 1500);
  };
  btnShare.addEventListener("click", () => {
    syncUrl();
    const shareHref = window.location.href;
    if (!navigator.clipboard?.writeText) {
      setShareFeedback("Falha ao copiar");
      return;
    }
    void navigator.clipboard.writeText(shareHref).then(
      () => setShareFeedback("Link copiado!"),
      () => setShareFeedback("Falha ao copiar"),
    );
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
        const profile =
          activeScope === "SP" ? cityByNormName.get(normalizeSearchText(match.nome)) : undefined;
        if (profile) {
          openCityView(profile);
        } else {
          syncUrl();
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
    if (activeScope !== "SP" || !explorerData) return;
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
          } else {
            syncUrl();
          }
          redraw();
        },
        closeExplorer,
      );
      explorerMounted = true;
    }
    explorerModal.classList.remove("hidden");
  };

  const closeAlmanac = (): void => {
    almanacModal.classList.add("hidden");
  };

  const openAlmanac = (): void => {
    renderAlmanac(almanacModal, grid, sourcesCatalog, closeAlmanac);
    almanacModal.classList.remove("hidden");
  };

  btnAlmanac.addEventListener("click", openAlmanac);
  almanacModal.addEventListener("click", (e) => {
    if (e.target === almanacModal) closeAlmanac();
  });

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
        closeAlmanac();
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
      if (!almanacModal.classList.contains("hidden")) {
        closeAlmanac();
      } else if (!explorerModal.classList.contains("hidden")) {
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
