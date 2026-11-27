import { LEGEND_BUCKETS, type HexDatum } from "./data";

export function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function buildTooltipHtml(hex: HexDatum): string {
  const plural = hex.municipio_count === 1 ? "município" : "municípios";
  const areaFormatted = hex.area_km2.toFixed(1).replace(".", ",");
  const nomes = hex.municipios.map(escapeHtml).join(", ");
  return [
    '<div class="deck-tooltip-card">',
    `<div class="deck-tooltip-title">H3 ${escapeHtml(hex.h3)}</div>`,
    `<div class="deck-tooltip-meta">${hex.municipio_count} ${plural} · ${areaFormatted} km²</div>`,
    `<div class="deck-tooltip-list">${nomes}</div>`,
    "</div>",
  ].join("");
}

export function renderLegend(container: HTMLElement): void {
  container.replaceChildren();

  const title = document.createElement("h2");
  title.className = "legend-title";
  title.textContent = "Municípios por hex";
  container.appendChild(title);

  const list = document.createElement("ul");
  list.className = "legend-items";

  for (const bucket of LEGEND_BUCKETS) {
    const item = document.createElement("li");
    item.className = "legend-item";

    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    const [r, g, b] = bucket.color;
    swatch.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;

    const label = document.createElement("span");
    label.textContent = bucket.label;

    item.append(swatch, label);
    list.appendChild(item);
  }

  container.appendChild(list);
}

export function renderStatus(container: HTMLElement, text: string, isError = false): void {
  container.textContent = text;
  container.classList.toggle("error", isError);
}
