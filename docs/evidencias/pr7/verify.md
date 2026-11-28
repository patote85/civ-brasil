# Evidências de Verificação — PR 7 (Fontes Nacionais)

- `make data-br-sources` (`0` downloads após cache inicial, `2 min 45 s` em passo único nacional):
  - `data/processed/br_municipios_indicators.parquet`: `5.570` municípios únicos.
  - `pop_2022`: `203.080.756` (`5.570/5.570`).
  - `RAIS 2025`: `59.966.833` vínculos (`5.570/5.570`).
  - `INEP Escolar 2024`: `47.088.922` matrículas (`5.570/5.570`).
  - `INEP Superior 2025`: `8.873.206` matrículas (`1.193` municípios com oferta).
  - `INEP IDEB 2025 AF`: `5.490/5.570` municípios.
  - `CNES 2025`: `542.006` leitos (`3.603` municípios com leitos).
  - `EPE/ANEEL Usinas`: `3.001` usinas (`204.392,0 MW`).
  - `TSE 2024`: `156.654.236` aptos, `122.650.344` comparecimentos (`5.568/5.568` municípios votantes; DF e Fernando de Noronha/PE sem eleição municipal).
  - `IPEA/FBSP Atlas da Violência (AVIOL12_THOMIC)`: `5.570/5.570` municípios (`descontentamento_nacional_source = ipea_atlas_violencia`, blindado contra mistura de `ssp_sp` e `sinesp_vde`).
  - `MDS/IPEA Bolsa Família (FAM_PBF/VAL_PBF)`: `18.618.236` famílias (`5.570/5.570`).
  - `IBGE Censo 2022 Saneamento (SIDRA 6805)`: `5.545/5.570` municípios.
  - `IPEA/PNUD IDHM/Gini 2010`: `5.564/5.570` (6 ausentes explícitos pós-2010/OData4 registrados).
- `make check`: `ruff`, `lint-imports` (91 arquivos, 2 contratos mantidos), `eslint`, `mypy --strict` (68 arquivos), `tsc --noEmit`, `pytest` (`43 passed`), `vitest` (`15 passed`).
- `make web-build`, `make verify`, `make e2e` (`6 passed` em `16.5s`): zero regressão.
