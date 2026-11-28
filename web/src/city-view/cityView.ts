import { formatPtBrCompact, type CityProfile } from "../data";

function makeStatCard(label: string, value: string): HTMLElement {
  const card = document.createElement("div");
  card.className = "city-stat-card";
  const lbl = document.createElement("span");
  lbl.className = "city-stat-label";
  lbl.textContent = label;
  const val = document.createElement("strong");
  val.className = "city-stat-value";
  val.textContent = value;
  card.append(lbl, val);
  return card;
}

function makeSection(titleText: string): HTMLElement {
  const section = document.createElement("section");
  section.className = "city-section";
  const h3 = document.createElement("h3");
  h3.className = "city-section-title";
  h3.textContent = titleText;
  section.appendChild(h3);
  return section;
}

function formatIdeb(val: number | null): string {
  return val === null ? "—" : val.toFixed(1).replace(".", ",");
}

export function renderCityView(
  container: HTMLElement,
  city: CityProfile,
  onClose: () => void,
): void {
  container.replaceChildren();

  const header = document.createElement("div");
  header.className = "city-header";

  const titleWrap = document.createElement("div");
  const title = document.createElement("h2");
  title.className = "city-title";
  title.textContent = city.nome;
  const sub = document.createElement("div");
  sub.className = "city-subtitle";
  sub.textContent = `IBGE ${city.cd_mun} · City View`;
  titleWrap.append(title, sub);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "action-btn";
  closeBtn.textContent = "Fechar";
  closeBtn.ariaLabel = "Fechar City View";
  closeBtn.addEventListener("click", onClose);

  header.append(titleWrap, closeBtn);
  container.appendChild(header);

  const yieldsGrid = document.createElement("div");
  yieldsGrid.className = "city-stats-grid";
  yieldsGrid.append(
    makeStatCard("População", formatPtBrCompact(city.pop, "habitantes")),
    makeStatCard("Ouro (PIB)", formatPtBrCompact(city.pib_mil, "R$ mil")),
    makeStatCard("Vínculos RAIS", formatPtBrCompact(city.vinculos, "vínculos")),
    makeStatCard("Estab. RAIS", formatPtBrCompact(city.estabelecimentos_rais, "estab")),
  );
  container.appendChild(yieldsGrid);

  const distSection = makeSection("Distritos Especializados (QL ≥ 2 · CNAE 2 dígitos)");
  if (city.districts.length === 0) {
    const empty = document.createElement("p");
    empty.className = "city-empty";
    empty.textContent = "Sem especialização acima de QL 2,0 registrada na RAIS.";
    distSection.appendChild(empty);
  } else {
    const list = document.createElement("ul");
    list.className = "city-districts-list";
    for (const d of city.districts) {
      const li = document.createElement("li");
      li.className = "city-district-item";

      const left = document.createElement("div");
      left.className = "city-district-name";
      left.textContent = d.name;

      const meta = document.createElement("div");
      meta.className = "city-district-meta";
      meta.textContent = `CNAE ${d.div} · ${d.vinculos.toLocaleString("pt-BR")} vínculos`;

      const badge = document.createElement("span");
      badge.className = "city-ql-badge";
      badge.textContent = `${d.ql.toFixed(1).replace(".", ",")}x QL`;

      const info = document.createElement("div");
      info.append(left, meta);
      li.append(info, badge);
      list.appendChild(li);
    }
    distSection.appendChild(list);
  }
  container.appendChild(distSection);

  const citSection = makeSection("Cidadãos por Setor (RAIS)");
  if (city.citizens.length === 0) {
    const empty = document.createElement("p");
    empty.className = "city-empty";
    empty.textContent = "Composição setorial indisponível.";
    citSection.appendChild(empty);
  } else {
    const bars = document.createElement("div");
    bars.className = "city-citizens-bars";
    for (const c of city.citizens) {
      const row = document.createElement("div");
      row.className = "city-bar-row";

      const labelRow = document.createElement("div");
      labelRow.className = "city-bar-labels";
      const sName = document.createElement("span");
      sName.textContent = c.sector;
      const sVal = document.createElement("span");
      sVal.textContent = `${c.pct.toFixed(1).replace(".", ",")}% (${formatPtBrCompact(c.vinculos, "vínculos")})`;
      labelRow.append(sName, sVal);

      const track = document.createElement("div");
      track.className = "city-bar-track";
      const fill = document.createElement("div");
      fill.className = "city-bar-fill";
      fill.style.width = `${Math.max(2, Math.min(100, c.pct))}%`;
      track.appendChild(fill);

      row.append(labelRow, track);
      bars.appendChild(row);
    }
    citSection.appendChild(bars);
  }
  container.appendChild(citSection);

  const eduSection = makeSection("Ciência & Educação (INEP)");
  const eduGrid = document.createElement("div");
  eduGrid.className = "city-stats-grid";
  eduGrid.append(
    makeStatCard("Escolas (2024)", city.education.escolas.toLocaleString("pt-BR")),
    makeStatCard("Matr. Básica", formatPtBrCompact(city.education.matriculas_basica, "matrículas")),
    makeStatCard("IES (2025)", city.education.ies.toLocaleString("pt-BR")),
    makeStatCard("Matr. Superior", formatPtBrCompact(city.education.matriculas_superior, "matrículas")),
    makeStatCard("IDEB Anos Inic.", formatIdeb(city.education.ideb_ai)),
    makeStatCard("IDEB Anos Fin.", formatIdeb(city.education.ideb_af)),
    makeStatCard("IDEB Ens. Médio", formatIdeb(city.education.ideb_em)),
    makeStatCard("IDEB Médio", formatIdeb(city.education.ideb_medio)),
  );
  eduSection.appendChild(eduGrid);
  container.appendChild(eduSection);

  const healthSection = makeSection("Saúde (CNES)");
  const healthGrid = document.createElement("div");
  healthGrid.className = "city-stats-grid";
  healthGrid.append(
    makeStatCard("Estabelecimentos", city.health.estabelecimentos.toLocaleString("pt-BR")),
    makeStatCard("Hospitais", city.health.hospitais.toLocaleString("pt-BR")),
    makeStatCard("Leitos", city.health.leitos.toLocaleString("pt-BR")),
  );
  healthSection.appendChild(healthGrid);
  container.appendChild(healthSection);

  const infraSection = makeSection("Infraestrutura & Energia");
  const infraGrid = document.createElement("div");
  infraGrid.className = "city-stats-grid";
  infraGrid.append(
    makeStatCard("Usinas (EPE/ANEEL)", city.infra.usinas.toLocaleString("pt-BR")),
    makeStatCard("Potência Instalada", formatPtBrCompact(city.infra.potencia_mw, "MW")),
    makeStatCard("Portos (InfraSA)", city.infra.portos.toLocaleString("pt-BR")),
  );
  infraSection.appendChild(infraGrid);
  container.appendChild(infraSection);

  if (city.sensitive) {
    const sensSection = makeSection("Indicadores Cívicos, IDHM (2010) & SSP-SP (2025)");
    const sensGrid = document.createElement("div");
    sensGrid.className = "city-stats-grid";
    const idhmStr =
      city.sensitive.idhm === null ? "—" : city.sensitive.idhm.toFixed(3).replace(".", ",");
    const giniStr =
      city.sensitive.gini === null ? "—" : city.sensitive.gini.toFixed(3).replace(".", ",");
    sensGrid.append(
      makeStatCard("Participação TSE 2024", formatPtBrCompact(city.sensitive.participacao_pct, "%")),
      makeStatCard("IDHM (2010)", idhmStr),
      makeStatCard("Gini (2010)", giniStr),
      makeStatCard("Homicídios/100k", formatPtBrCompact(city.sensitive.homicidio_100k, "/100k")),
      makeStatCard("Roubos/100k", formatPtBrCompact(city.sensitive.roubo_100k, "/100k")),
    );
    sensSection.appendChild(sensGrid);
    container.appendChild(sensSection);
  }

  const footer = document.createElement("footer");
  footer.className = "city-footer";
  footer.textContent =
    "Fontes: IBGE Censo 2022 · IBGE PIB 2021 · MTE RAIS 2025 · INEP 2024/2025 · CNES 2025 · EPE/ANEEL · InfraSA · TSE 2024 · IPEA 2010 · SSP-SP 2025.";
  container.appendChild(footer);
}
