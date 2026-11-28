# Evidência de Verificação — PR 4

## 1. Gates executados
- `make check`: exit `0` (`ruff`, `lint-imports` 2/2, `eslint`, `mypy --strict` 53 arquivos, `tsc --noEmit`, `pytest` 29/29, `vitest` 11/11)
- `make data-sp`: exit `0` (`Fontes SP sincronizadas (sem download: 14/14)`)
- `make web-build`: exit `0` (`dist/assets/index-5hm0G0yf.js` = `38.96 kB` raw / `13.27 kB` gzip)
- `make verify`: exit `0` (`Verificacao OK: web/dist presente (38957 B JS, 0 unpkg), 1091 hexes H3 res 5, 11 lentes, pop=44,411,238, area=248200.39 km2.`)
- `make e2e`: exit `0` (`2 passed (9.5s)` em `desktop-1280x800` e `mobile-375x812`, capturas salvas em `docs/evidencias/pr4/`)

## 2. Blast Radius — Preservação PR 1, PR 2 e PR 3
- `git diff --stat main -- data/processed/sp_municipio_hex.parquet web/public/data/sp_hex.json data/processed/sp/dasymetric_weights.parquet data/processed/sp/mun_base.parquet data/processed/sp/hex_base.parquet data/processed/sp/hex_economia.parquet data/processed/sp/pontos_infra.parquet`: **vazio (zero diff)**.

## 3. Orçamentos de payload web (`web/public/data/sp/`)
- `explorer.json`: **182.990 B (~179 KB)** (`≤ 350 KB` orçamento)
- `lealdade.json`: **6,5 KB**, `desenvolvimento.json`: **5,4 KB**, `descontentamento.json`: **5,5 KB** (`≤ 50 KB` cada)
- Total JSONs SP: **~516 KB** (`≤ 1.500 KB` orçamento)
