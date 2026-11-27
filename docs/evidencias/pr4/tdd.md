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
*(a preencher após implementação e validação completa)*
