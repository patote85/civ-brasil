# Evidência TDD — PR 4 (Lentes Sensíveis SP, Explorer e E2E)

## 1. Fase RED (invariantes escritos antes da implementação)
- **Comando:** `uv run pytest tests/test_pr4_invariants.py`
- **Exit code:** `2`
- **Trecho da saída:**

```text
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
collected 0 items / 1 error
tests/test_pr4_invariants.py:13: in <module>
    from pipeline.sources.ipea_idhm import load_ipea_idhm_from_files
E   ModuleNotFoundError: No module named 'pipeline.sources.ipea_idhm'
```

## 2. Fase GREEN
- **Comandos:**
  - `make check`: exit `0` (`ruff`, `lint-imports` 2/2, `eslint`, `mypy --strict` 53 arquivos, `tsc --noEmit`, `pytest` 29/29, `vitest` 11/11)
  - `make web-build`: exit `0` (`38,96 KB` JS raw / `13,27 KB` gzip)
  - `make verify`: exit `0` (`1.091 hexes`, `11 lentes`, `44.411.238 hab`, `0 unpkg`)
  - `make e2e`: exit `0` (`2 passed` — `desktop-1280x800` e `mobile-375x812`, `0` erros de console, `0` requisições externas)

