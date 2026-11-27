# In your own words — PR 2 (Núcleo `--uf`, Censo/PIB, Grade 1 km e Motor Canvas 2D)

## Objetivo
Construir a base de dados reconciliada de São Paulo (Censo 2022, PIB e VABs 2021 do IBGE e Grade Estatística 2022 de 1 km) já parametrizada por `--uf` para escalar ao Brasil sem retrabalho, e substituir o mapa choropleth plano de `deck.gl` (`1.062 kB` JS + `unpkg.com` latente) por um motor **Canvas 2D** leve e determinístico com 4 lentes reais (`Ouro`, `Produção`, `Comida`, `Cidadãos`), barra de Yields, busca `/` nos 645 municípios, filtro interativo na legenda, minimapa e toggle entre **Atlas Estratégico** e **Modo Civ**.

## Problema que estamos resolvendo
1. O PR 1 entrega apenas a grade H3 de SP com contagem de municípios; ainda não existe motor de reconciliação dasimétrica (`município → hex`) nem dados socioeconômicos reais.
2. O formato JSON anterior (`sp_hex.json`, `327 KB` formatado) e a repetição de strings `h3` por lente estouram o orçamento no Amazonas; precisamos desde já de `<uf>/grid.json` compacto e lentes posicionais.
3. O bundle `deck.gl` custa `1.062 kB` JS e embute `https://unpkg.com/@loaders.gl`, conflitando com nossa meta de CSP estrita, performance e estética *Civilization*.
4. Precisamos de checkpoints por etapa (`raw → mun → hex → json`) e invariantes externos independentes para que nenhuma falha de parsing ou enfraquecimento de teste passe despercebido.

## Menor conjunto de mudanças que cumpre o requisito
- Fixar Python `>=3.13,<3.14` (`.python-version` e `pyproject.toml`) e adicionar `pyogrio` e `pyyaml` pinados.
- Criar `pipeline/types.py`, `pipeline/sources/_common.py` e as 3 fontes (`ibge_censo`, `ibge_pib`, `ibge_grade` 1 km) com fetch idempotente por SHA-256.
- Implementar `pipeline/reconcile/` (pesos dasimétricos via Grade 1 km com fallback documentado por área, `reconcile_sum` e `reconcile_rate`), `pipeline/checkpoints.py`, `pipeline/civ/` (`civ_rules.yaml` + exportador posicional compacto) e `pipeline/run_uf.py` (`--uf SP`).
- Substituir `web/src/` pelo motor Canvas 2D (removendo `@deck.gl/*` e `h3-js` do bundle web) consumindo `/data/sp/grid.json` e `/data/sp/lentes/*.json`, pronto para preview estático na Vercel.
- Escrever testes TDD antes do código cobrindo invariantes de reconciliação, fronteiras SIDRA, determinismo, orçamento de payload e zero `unpkg.com` em `web/dist/`.
