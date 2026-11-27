# Evidência TDD — PR 2 (Núcleo `--uf`, Reconciliação Dasimétrica e Motor Canvas 2D)

## 1. Fase RED (testes de invariantes escritos antes do código)
- **Comando:** `uv run pytest tests/test_reconcile_invariants.py`
- **Exit code:** `2`
- **Trecho da saída:**

```text
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
collected 0 items / 1 error
tests/test_reconcile_invariants.py:10: in <module>
    from pipeline.civ.export import export_uf_web_bundle
E   ModuleNotFoundError: No module named 'pipeline.civ'
```

## 2. Fase GREEN (após implementação do pipeline e frontend Canvas 2D)
- **Comando:** `uv run pytest tests/test_reconcile_invariants.py`
- **Exit code:** `0` (`4 passed in 0.52s`)
- **Suíte completa (`make check`):** `ruff` OK, `lint-imports` 2/2 KEPT, `eslint` OK, `mypy --strict` (29 arquivos) OK, `tsc --noEmit` OK, `pytest` (`18 passed` com brutos locais / `17 passed, 1 skipped` sem `CIVBR_RAW`), `vitest` (`5 passed`).

## 3. Rodada Bugbot (3 apontamentos: `verify.py`, busca de município e recorte do minimapa)
- **RED (`b652f6e`):**
  - `uv run pytest tests/test_verify_and_io.py` → exit `1` (`FAILED test_verify_artifacts_checks_pr2_web_even_when_parquets_missing`).
  - `npm --prefix web run test` → exit `1` (`3 failed`: busca multi-hex caía no 1º hex `3` em vez do hub `4`; `computeMinimapViewportRect` inexistente).
- **GREEN:** `make check` exit `0` (`pytest`: `19 passed` / `18 passed, 1 skipped` sem `CIVBR_RAW`; `vitest`: `7 passed`), `make web-build` exit `0` (`19.62 kB` JS / `7.48 kB` gzip), `make verify` exit `0`.

