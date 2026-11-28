import { formatPtBrCompact, type UfGridDataset } from "../data";

export interface SourceCatalogEntry {
  readonly key: string;
  readonly orgao: string;
  readonly licenca: string;
  readonly url: string;
  readonly ano_ref: number | null;
  readonly cobertura: string;
  readonly fetched_at: string;
  readonly sha256: string;
}

export interface SourcesCatalog {
  readonly uf: string;
  readonly source_count: number;
  readonly lens_count: number;
  readonly sources: readonly SourceCatalogEntry[];
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function parseSourcesCatalog(raw: unknown): SourcesCatalog {
  if (!isRecord(raw) || typeof raw.uf !== "string" || !Array.isArray(raw.sources)) {
    throw new Error("sources.json inválido");
  }
  const sources: SourceCatalogEntry[] = raw.sources
    .filter((s): s is Record<string, unknown> => isRecord(s))
    .map((s) => ({
      key: String(s.key ?? ""),
      orgao: String(s.orgao ?? ""),
      licenca: String(s.licenca ?? ""),
      url: String(s.url ?? ""),
      ano_ref: typeof s.ano_ref === "number" ? s.ano_ref : null,
      cobertura: String(s.cobertura ?? ""),
      fetched_at: String(s.fetched_at ?? ""),
      sha256: String(s.sha256 ?? ""),
    }));
  return {
    uf: raw.uf,
    source_count: Number(raw.source_count ?? sources.length),
    lens_count: Number(raw.lens_count ?? 0),
    sources,
  };
}

export function renderAlmanac(
  container: HTMLElement,
  grid: UfGridDataset,
  catalog: SourcesCatalog | null,
  onClose: () => void,
): void {
  container.replaceChildren();

  const card = document.createElement("div");
  card.className = "almanac-card";

  const header = document.createElement("div");
  header.className = "explorer-header";
  const titleWrap = document.createElement("div");
  const title = document.createElement("h2");
  title.textContent = `Almanaque & Fontes · ${grid.uf} (UF View)`;
  const sub = document.createElement("span");
  sub.className = "explorer-count";
  sub.textContent = `${grid.hex_count} hexes H3 res ${grid.resolution} · ${grid.mun_count} municípios · ${grid.total_area_km2.toLocaleString("pt-BR")} km²`;
  titleWrap.append(title, sub);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "action-btn";
  closeBtn.textContent = "Fechar (Esc)";
  closeBtn.addEventListener("click", onClose);
  header.append(titleWrap, closeBtn);

  const yieldsGrid = document.createElement("div");
  yieldsGrid.className = "almanac-yields-grid";
  const summaryStats: readonly [string, string][] = [
    ["População (2022)", formatPtBrCompact(grid.yields.pop, "habitantes")],
    ["PIB Estadual (2021)", formatPtBrCompact(grid.yields.pib_mil, "R$ mil")],
    ["VAB Indústria", formatPtBrCompact(grid.yields.vab_ind_mil, "R$ mil")],
    ["VAB Agropecuária", formatPtBrCompact(grid.yields.vab_agro_mil, "R$ mil")],
    ["VAB Serviços", formatPtBrCompact(grid.yields.vab_serv_mil, "R$ mil")],
    ["Fontes no Manifesto", catalog ? `${catalog.source_count} arquivos oficiais` : "—"],
  ];
  for (const [label, val] of summaryStats) {
    const stat = document.createElement("div");
    stat.className = "city-stat-card";
    const lbl = document.createElement("span");
    lbl.className = "city-stat-label";
    lbl.textContent = label;
    const v = document.createElement("strong");
    v.className = "city-stat-value";
    v.textContent = val;
    stat.append(lbl, v);
    yieldsGrid.appendChild(stat);
  }

  const note = document.createElement("p");
  note.className = "almanac-note";
  note.textContent =
    "Todos os indicadores são processados por scripts determinísticos a partir de bases públicas oficiais, reconciliados para H3 res 5 via Grade Estatística 1 km do IBGE (Censo 2022) com conservação verificada.";

  const tableWrap = document.createElement("div");
  tableWrap.className = "explorer-table-wrap";
  const table = document.createElement("table");
  table.className = "explorer-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const h of ["Órgão", "Artefato", "Ano", "Cobertura", "Licença", "SHA-256"]) {
    const th = document.createElement("th");
    th.textContent = h;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);

  const tbody = document.createElement("tbody");
  if (catalog) {
    for (const src of catalog.sources) {
      const tr = document.createElement("tr");
      tr.dataset.testid = "almanac-source-row";

      const tdOrg = document.createElement("td");
      tdOrg.textContent = src.orgao;

      const tdKey = document.createElement("td");
      const link = document.createElement("a");
      link.href = src.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = "almanac-link";
      link.textContent = src.key;
      tdKey.appendChild(link);

      const tdAno = document.createElement("td");
      tdAno.textContent = src.ano_ref ? String(src.ano_ref) : "—";

      const tdCob = document.createElement("td");
      tdCob.textContent = src.cobertura;

      const tdLic = document.createElement("td");
      tdLic.textContent = src.licenca;

      const tdSha = document.createElement("td");
      tdSha.textContent = src.sha256.slice(0, 12);

      tr.append(tdOrg, tdKey, tdAno, tdCob, tdLic, tdSha);
      tbody.appendChild(tr);
    }
  }
  table.append(thead, tbody);
  tableWrap.appendChild(table);

  card.append(header, yieldsGrid, note, tableWrap);
  container.appendChild(card);
}
