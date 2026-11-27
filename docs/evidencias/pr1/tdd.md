# Evidência TDD — Invariantes da grade H3 de São Paulo (PR 1)

## 1. Fase RED (testes escritos antes da implementação)

- **Comando**: `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_grid_invariants.py`
- **Exit code**: `1`
- **Trecho da saída**:

```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: /workspace/civ-brasil
configfile: pyproject.toml
collecting ... collected 2 items

tests/test_grid_invariants.py FF                                         [100%]

=================================== FAILURES ===================================
_______ test_fixture_invariants_coverage_fractions_area_and_determinism ________
...
pipeline/sources/ibge_malhas/loader.py:65: NotImplementedError
___________________________ test_sp_full_invariants ____________________________
...
pipeline/sources/ibge_malhas/loader.py:65: NotImplementedError
=========================== short test summary info ============================
FAILED tests/test_grid_invariants.py::test_fixture_invariants_coverage_fractions_area_and_determinism
FAILED tests/test_grid_invariants.py::test_sp_full_invariants - NotImplementedError
============================== 2 failed in 0.34s ===============================
```

## 2. Fase GREEN (após implementação da fonte IBGE e grade H3 res 5)

- **Comando**: `timeout 120 uv run --directory /workspace/civ-brasil pytest tests/test_grid_invariants.py`
- **Exit code**: `0`
- **Trecho da saída**:

```text
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: /workspace/civ-brasil
configfile: pyproject.toml
collecting ... collected 2 items

tests/test_grid_invariants.py ..                                         [100%]

============================== 2 passed in 1.26s ===============================
```

Os dois testes validam pela interface pública (`load_municipios_from_files`, `build_municipio_hex_table`, `compute_equal_area_km2`, `build_hex_summaries`):
1. Cobertura total dos 645 municípios de SP (e dos 4 municípios na fixture versionada sem rede);
2. Todo município possui ao menos 1 hexágono H3 resolução 5;
3. Soma de `frac` por município igual a `1.0` com tolerância `1e-6`;
4. Soma das áreas das interseções igual à área total do estado na projeção de área igual (`+proj=aea +lat_0=-32 +lon_0=-60 +lat_1=-5 +lat_2=-42 +ellps=GRS80 +units=m`), dentro de ±0,5% de 248.219 km²;
5. Contagem total de hexágonos entre 900 e 1.100;
6. Determinismo completo (resultados idênticos em duas execuções consecutivas).
