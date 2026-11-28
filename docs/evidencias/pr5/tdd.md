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
*(a preencher após implementação e validação completa)*
