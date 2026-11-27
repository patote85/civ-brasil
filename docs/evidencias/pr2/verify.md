# Verify-This — PR 2

## Afirmação 1 — Conservação exata de população, PIB e VABs na reconciliação dasimétrica (Grade 1 km)
- **Condição:** Soma nos 1.091 hexes H3 res 5 igual à soma dos 645 municípios (`rel_tol = 1e-6`), população total = `44.411.238 ±0,1%`, `sum(w) = 1 ±1e-9` por município.
- **Baseline (`8f0d478`):** `data/processed/sp/hex_base.parquet` inexistente (`0` fontes socioeconômicas).
- **Treatment:** `make data-sp` + `make verify` → `645` municípios, `1.091` hexes, `203.983` células populadas da Grade 1 km, `0` fallbacks por área, `pop_total = 44.411.238` (municipal e hex idênticos), `pib_total = R$ 2.719.751.233 mil` (municipal e hex idênticos), `vab_ind = 518.292.544 mil`, `vab_agro = 46.193.516 mil`.

## Afirmação 2 — Idempotência e determinismo byte-a-byte + artefatos do PR 1 preservados
- **Condição:** 2ª execução de `make data-sp` sem download (`4/4`), SHA-256 idêntico dos parquets e JSONs, e `sp_municipio_hex.parquet` / `sp_hex.json` inalterados.
- **Baseline (`8f0d478`):** artefatos PR 1 presentes; sem execução PR 2.
- **Treatment:** 2ª execução imprimiu `Fontes SP sincronizadas (sem download: 4/4).`; `sha256sum -c` retornou `OK` em todos os 5 artefatos verificados; `git diff --stat -- data/processed/sp_municipio_hex.parquet web/public/data/sp_hex.json` vazio.

## Afirmação 3 — Orçamento de payload web e eliminação de `unpkg.com`
- **Condição:** Bundle JS `≤ 150 KB`, `grid.json ≤ 220 KB`, cada lente posicional `≤ 40 KB`, zero ocorrências de `unpkg.com` em `web/dist/`.
- **Baseline (`8f0d478`):** JS = `1.062.470 B` (`303,14 kB` gzip) com 2 referências a `https://unpkg.com/@loaders.gl`; `sp_hex.json` = `326.859 B`.
- **Treatment:** `make web-build` + `make verify` → JS = `19.615 B` (`7,48 kB` gzip, redução de **54,2×**), `0` ocorrências de `unpkg.com`, `grid.json` = `65.715 B`, lentes posicionais de `8.766 B` a `10.489 B` (`105 KB` totais sem compressão).

VERIFIED
