## Resumo — PR 6: Base Brasil (`--uf BR`, H3 res 3 + res 5 sob demanda, 5.570 municípios)

- **Pipeline nacional em streaming (`pipeline/run_br.py`, `pipeline/grid/br.py`, `pipeline/sources/ibge_malhas/`, `pipeline/sources/ibge_arranjos/`):**
  - Generalizada a malha municipal IBGE para as 27 UFs (`5.570` municípios do Censo 2022, filtrando lagoas não-municipais do RS `4300001`/`4300002`, `GeometryCollection` após `make_valid` no AM e o município pós-Censo 2022 `5101837` Boa Esperança do Norte/MT ausente na malha 2022).
  - Permitido VAB setorial negativo legítimo na SIDRA 5938 (ex.: Cachoeira Dourada/GO `5204250`), mantendo rejeição para PIB total negativo.
  - Ingeridos os **Arranjos Populacionais oficiais do IBGE** (`tab01.xlsx`, `294` arranjos / `953` municípios) para `data/processed/br_arranjos.parquet`.
  - Gerados `web/public/data/br/br_res3.json` (`739` hexes H3 res 3, `64 KB`) e os grids/lentes compactos das 27 UFs (`32.173` hexes H3 res 5 únicos, `am_grid.json` `255 KB`, total `2,8 MB`).
- **Frontend Brasil LOD (`web/src/br/brData.ts`, `web/src/url-state/urlState.ts`, `web/src/main.ts`, `web/index.html`):**
  - Botão **Brasil (27 UFs)** e suporte em URL (`?uf=BR`, `?uf=AM`, `?uf=PE`, mantendo SP padrão sem regressão).
  - Drill-down por clique em qualquer UF no mapa nacional H3 res 3 carregando o grid H3 res 5 sob demanda.
- **Invariantes e Verificação (`tests/test_br_invariants.py`, `web/src/data.test.ts`, `web/e2e/app.spec.ts`):**
  - `5.570` municípios, `pop=203.080.756` (`0,000%` vs Censo 2022), `area=8.497.217,56 km²` (`-0,155%`), recorte SP idêntico ao piloto (`rel_tol=1e-9`), `0` downloads na 2ª execução de `make data UF=BR`.
  - `make check` (`37 pytest` + `15 vitest`), `make web-build`, `make verify` e `make e2e` (`6/6` desktop + mobile) verdes.
