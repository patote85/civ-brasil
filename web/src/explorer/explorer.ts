import {
  formatPtBrCompact,
  normalizeSearchText,
  type ExplorerDataset,
  type ExplorerRow,
} from "../data";

export type MetricKey =
  | "pop"
  | "pib_mil"
  | "pib_pc"
  | "vinculos"
  | "ideb_medio"
  | "leitos"
  | "idhm"
  | "gini"
  | "participacao_pct"
  | "homicidio_100k"
  | "roubo_100k";

interface MetricDef {
  readonly key: MetricKey;
  readonly label: string;
  readonly unit: string;
}

const METRICS: readonly MetricDef[] = [
  { key: "pop", label: "População (2022)", unit: "habitantes" },
  { key: "pib_mil", label: "PIB (2021)", unit: "R$ mil" },
  { key: "pib_pc", label: "PIB per capita", unit: "R$" },
  { key: "vinculos", label: "Vínculos RAIS (2025)", unit: "vínculos" },
  { key: "ideb_medio", label: "IDEB Médio (2025)", unit: "nota" },
  { key: "leitos", label: "Leitos CNES (2025)", unit: "leitos" },
  { key: "idhm", label: "IDHM (2010)", unit: "índice" },
  { key: "gini", label: "Gini (2010)", unit: "índice" },
  { key: "participacao_pct", label: "Participação TSE (2024)", unit: "%" },
  { key: "homicidio_100k", label: "Homicídios/100k (2025)", unit: "/100k" },
  { key: "roubo_100k", label: "Roubos/100k (2025)", unit: "/100k" },
];

export function formatExplorerValue(val: number | null, unit: string): string {
  if (val === null || !Number.isFinite(val)) return "—";
  if (unit === "R$") {
    return `R$ ${Math.round(val).toLocaleString("pt-BR")}`;
  }
  if (unit === "nota") {
    return val.toFixed(1).replace(".", ",");
  }
  return formatPtBrCompact(val, unit);
}

export function safeLog10(value: number): number {
  return Math.log10(Math.max(1e-3, value));
}

export function mountExplorer(
  container: HTMLElement,
  dataset: ExplorerDataset,
  onSelectMunicipality: (row: ExplorerRow) => void,
  onClose: () => void,
): { refresh: () => void } {
  container.replaceChildren();

  let query = "";
  let sortKey: MetricKey | "nome" = "pop";
  let sortAsc = false;
  let xKey: MetricKey = "pib_pc";
  let yKey: MetricKey = "idhm";
  let useLog = true;

  const card = document.createElement("div");
  card.className = "explorer-card";

  const header = document.createElement("div");
  header.className = "explorer-header";
  const titleWrap = document.createElement("div");
  const title = document.createElement("h2");
  title.textContent = `Explorer · ${dataset.municipios.length} Municípios (${dataset.uf})`;
  const countBadge = document.createElement("span");
  countBadge.className = "explorer-count";
  titleWrap.append(title, countBadge);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "action-btn";
  closeBtn.textContent = "Fechar (Esc)";
  closeBtn.addEventListener("click", onClose);
  header.append(titleWrap, closeBtn);

  const controls = document.createElement("div");
  controls.className = "explorer-controls";

  const searchInput = document.createElement("input");
  searchInput.type = "search";
  searchInput.className = "explorer-search";
  searchInput.placeholder = "Filtrar município sem acento (ex.: sao jose)…";
  searchInput.ariaLabel = "Filtrar municípios no Explorer";

  const makeSelect = (label: string, initial: MetricKey, onChange: (k: MetricKey) => void): HTMLElement => {
    const wrap = document.createElement("label");
    wrap.className = "explorer-axis-label";
    wrap.textContent = label;
    const sel = document.createElement("select");
    sel.className = "explorer-select";
    for (const m of METRICS) {
      const opt = document.createElement("option");
      opt.value = m.key;
      opt.textContent = m.label;
      if (m.key === initial) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener("change", () => {
      onChange(sel.value as MetricKey);
      renderAll();
    });
    wrap.appendChild(sel);
    return wrap;
  };

  const logBtn = document.createElement("button");
  logBtn.type = "button";
  logBtn.className = "action-btn";
  logBtn.textContent = "Escala X: Log";
  logBtn.addEventListener("click", () => {
    useLog = !useLog;
    logBtn.textContent = useLog ? "Escala X: Log" : "Escala X: Linear";
    renderScatter();
  });

  controls.append(
    searchInput,
    makeSelect("Eixo X:", xKey, (k) => {
      xKey = k;
    }),
    makeSelect("Eixo Y:", yKey, (k) => {
      yKey = k;
    }),
    logBtn,
  );

  const body = document.createElement("div");
  body.className = "explorer-body";

  const scatterWrap = document.createElement("div");
  scatterWrap.className = "explorer-scatter-wrap";
  const scatterCanvas = document.createElement("canvas");
  scatterCanvas.width = 460;
  scatterCanvas.height = 300;
  scatterCanvas.className = "explorer-scatter";
  scatterCanvas.dataset.testid = "explorer-scatter";
  scatterCanvas.ariaLabel = "Gráfico de dispersão municipal";
  const scatterHint = document.createElement("div");
  scatterHint.className = "explorer-scatter-hint";
  scatterHint.textContent =
    "Clique em qualquer ponto ou linha da tabela para destacar o município no mapa. Notas: IDHM/Gini referem-se a 2010; taxas SSP-SP com população < 20k marcadas com flag.";
  scatterWrap.append(scatterCanvas, scatterHint);

  const tableWrap = document.createElement("div");
  tableWrap.className = "explorer-table-wrap";
  const table = document.createElement("table");
  table.className = "explorer-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  const tableCols: readonly { key: MetricKey | "nome"; label: string; unit: string }[] = [
    { key: "nome", label: "Município", unit: "" },
    { key: "pop", label: "Pop.", unit: "habitantes" },
    { key: "pib_pc", label: "PIB/hab", unit: "R$" },
    { key: "vinculos", label: "Vínculos", unit: "vínculos" },
    { key: "idhm", label: "IDHM (2010)", unit: "índice" },
    { key: "gini", label: "Gini (2010)", unit: "índice" },
    { key: "participacao_pct", label: "Part. TSE", unit: "%" },
    { key: "homicidio_100k", label: "Hom./100k", unit: "/100k" },
  ];

  for (const col of tableCols) {
    const th = document.createElement("th");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "explorer-sort-btn";
    btn.textContent = col.label;
    btn.addEventListener("click", () => {
      if (sortKey === col.key) {
        sortAsc = !sortAsc;
      } else {
        sortKey = col.key;
        sortAsc = col.key === "nome";
      }
      renderTable();
    });
    th.appendChild(btn);
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);

  const tbody = document.createElement("tbody");
  table.append(thead, tbody);
  tableWrap.appendChild(table);

  body.append(scatterWrap, tableWrap);
  card.append(header, controls, body);
  container.appendChild(card);

  let projectedPoints: { px: number; py: number; row: ExplorerRow }[] = [];

  const getFiltered = (): ExplorerRow[] => {
    const needle = normalizeSearchText(query);
    const list = needle
      ? dataset.municipios.filter((r) => normalizeSearchText(r.nome).includes(needle))
      : [...dataset.municipios];

    list.sort((a, b) => {
      if (sortKey === "nome") {
        return sortAsc ? a.nome.localeCompare(b.nome, "pt-BR") : b.nome.localeCompare(a.nome, "pt-BR");
      }
      const va = a[sortKey];
      const vb = b[sortKey];
      const na = va === null ? Number.NEGATIVE_INFINITY : va;
      const nb = vb === null ? Number.NEGATIVE_INFINITY : vb;
      return sortAsc ? na - nb : nb - na;
    });
    return list;
  };

  const renderTable = (): void => {
    const rows = getFiltered();
    countBadge.textContent = `${rows.length} de ${dataset.municipios.length} exibidos`;
    const frag = document.createDocumentFragment();
    for (const row of rows) {
      const tr = document.createElement("tr");
      tr.className = "explorer-row";
      tr.dataset.testid = "explorer-row";
      tr.tabIndex = 0;

      const tdName = document.createElement("td");
      tdName.textContent = row.baixa_populacao ? `${row.nome} (<20k)` : row.nome;
      tr.appendChild(tdName);

      for (const col of tableCols.slice(1)) {
        const td = document.createElement("td");
        const val = row[col.key as MetricKey];
        td.textContent = formatExplorerValue(val, col.unit);
        tr.appendChild(td);
      }

      const pick = (): void => {
        onSelectMunicipality(row);
      };
      tr.addEventListener("click", pick);
      tr.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") pick();
      });
      frag.appendChild(tr);
    }
    tbody.replaceChildren(frag);
  };

  const renderScatter = (): void => {
    const ctx = scatterCanvas.getContext("2d");
    const w = scatterCanvas.width;
    const h = scatterCanvas.height;
    const pad = 34;

    const validRows = dataset.municipios.filter((r) => r[xKey] !== null && r[yKey] !== null);
    scatterCanvas.dataset.pointCount = String(validRows.length);
    projectedPoints = [];

    if (!ctx) return;
    ctx.fillStyle = "#0b1422";
    ctx.fillRect(0, 0, w, h);

    if (validRows.length === 0) return;

    const xVals = validRows.map((r) => {
      const raw = r[xKey] ?? 0;
      return useLog ? safeLog10(raw) : raw;
    });
    const yVals = validRows.map((r) => r[yKey] ?? 0);

    const minX = Math.min(...xVals);
    const maxX = Math.max(...xVals);
    const minY = Math.min(...yVals);
    const maxY = Math.max(...yVals);
    const spanX = Math.max(1e-6, maxX - minX);
    const spanY = Math.max(1e-6, maxY - minY);

    ctx.strokeStyle = "#22344b";
    ctx.lineWidth = 1;
    ctx.strokeRect(pad, 12, w - pad - 12, h - pad - 12);

    const needle = normalizeSearchText(query);
    for (let i = 0; i < validRows.length; i++) {
      const row = validRows[i];
      if (!row) continue;
      const xv = xVals[i] ?? minX;
      const yv = yVals[i] ?? minY;
      const px = pad + ((xv - minX) / spanX) * (w - pad - 20) + 4;
      const py = h - pad - ((yv - minY) / spanY) * (h - pad - 20) - 4;
      projectedPoints.push({ px, py, row });

      const matched = !needle || normalizeSearchText(row.nome).includes(needle);
      ctx.beginPath();
      ctx.arc(px, py, matched ? 3.0 : 2.0, 0, Math.PI * 2);
      ctx.fillStyle = matched ? (row.baixa_populacao ? "#f59e0b" : "#38bdf8") : "rgba(100,116,139,0.28)";
      ctx.fill();
    }

    const xLabel = METRICS.find((m) => m.key === xKey)?.label ?? xKey;
    const yLabel = METRICS.find((m) => m.key === yKey)?.label ?? yKey;
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillText(`${xLabel}${useLog ? " (log)" : ""}`, pad, h - 10);
    ctx.fillText(yLabel, pad + 4, 24);
  };

  const renderAll = (): void => {
    renderTable();
    renderScatter();
  };

  searchInput.addEventListener("input", () => {
    query = searchInput.value;
    renderAll();
  });

  scatterCanvas.addEventListener("click", (ev) => {
    const rect = scatterCanvas.getBoundingClientRect();
    const sx = ((ev.clientX - rect.left) / rect.width) * scatterCanvas.width;
    const sy = ((ev.clientY - rect.top) / rect.height) * scatterCanvas.height;
    let best: ExplorerRow | null = null;
    let bestDist = 14;
    for (const pt of projectedPoints) {
      const d = Math.hypot(sx - pt.px, sy - pt.py);
      if (d < bestDist) {
        bestDist = d;
        best = pt.row;
      }
    }
    if (best) {
      onSelectMunicipality(best);
    }
  });

  renderAll();
  return { refresh: renderAll };
}
