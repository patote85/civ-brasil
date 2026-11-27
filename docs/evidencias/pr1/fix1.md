# Evidências PR 1 — fix1 (achados da auto-revisão 2)

- **Branch**: `pr1-grade-sp`
- **SHA de partida**: `f5e6273f3cd45956ecc1fb9a733ee2e5e30365dc`
- **Origem**: achados A1, A2 e A4 do relatório de revisão 2 (`pr1-rev2-relatorio.md`).

## 1. Correções aplicadas

- **A1 (Alta) — `.gitignore`**: restaurados os padrões `.env`, `.env.*`, `.vercel/`, `agy-*.log`, `*-stream.jsonl` e `node_modules/`, preservadas as linhas existentes (`.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `web/node_modules/`, `web/dist/`, `.DS_Store`) e adicionado `.import_linter_cache/`.
- **A2 (Média) — `.github/workflows/ci.yml`**: adicionado `permissions: contents: read` no nível superior do workflow e `timeout-minutes: 15` no job `ci`.
- **A4 (Baixa) — `Makefile`**: atualizado o alvo `setup` para executar `uv sync --dev --locked` (alvo usado localmente e pelo passo `Setup` no `.github/workflows/ci.yml`).
- **Check determinístico — `tests/test_repo_hygiene.py`**: testes pela interface pública (leitura direta dos arquivos do repositório) garantindo todos os padrões obrigatórios do `.gitignore`, `permissions` com `contents: read` e `timeout-minutes` no `ci.yml`, além de `--locked` em todo `uv sync` no `Makefile`.

## 2. Evidência TDD (`tests/test_repo_hygiene.py`)

### Fase RED (antes das correções)

- **Comando**: `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_repo_hygiene.py`
- **Exit code**: `1`
- **Trecho da saída**:

```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: /workspace/civ-brasil
configfile: pyproject.toml
collecting ... collected 3 items

tests/test_repo_hygiene.py FFF                                           [100%]

=================================== FAILURES ===================================
__________________ test_gitignore_contains_required_patterns ___________________
E       AssertionError: Padrões obrigatórios ausentes no .gitignore: ['*-stream.jsonl', '.env', '.env.*', '.import_linter_cache/', '.vercel/', 'agy-*.log', 'node_modules/']
____________ test_ci_workflow_enforces_least_privilege_and_timeout _____________
E       AssertionError: ci.yml deve definir bloco top-level 'permissions'
______________________ test_makefile_uses_locked_uv_sync _______________________
E       AssertionError: Comandos 'uv sync' sem '--locked' no Makefile: ['uv sync --dev']
=========================== short test summary info ============================
FAILED tests/test_repo_hygiene.py::test_gitignore_contains_required_patterns
FAILED tests/test_repo_hygiene.py::test_ci_workflow_enforces_least_privilege_and_timeout
FAILED tests/test_repo_hygiene.py::test_makefile_uses_locked_uv_sync
============================== 3 failed in 0.03s ===============================
```

### Fase GREEN (após as correções)

- **Comando**: `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_repo_hygiene.py`
- **Exit code**: `0`
- **Trecho da saída**:

```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: /workspace/civ-brasil
configfile: pyproject.toml
collecting ... collected 3 items

tests/test_repo_hygiene.py ...                                           [100%]

============================== 3 passed in 0.02s ===============================
```

## 3. Gates validados após a correção

| Comando | Exit code | Resultado |
| --- | --- | --- |
| `timeout 600 make -C /workspace/civ-brasil check` | `0` | `ruff` OK; `lint-imports` 2/2 contratos KEPT; `eslint` OK; `mypy --strict` (14 arquivos) OK; `tsc --noEmit` OK; `pytest` 12 passed; `vitest` 5 passed. |
| `timeout 300 make -C /workspace/civ-brasil web-build` | `0` | Vite build OK em `4.76s` (`web/dist/index.html`, CSS e bundles JS gerados). |
| `timeout 120 make -C /workspace/civ-brasil verify` | `0` | `Verificacao OK: web/dist presente, 1091 hexes H3 res 5, area=248200.39 km2.` |

## 4. Risco residual (registrado sem alteração neste fix)

- **A2 (detalhe residual — pinagem de actions por tag)**: as GitHub Actions no `.github/workflows/ci.yml` (`actions/checkout@v4`, `astral-sh/setup-uv@v5`, `actions/setup-node@v4`) seguem fixadas por tag major em vez de commit SHA.
- **A3 (Baixa — fallback de CDN externo e ausência de CSP)**: o bundle gerado em `web/dist/assets/index-*.js` carrega o fallback `https://unpkg.com/@loaders.gl` vindo de `@loaders.gl` (via `deck.gl`), latente enquanto apenas `H3HexagonLayer` com array em memória é utilizada; falta também política de CSP e `headers` no `vercel.json`.
- **A5 (Baixa — proveniência do `manifest.json`)**: `pipeline/sources/ibge_malhas/loader.py` grava `datetime.now()` em `fetched_at` quando o bruto já existe localmente sem entrada prévia no manifesto e confia no arquivo local sem `SHA256SUMS` (trust on first use).
- **A6 (Baixa — `DEFAULT_RAW_ROOT` e caminhos relativos)**: `DEFAULT_RAW_ROOT` aponta para `/workspace/civbr-dados/raw` e caminhos relativos (`data/manifest.json`, `pipeline/grid/sp.py`) assumem execução na raiz do repositório; fora do box sem `CIVBR_RAW`, `make data-sp` falha ao criar `/workspace/...`.
- **A7 (Baixa — escrita atômica do Parquet e escopo do catálogo de QA)**: `pipeline/grid/h3_grid.py` substitui o Parquet via `os.replace` sem `fsync` prévio; `qa/catalog/README.md` menciona re-obtenção segura enquanto o loader apenas rejeita com `IntegrityError`; Parquet, JSON e manifesto são gravados em passos independentes.
- **A8 (Info — deriva entre JSON versionado e pipeline no CI)**: o CI não executa `make data-sp` e o teste `test_sp_full_invariants` é pulado sem brutos locais; `make verify` confere consistência interna (1.091 hexes, a 9 do teto de 1.100), mas não revalida contra os brutos do IBGE.
- **A9 (Info — versão de Node não fixada no Vercel)**: `vercel.json` e `web/package.json` não definem `engines` nem `.nvmrc`, deixando o build do Vercel usar a versão padrão do projeto enquanto o CI fixa Node 24.
