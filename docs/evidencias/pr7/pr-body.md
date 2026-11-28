## Resumo — PR 7: Fontes Nacionais (`--uf BR`, 5.570 municípios)

- **3 novas fontes nacionais oficiais:**
  - `pipeline/sources/ipea_atlas_violencia/` — **Atlas da Violência (IPEA/FBSP, `AVIOL12_THOMIC`)**: `5.570/5.570` municípios, com flag `baixa_populacao (<20k)` e teste de blindagem garantindo que `descontentamento` nacional nunca referencia `ssp_sp` nem `sinesp_vde`.
  - `pipeline/sources/mds_bolsa/` — **Bolsa Família (MDS/IPEA, `FAM_PBF` + `VAL_PBF`)**: `18.618.236` famílias (`5.570/5.570` municípios).
  - `pipeline/sources/ibge_saneamento/` — **Saneamento Básico (IBGE Censo 2022 SIDRA 6805, `c11558/46290`)**: `5.545/5.570` municípios em `[0, 100]`.
- **Extensão nacional em passo único (`uf=None`) das fontes existentes:**
  - `RAIS 2025` (`59.966.833` vínculos, `5.570/5.570`), `INEP Escolar 2024` (`47.088.922` matrículas), `INEP Superior 2025` (`8.873.206` matrículas), `INEP IDEB 2025` (`5.490/5.570`), `CNES 2025` (`542.006` leitos), `ANEEL/EPE` (`3.001` usinas / `204.392,0 MW`), `TSE 2024` (`5.568/5.568` municípios votantes com os 13 aliases oficiais nacionais + exceções DF/FN/Boa Esperança do Norte) e `IPEA IDHM/Gini 2010` (`5.564/5.570` com ausentes pós-2010 explícitos).
- **Consolidação determinística (`pipeline/run_br_sources.py`, `Makefile` `data-br-sources`):**
  - Gerados `data/processed/br_municipios_indicators.parquet` (`5.570` linhas) e `data/checkpoints/br_sources.json` (`0` downloads na 2ª rodada, `2 min 45 s`).
- **Gates:** `make check` (`43 pytest` + `15 vitest`), `make web-build`, `make verify`, `make e2e` (`6/6`) todos verdes.
