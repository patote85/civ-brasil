# Relatório PR 1 — civ-brasil: esqueleto, grade H3 de SP e mapa mínimo

## 1. In your own words

O objetivo do PR 1 é inaugurar a base técnica e o primeiro recorte funcional do **civ-brasil** (piloto do estado de São Paulo), com processamento 100% determinístico e auditável, sem banco de dados, sem modelos de linguagem lendo dados brutos e sem serviços pagos:

- Estruturar o repositório com governança de qualidade desde o primeiro PR (Python 3.13 com `uv`, `ruff`, `mypy --strict`, `pytest`, `import-linter`; frontend Vite 6 + TypeScript estrito + Vitest 3 + ESLint 9 + deck.gl 9 + `h3-js` 4; Makefile com suporte automático a cache offline no sandbox e modo online no CI; CI em `pull_request`, ADR 0001, catálogo de QA, `GEMINI.md` e `.cursor/BUGBOT.md`).
- Ingerir de forma idempotente a malha municipal e a lista de municípios de SP do IBGE, validando SHA-256 contra `data/manifest.json` e `SHA256SUMS`, reaproveitando arquivos locais sem download repetido e expondo `Municipio` tipado na fronteira.
- Projetar os 645 municípios de SP sobre a grade H3 resolução 5 (incluindo bordas) usando projeção de área igual (`+proj=aea +lat_0=-32 +lon_0=-60 +lat_1=-5 +lat_2=-42 +ellps=GRS80 +units=m`), gerando `data/processed/sp_municipio_hex.parquet` e `web/public/data/sp_hex.json` com prova TDD de todos os invariantes.
- Entregar o mapa mínimo estático em `web/` (`H3HexagonLayer`, sem mapa base e sem requisições externas além do JSON estático), responsivo em 1280 px e 375 px, pronto para deploy na Vercel (`vercel.json`) e verificado por `make verify`.

Registro original: `docs/evidencias/pr1/00-in-your-own-words.md`.

## 2. Princípios do pstack aplicados

- **`principle-boundary-discipline`**: validação de schema, integridade SHA-256, normalização de geometrias e parsing JSON concentrados nas fronteiras (`pipeline/sources/ibge_malhas/loader.py` e `web/src/data.ts`), mantendo a lógica espacial (`pipeline/grid/h3_grid.py`) e de visualização (`web/src/ui.ts`) em funções puras e cascas finas (`pipeline/grid/sp.py`, `web/src/main.ts`). Fronteira arquitetural garantida por `import-linter`.
- **`principle-test-behavior-not-implementation`**: todos os testes exercitam a interface pública (`load_municipios_from_files`, `ensure_sp_raw_files`, `build_municipio_hex_table`, `build_hex_summaries`, `verify_artifacts`, `parseSpHexDataset`, `renderLegend`, `buildTooltipHtml`) e verificam efeitos observáveis (invariantes matemáticos, erros de integridade/rede, escrita atômica e determinismo).
- **`principle-prove-it-works`**: validação direta dos artefatos reais produzidos (`sp_municipio_hex.parquet`, `sp_hex.json`, `data/manifest.json`, `web/dist`), incluindo segunda execução de `make data-sp` comprovando ausência de download e preservação do manifesto, e script determinístico `make verify`.
- **`tdd`**: testes de invariantes escritos e executados primeiro em estado RED (`exit 1`) e só depois satisfeitos pela implementação em estado GREEN (`exit 0`), documentados em `docs/evidencias/pr1/tdd.md`.
- **`no-comments`**: código mantido sem comentários supérfluos ou narrativos; documentação restrita aos artefatos explicitamente solicitados.

## 3. Comandos de gate e exit codes

| Comando | Exit code | Resultado observado |
| --- | --- | --- |
| `timeout 300 make -C /workspace/civ-brasil setup` | `0` | Instalou 25 pacotes Python (versões exatas de `python-versoes.txt`) e 340 pacotes npm offline, gerando `uv.lock` e `web/package-lock.json`. |
| `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_grid_invariants.py` (TDD RED) | `1` | 2 testes de invariantes falharam com `NotImplementedError` antes da implementação. |
| `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_grid_invariants.py` (TDD GREEN) | `0` | 2 testes de invariantes passaram sem warnings em `1.26s`. |
| `timeout 600 make -C /workspace/civ-brasil check` | `0` | `ruff` OK, `lint-imports` (2/2 contratos KEPT), `eslint` OK, `mypy --strict` (13 arquivos OK), `tsc --noEmit` OK, `pytest` (9 passed), `vitest` (5 passed). |
| `timeout 300 make -C /workspace/civ-brasil data-sp` (1ª execução) | `0` | Sem download; gerou 645 municípios, 3.688 linhas Parquet, 1.091 hexes H3 res 5, área `248.200,39 km²` (−0,0075% vs 248.219 km²). |
| `timeout 300 make -C /workspace/civ-brasil data-sp` (2ª execução) | `0` | Sem download (`arquivos locais validos`); saída e `fetched_at` do manifesto idênticos. |
| `timeout 300 make -C /workspace/civ-brasil web-build` | `0` | Build Vite 6 concluído em `5.45s` (`web/dist/index.html`, CSS, bundles JS e `web/dist/data/sp_hex.json`). |
| `timeout 120 make -C /workspace/civ-brasil verify` | `0` | `Verificacao OK: web/dist presente, 1091 hexes H3 res 5, area=248200.39 km2.` |

## 4. Arquivos criados e modificados

### Modificados
- `.gitignore`
- `README.md`

### Criados
- Configuração e governança: `pyproject.toml`, `uv.lock`, `Makefile`, `vercel.json`, `LICENSE`, `GEMINI.md`, `.cursor/BUGBOT.md`, `.github/workflows/ci.yml`, `docs/adr/0001-civ-brasil.md`, `qa/catalog/README.md`.
- Pipeline Python: `pipeline/__init__.py`, `pipeline/sources/__init__.py`, `pipeline/sources/ibge_malhas/__init__.py`, `pipeline/sources/ibge_malhas/loader.py`, `pipeline/grid/__init__.py`, `pipeline/grid/h3_grid.py`, `pipeline/grid/sp.py`, `pipeline/reconcile/__init__.py`, `pipeline/verify.py`.
- Dados e manifesto: `data/manifest.json`, `data/processed/sp_municipio_hex.parquet`, `web/public/data/sp_hex.json`.
- Testes Python e fixtures: `tests/__init__.py`, `tests/fixtures/sp_sample_malha.geojson`, `tests/fixtures/sp_sample_municipios.json`, `tests/test_grid_invariants.py`, `tests/test_ibge_malhas.py`, `tests/test_verify_and_io.py`.
- Frontend web: `web/package.json`, `web/package-lock.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/vitest.config.ts`, `web/eslint.config.js`, `web/index.html`, `web/src/styles.css`, `web/src/data.ts`, `web/src/ui.ts`, `web/src/main.ts`, `web/src/data.test.ts`.
- Evidências do PR 1: `docs/evidencias/pr1/00-in-your-own-words.md`, `docs/evidencias/pr1/tdd.md`, `docs/evidencias/pr1/relatorio.md`, `docs/evidencias/pr1/pr-body.md`.

## 5. Riscos e o que ficou fora

- **Validação visual em navegador real (WebGL)**: no sandbox sem browser headless, a responsividade 1280/375 px e a renderização de legenda/tooltip foram verificadas por testes Vitest (`jsdom`) + build real do Vite; a inspeção visual WebGL em Chromium real (ex.: Playwright) ficou fora deste PR.
- **Tamanho do chunk JS principal (`~1.06 MB` bruto / `~303 kB` gzip)**: decorre de `@deck.gl/core` + `@deck.gl/geo-layers` + `h3-js`; aceitável para o piloto estático, mas futuro code-splitting pode reduzir o bundle inicial.
- **Módulo `pipeline/reconcile/`**: criado apenas com `__init__.py`, aguardando as próximas fontes temáticas (população, economia, educação, saúde) nos PRs seguintes.
- **Commit, PR e deploy Vercel**: deixados para o operador conforme regra de execução.

## 6. /teach (em até 5 linhas)

1. Hexágonos H3 projetados pelos vértices compartilhados em Albers Equal Area formam uma partição sem sobreposições nem lacunas, garantindo que a soma das frações por município feche exatamente em `1.0` (`< 1e-6`).
2. Usar `contain="overlap"` do H3 v4 combinado com `grid_disk(cell, 1)` e recorte exato em Shapely garante 100% de cobertura de bordas e municípios pequenos, totalizando 1.091 hexágonos e 248.200,39 km² em SP.
3. Escritas atômicas (`mkstemp` + `fsync` + `os.replace`) e validação de SHA-256 na fronteira impedem corrupção silenciosa em falhas de rede ou I/O interrompido.
4. Detectar caches locais apenas no `Makefile` via `$(wildcard ...)` permite rodar 100% offline no sandbox mantendo `pyproject.toml`, `package.json` e o CI do GitHub portáveis.

## 7. Rascunho do corpo do PR

Gravado em `docs/evidencias/pr1/pr-body.md`.
