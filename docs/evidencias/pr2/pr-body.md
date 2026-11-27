## In your own words
Este PR implementa o núcleo parametrizado por `--uf` do **civ-brasil** (piloto SP) com reconciliação dasimétrica via Grade Estatística 1 km do IBGE (Censo 2022 + PIB/VABs 2021), checkpoints por etapa e a migração do frontend para um motor **Canvas 2D** leve em TypeScript puro (sem `deck.gl` e sem `unpkg.com`), entregando as 4 primeiras lentes reais (`Ouro`, `Produção`, `Comida`, `Cidadãos`), Yields bar, busca `/` nos 645 municípios, filtro interativo na legenda, minimapa e toggle entre modo **Atlas** e **Civ**.

## Princípios aplicados
- `principle-model-the-domain`: tipos de domínio (`CdMun`, `H3Index`, `UfCode`), `civ_rules.yaml` validado e vetores posicionais de lente sem repetição de strings `h3`.
- `principle-boundary-discipline`: validação estrita de SIDRA (`-`, `...`, `X`) e JSONs nas fronteiras; `import-linter` garantindo isolamento de `pipeline.sources.*`.
- `principle-make-operations-idempotent`: fetch idempotente por SHA-256 (`sem download: 4/4` na 2ª execução) e escrita atômica com `fsync`.
- `principle-explain-the-number` e `principle-prove-it-works`: orçamentos reais medidos e travados em `pipeline/verify.py` (`1.062 kB → 19 kB` JS; `327 KB → 65,7 KB` grid + `9–10 KB`/lente).
- `principle-sequence-verifiable-units`: testes TDD de invariantes commitados antes da implementação.

## Evidências
| gate | comando | exit |
| --- | --- | --- |
| setup | `make setup` (Python 3.13.18 + npm ci 211 pkgs) | `0` |
| dados (1ª) | `make data-sp` (645 mun, 1.091 hexes, `fallback_area=0`) | `0` |
| dados (2ª) | `make data-sp` (`sem download: 4/4`, SHA-256 idêntico) | `0` |
| check | `make check` (`ruff`, `lint-imports`, `eslint`, `mypy --strict`, `tsc`, 18 pytest, 5 vitest) | `0` |
| web-build | `make web-build` (`19,04 kB` JS / `7,22 kB` gzip em `316 ms`) | `0` |
| verify | `make verify` (`0 unpkg`, `pop=44,411,238`, conservação exata) | `0` |

verify-this: `VERIFIED` — `pop_total` = `44.411.238` (exato), `pib_total` = `R$ 2.719.751.233 mil` (exato), bundle JS `1.062.470 B → 19.044 B` (−98,2%), `unpkg.com` `2 → 0`, `grid.json` `65.715 B`, lentes `8,8–10,5 KB`.

## Blast radius
- Fato do qual a segurança depende: o PR 2 preserva intactos `data/processed/sp_municipio_hex.parquet` e `web/public/data/sp_hex.json` do PR 1 e não exige Python no build da Vercel (`vercel.json` roda apenas `cd web && npm ci && npm run build`).
- Prova: `git diff --stat -- data/processed/sp_municipio_hex.parquet web/public/data/sp_hex.json` vazio; `CIVBR_RAW=/tmp/nonexistent uv run pytest` (`17 passed, 1 skipped`); `make web-build && make verify` verde.

## Risco e /teach
- **Risco residual:** inspeção visual em navegador headless automatizado (Playwright) entra no PR 4; revisar o preview da Vercel deste PR em desktop e mobile antes do merge.
- **/teach:** pré-projetar a geometria H3 no pipeline e usar lentes posicionais derrubou o JS em 55× (`1.062 kB → 19 kB`) e o payload de lente para `~10 KB`, mantendo conservação matemática exata com a Grade 1 km do IBGE (`0` fallbacks em SP).

## Achados do Bugbot e correções
*(nenhum na abertura)*
