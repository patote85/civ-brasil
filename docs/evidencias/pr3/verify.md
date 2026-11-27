# Evidência de Verificação — PR 3

## 1. Gates executados
- `make check`: exit `0` (ruff, lint-imports 2/2, eslint, mypy --strict 46 arquivos, tsc --noEmit, pytest 23/23, vitest 8/8)
- `CIVBR_RAW=/tmp/nonexistent uv run pytest -q`: exit `0` (`22 passed, 1 skipped`)
- `make data-sp` (rodada 1 e rodada 2): exit `0` (`Fontes SP sincronizadas (sem download: 11/11)`)
- `sha256sum -c /tmp/pr3_run1.sha256`: exit `0` (**21/21** artefatos Parquets e JSONs idênticos byte-a-byte)
- `make web-build`: exit `0` (`dist/assets/index-iK8VSC3Z.js` = `29.75 kB` raw / `10.50 kB` gzip; orçamento `≤ 150 KB`)
- `make verify`: exit `0`
  - `Verificacao OK: web/dist presente (29745 B JS, 0 unpkg), 1091 hexes H3 res 5, 8 lentes, pop=44,411,238, area=248200.39 km2.`

## 2. Blast Radius — Preservação PR 1 e PR 2
- `git diff --stat main -- data/processed/sp_municipio_hex.parquet web/public/data/sp_hex.json data/processed/sp/dasymetric_weights.parquet data/processed/sp/mun_base.parquet data/processed/sp/hex_base.parquet`: **vazio (zero diff)**.
- `pipeline/reconcile/dasymetric.py`: inalterado.

## 3. Orçamentos de payload web (`web/public/data/sp/`)
| Arquivo | Tamanho real | Orçamento | Status |
|---|---:|---:|---|
| `grid.json` | 65.715 B | ≤ 220.000 B | OK |
| `pontos.json` | 60.345 B | ≤ 200.000 B | OK |
| `cities.json` | 81.562 B | ≤ 200.000 B | OK |
| `lentes/index.json` | 3.014 B | — | OK |
| `lentes/ouro.json` | 10.489 B | ≤ 50.000 B | OK |
| `lentes/producao.json` | 9.561 B | ≤ 50.000 B | OK |
| `lentes/comida.json` | 9.294 B | ≤ 50.000 B | OK |
| `lentes/cidadaos.json` | 8.766 B | ≤ 50.000 B | OK |
| `lentes/distritos.json` | 6.190 B | ≤ 50.000 B | OK |
| `lentes/saude.json` | 5.945 B | ≤ 50.000 B | OK |
| `lentes/ciencia_educacao.json` | 5.848 B | ≤ 50.000 B | OK |
| `lentes/infra.json` | 4.710 B | ≤ 50.000 B | OK |
