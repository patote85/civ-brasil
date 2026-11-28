# Evidências de Verificação — PR 6 (Base Brasil)

- `make data UF=BR` (2ª execução, 0 downloads): `5.570` municípios, `32.173` hexes H3 res 5 únicos, `739` hexes H3 res 3, `pop=203.080.756` (`0,000%` vs Censo 2022), `area=8.497.217,56 km²` (`-0,155%` vs `8.510.417,771 km²`), `br_arranjos.parquet` (`953` municípios em `294` arranjos populacionais IBGE 2ª ed.).
- Equivalência do recorte SP (`br/sp_grid.json` vs `sp/grid.json`): `hex_count=1091`, `pop=44.411.238`, `pib_mil`, `total_area_km2=248200.39` idênticos (`rel_tol=1e-9`).
- Orçamento de payload:
  - `br_res3.json`: `64 KB` raw (carga inicial Brasil + JS/CSS/HTML `~129 KB` raw, orçamento `<= 500 KB`).
  - `am_grid.json` (maior UF, `6.256` hexes): `255 KB` raw (orçamento `<= 1,0 MB`).
  - `am_lenses/*.json`: `19–37 KB` raw (orçamento `<= 80 KB`).
  - Total das 27 UFs em `web/public/data/br/`: `2,8 MB` raw.
- `make check`: `ruff`, `lint-imports` (2 contratos mantidos), `eslint`, `mypy --strict` (60 arquivos), `tsc --noEmit`, `pytest` (`37 passed`), `vitest` (`15 passed`).
- `make web-build`: `dist/assets/index-*.js` `50,15 KB` (`16,74 KB` gzip).
- `make verify`: OK (`1091 hexes H3 res 5`, `11 lentes`, `0 unpkg`).
- `make e2e`: `6 passed (17.2s)` em `1280×800` e `375×812` cobrindo SP piloto, URL state, Brasil H3 res 3 e drill-down sob demanda para `AM` (`6256 hexes`), `PE` (`415 hexes`) e `SP` (`1091 hexes`), com 0 erros de console.
