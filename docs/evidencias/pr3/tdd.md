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
*(a preencher após implementação e validação completa)*
