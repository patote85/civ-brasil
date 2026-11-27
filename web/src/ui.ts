import {
  buildLegendBuckets,
  formatPtBrCompact,
  NO_DATA_COLOR,
  type LensMetadata,
  type PositionalLensData,
  type UfGridDataset,
  type VisualMode,
} from "./data";

export function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function renderYieldsBar(container: HTMLElement, grid: UfGridDataset): void {
  container.replaceChildren();
  const items: readonly [string, string][] = [
    ["População", formatPtBrCompact(grid.yields.pop, "habitantes")],
    ["Ouro (PIB)", formatPtBrCompact(grid.yields.pib_mil, "R$ mil")],
    ["Produção (Ind.)", formatPtBrCompact(grid.yields.vab_ind_mil, "R$ mil")],
    ["Comida (Agro)", formatPtBrCompact(grid.yields.vab_agro_mil, "R$ mil")],
    ["Território", `${grid.hex_count} hex · ${grid.mun_count} mun`],
  ];

  for (const [label, value] of items) {
    const pill = document.createElement("span");
    pill.className = "yield-pill";

    const lbl = document.createElement("span");
    lbl.className = "yield-label";
    lbl.textContent = `${label}:`;

    const val = document.createElement("strong");
    val.textContent = value;

    pill.append(lbl, val);
    container.appendChild(pill);
  }
}

export function renderLensButtons(
  container: HTMLElement,
  lenses: readonly LensMetadata[],
  activeId: string,
  onSelect: (id: string) => void,
): void {
  container.replaceChildren();
  for (const lens of lenses) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.role = "tab";
    btn.ariaSelected = String(lens.id === activeId);
    btn.className = lens.id === activeId ? "lens-btn active" : "lens-btn";
    btn.textContent = `${lens.civ_name} (${lens.br_name})`;
    btn.dataset.lensId = lens.id;
    btn.addEventListener("click", () => onSelect(lens.id));
    container.appendChild(btn);
  }
}

export function renderLegend(
  container: HTMLElement,
  lensMeta: LensMetadata,
  lensData: PositionalLensData,
  mode: VisualMode,
  activeBucket: number | null,
  onHoverBucket: (bucketIndex: number | null) => void,
): void {
  container.replaceChildren();

  const title = document.createElement("h2");
  title.className = "legend-title";
  title.textContent = `${lensMeta.civ_name} · ${lensMeta.br_name}`;

  const sub = document.createElement("div");
  sub.className = "legend-sub";
  sub.textContent = `Unidade: ${lensMeta.unit}`;

  const list = document.createElement("ul");
  list.className = "legend-items";

  const buckets = buildLegendBuckets(lensData, lensMeta.palette, mode);
  buckets.forEach((bucket, idx) => {
    const item = document.createElement("li");
    item.className = activeBucket === idx ? "legend-item active" : "legend-item";

    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = bucket.color;

    const label = document.createElement("span");
    label.textContent = bucket.label;

    item.addEventListener("mouseenter", () => onHoverBucket(idx));
    item.addEventListener("mouseleave", () => onHoverBucket(null));
    item.append(swatch, label);
    list.appendChild(item);
  });

  if (lensData.values.some((v) => v === null)) {
    const emptyItem = document.createElement("li");
    emptyItem.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = NO_DATA_COLOR;
    const label = document.createElement("span");
    label.textContent = "Sem dado";
    emptyItem.append(swatch, label);
    list.appendChild(emptyItem);
  }

  const meta = document.createElement("div");
  meta.className = "legend-meta";
  meta.textContent = `Fonte: ${lensMeta.source_label} · Ano: ${lensMeta.ano_ref}. ${lensMeta.note}`;

  container.append(title, sub, list, meta);
}

export function buildTooltipHtml(
  grid: UfGridDataset,
  hexIndex: number,
  lensMeta: LensMetadata,
  lensData: PositionalLensData,
): string {
  const h3Cell = grid.h3[hexIndex] ?? "";
  const area = grid.area_km2[hexIndex] ?? 0;
  const munIndices = grid.mun_idx[hexIndex] ?? [];
  const nomes = munIndices
    .map((idx) => grid.municipios[idx] ?? "")
    .filter(Boolean)
    .map(escapeHtml)
    .join(", ");

  const rawValue = lensData.values[hexIndex] ?? null;
  const formattedVal =
    rawValue === null ? "Sem dado" : formatPtBrCompact(rawValue, lensMeta.unit);

  return [
    `<div class="tooltip-title">H3 ${escapeHtml(h3Cell)}</div>`,
    `<div class="tooltip-val">${escapeHtml(lensMeta.civ_name)}: ${escapeHtml(formattedVal)}</div>`,
    `<div class="tooltip-muns">${munIndices.length} ${munIndices.length === 1 ? "município" : "municípios"} · ${area.toFixed(1).replace(".", ",")} km²</div>`,
    `<div class="tooltip-muns">${nomes}</div>`,
  ].join("");
}

export function renderStatus(container: HTMLElement, text: string, isError = false): void {
  container.textContent = text;
  container.classList.toggle("error", isError);
}
