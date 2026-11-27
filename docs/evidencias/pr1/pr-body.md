## In your own words

Este PR inaugura a base técnica e o primeiro recorte funcional do **civ-brasil** (piloto do estado de São Paulo):

- Esqueleto completo do repositório com Python 3.13 (`uv`, `ruff`, `mypy --strict`, `pytest`, `import-linter`) e web estático (`Vite 6`, `TypeScript 5`, `Vitest 3`, `ESLint 9`, `deck.gl 9`, `h3-js 4`), `Makefile` portável (offline no sandbox via `wildcard`, online no CI), CI em `pull_request`, `vercel.json`, ADR 0001, catálogo de QA, `GEMINI.md` e `.cursor/BUGBOT.md`.
- Ingestão determinística e idempotente da malha e da relação de municípios de SP do IBGE com verificação SHA-256 em `data/manifest.json` e schema tipado na fronteira.
- Grade H3 resolução 5 cobrindo os 645 municípios de SP em projeção de área igual (`Albers Equal Area`), gerando `data/processed/sp_municipio_hex.parquet` e `web/public/data/sp_hex.json` com prova TDD de todos os invariantes (cobertura, frações, área, faixa de hexes e determinismo).
- Mapa mínimo estático em `web/` com `H3HexagonLayer` colorido pelo número de municípios por hexágono, tooltip, legenda e layout responsivo para 1280 px e 375 px, sem mapa base e sem chamadas externas de rede.

## Princípios aplicados

- **`principle-boundary-discipline`**: validação de dados, SHA-256 e JSON nas fronteiras (`pipeline/sources/ibge_malhas/loader.py`, `web/src/data.ts`), lógica espacial/UI em funções puras e limites entre módulos garantidos por `import-linter`.
- **`principle-test-behavior-not-implementation`**: testes orientados a invariantes e comportamentos observáveis pela interface pública, sem mocks frágeis e sem acesso à rede.
- **`principle-prove-it-works`**: verificação direta dos artefatos reais gerados (`make check`, `make data-sp` 2x sem re-download, `make web-build`, `make verify`).
- **`tdd`**: testes de invariantes executados falhando antes da implementação e passando depois (`docs/evidencias/pr1/tdd.md`).
- **`no-comments`**: código limpo sem comentários narrativos desnecessários.

## Evidências

- SHA do commit: `<adicionar pelo operador>`
- `timeout 300 make -C /workspace/civ-brasil setup`: **exit 0**
- `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_grid_invariants.py` (TDD RED): **exit 1**
- `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_grid_invariants.py` (TDD GREEN): **exit 0**
- `timeout 600 make -C /workspace/civ-brasil check`: **exit 0** (`ruff`, `lint-imports`, `eslint`, `mypy --strict`, `tsc --noEmit`, 9 testes `pytest`, 5 testes `vitest`)
- `timeout 300 make -C /workspace/civ-brasil data-sp` (1ª execução): **exit 0** (sem download; 645 municípios, 3.688 linhas, 1.091 hexes, 248.200,39 km²)
- `timeout 300 make -C /workspace/civ-brasil data-sp` (2ª execução): **exit 0** (sem download; saída e manifesto idênticos)
- `timeout 300 make -C /workspace/civ-brasil web-build`: **exit 0**
- `timeout 120 make -C /workspace/civ-brasil verify`: **exit 0**

## Risco e /teach

**Riscos e escopo futuro:**
- Responsividade 1280/375 px e UI foram testadas em `jsdom` + build Vite real; inspeção visual WebGL em navegador headless (Playwright) ficou para uma etapa seguinte.
- Chunk JS principal de `~303 kB` gzip (`deck.gl` + `h3-js`) pode ser otimizado com code-splitting quando novas camadas entrarem.
- `pipeline/reconcile/` permanece como stub para os dados temáticos dos próximos PRs.

**/teach:**
1. Projetar vértices compartilhados dos hexágonos H3 em Albers Equal Area preserva partição exata sem lacunas nem sobreposições, fechando `sum(frac) = 1.0` com precisão `< 1e-6`.
2. Combinar `h3shape_to_cells_experimental(..., contain="overlap")`, `grid_disk(cell, 1)` e interseção exata em Shapely cobre 100% dos 645 municípios de SP em 1.091 hexes (`248.200,39 km²`, −0,0075% da área oficial IBGE).
3. Escrita atômica (`mkstemp` + `fsync` + `os.replace`) e conferência SHA-256 na fronteira blindam o pipeline contra falhas de rede e I/O interrompido.
4. Exportar variáveis offline apenas via `$(wildcard ...)` no `Makefile` mantém o repo 100% portável entre sandbox offline e CI online.

## Achados do Bugbot e correções

