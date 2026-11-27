# Evidência TDD — PR 3 (Economia, Serviços SP e City View SP)

## 1. Fase RED (invariantes escritos antes da implementação)
- **Comando:** `uv run pytest tests/test_pr3_invariants.py`
- **Exit code:** `2`
- **Trecho da saída:**

```text
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
collected 0 items / 1 error
tests/test_pr3_invariants.py:10: in <module>
    from pipeline.civ.districts import compute_location_quotients
E   ModuleNotFoundError: No module named 'pipeline.civ.districts'
```

## 2. Fase GREEN
- **Comando:** `make check`
- **Exit code:** `0`
- **Resultados:**
  - `uv run ruff check pipeline tests`: `All checks passed!`
  - `uv run lint-imports`: `Contracts: 2 kept, 0 broken.`
  - `npm --prefix web run lint`: `0 errors`
  - `uv run mypy --strict pipeline tests`: `Success: no issues found in 46 source files`
  - `npm --prefix web run typecheck`: `0 errors`
  - `uv run pytest`: `23 passed in 3.23s`
  - `CIVBR_RAW=/tmp/nonexistent uv run pytest -q`: `22 passed, 1 skipped in 1.03s`
  - `npm --prefix web run test`: `8 passed (8)`

