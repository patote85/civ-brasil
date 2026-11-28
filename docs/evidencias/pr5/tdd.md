# Evidência TDD — PR 5 (Almanaque/Fontes, URL State, CSP/Headers e 1ª Produção SP)

## 1. Fase RED (invariantes escritos antes da implementação)
- **Comando:** `uv run pytest tests/test_pr5_invariants.py`
- **Exit code:** `2`
- **Trecho da saída:**

```text
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
collected 0 items / 1 error
tests/test_pr5_invariants.py:6: in <module>
    from pipeline.civ.almanac import build_sources_catalog
E   ModuleNotFoundError: No module named 'pipeline.civ.almanac'
```

## 2. Fase GREEN
- `make check`: exit `0` (`ruff`, `lint-imports` 2/2, `eslint`, `mypy --strict` 55 arquivos, `tsc --noEmit`, `pytest` 32/32, `vitest` 13/13)
- `make web-build`: exit `0` (`44,77 KB` JS raw / `14,91 KB` gzip)
- `make verify`: exit `0` (`sources.json` sincronizado, `404.html` presente, payload inicial `~135 KB ≤ 600 KB`, total SP `~527 KB ≤ 1,5 MB`)
- `make e2e`: exit `0` (`4 passed (13.5s)` em `1280×800` e `375×812` — incluindo Almanaque/Fontes e restauração de URL shareable)

