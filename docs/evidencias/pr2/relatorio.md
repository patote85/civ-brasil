# Relatório — PR 2 (Núcleo `--uf`, Censo/PIB, Grade 1 km e Motor Canvas 2D)

## 1. In your own words
Construído o núcleo parametrizado por `--uf` com ingestão determinística de Censo 2022, PIB/VABs 2021 e Grade Estatística 1 km do IBGE, reconciliação dasimétrica exata (`município → hex H3 res 5`), checkpoints por etapa e novo frontend estático em **Canvas 2D** (sem `deck.gl`, sem WebGL, sem `unpkg.com`) com 4 lentes reais (`Ouro`, `Produção`, `Comida`, `Cidadãos`), Yields bar, busca `/`, legenda interativa com fonte/ano, minimapa e toggle `Atlas` / `Civ`.

## 2. Princípios do pstack aplicados
- `principle-model-the-domain`: tipos de domínio (`CdMun`, `H3Index`, `UfCode`), `civ_rules.yaml` validado e vetores posicionais eliminando repetição de strings `h3`.
- `principle-boundary-discipline`: validação de códigos IBGE, sentinels SIDRA (`-`, `...`, `X`) e JSONs na fronteira; `import-linter` garantindo que `pipeline.sources.*` não importa `grid`, `reconcile` nem `civ`.
- `principle-make-operations-idempotent`: fetch compartilhado por SHA-256 + escrita atômica com `fsync` + 2ª execução `sem download: 4/4` byte-idêntica.
- `principle-explain-the-number` e `principle-prove-it-works`: bundle JS medido (`1.062 kB → 19 kB`), payloads posicionais medidos (`327 KB → 65,7 KB` grid + `~9–10 KB`/lente), conservação verificada sobre os 645 municípios reais de SP.
- `principle-sequence-verifiable-units`: testes TDD de invariantes antes da implementação.

## 3. Gates executados
| Comando | Exit code | Resultado |
| --- | --- | --- |
| `make setup` | `0` | Python 3.13.18 (`pyogrio 0.13.0`, `pyyaml 6.0.4`), npm ci 211 pacotes |
| `make data-sp` (1ª) | `0` | 645 mun, 1.091 hexes, pop `44.411.238`, PIB `R$ 2.719,75 bi`, `fallback_area=0` |
| `make data-sp` (2ª) | `0` | `sem download: 4/4`, SHA-256 idêntico em todos os artefatos |
| `make check` | `0` | `ruff`, `lint-imports` 2/2, `eslint`, `mypy --strict` (29 arqs), `tsc`, 18 pytest, 5 vitest |
| `CIVBR_RAW=/tmp/nonexistent uv run pytest` | `0` | 17 passed, 1 skipped (simulação de CI sem brutos locais) |
| `make web-build` | `0` | Vite build em `316 ms` (`19,04 kB` JS / `7,22 kB` gzip) |
| `make verify` | `0` | `19044 B JS`, `0 unpkg`, `1091 hexes`, `pop=44,411,238`, conservação exata |

## 4. Riscos e o que ficou fora
- Verificação visual em navegador real via Playwright entra no PR 4 (conforme plano recalibrado); a renderização Canvas 2D será inspecionada no preview da Vercel deste PR antes do merge.
- `SIDRA 5938` usa ano `2021` (último ano completo com PIB + 4 VABs na tabela; 2022–2023 têm `...` nos VABs setoriais), documentado no ADR 0002 e na legenda.

## 5. /teach
1. Pré-projetar os centros e o template hexagonal no pipeline reduziu o bundle JS de `1.062 kB` (`deck.gl`) para `19 kB` (`Canvas 2D`) com erro geométrico máximo de `0,4 px` em SP e zero dependências externas.
2. Lentes posicionais alinhadas à ordem canônica de `grid.json` derrubaram cada lente de SP para `9–10 KB`, garantindo folga para estados gigantes como o Amazonas.
3. Ler `BR1KM_20251002.zip` diretamente via `/vsizip/...` com `pyogrio` (`bbox` + `TOTAL > 0`) reconciliou 203.983 células populadas em ~25 s com `0` fallbacks em SP.

ESTADO FINAL | ok
