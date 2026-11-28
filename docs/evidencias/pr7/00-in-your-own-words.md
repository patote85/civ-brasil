# PR 7 — Fontes Nacionais (`--uf BR`: Social/Eleitoral, Segurança Pública BR e Economia/Infra BR)

## Entendimento do problema

Com a base territorial e demográfica das 27 UFs consolidada no PR 6 (`5.570` municípios, `32.173` hexes H3 res 5, `739` hexes H3 res 3), o PR 7 traz todas as fontes temáticas nacionais para os `5.570` municípios, preparando os parquets e checkpoints que alimentarão as 22 lentes e o Explorer BR no PR 8:

1. **Novas fontes nacionais oficiais**:
   - **Segurança Pública BR (`pipeline/sources/ipea_atlas_violencia/`)**: taxa municipal de homicídios por 100 mil habitantes do **Atlas da Violência (IPEA/FBSP)** via IPEA Data (`AVIOL12_THOMIC`), com flag `baixa_populacao (<20k)` e **blindagem absoluta**: a métrica nacional de `descontentamento` nunca mistura `ssp_sp` nem `sinesp_vde`.
   - **Social — Bolsa Família (`pipeline/sources/mds_bolsa/`)**: número de famílias beneficiárias (`FAM_PBF`) e valor total (`VAL_PBF`) por município via IPEA Data/MDS, com conferência de consistência por UF e cobertura registrada.
   - **Saneamento Básico (`pipeline/sources/ibge_saneamento/`)**: percentual de domicílios com esgotamento sanitário adequado (rede geral/pluvial ou fossa ligada à rede) do **Censo 2022 (IBGE SIDRA 6805, `c11558/46290`)** para todos os 5.570 municípios.
2. **Extensão nacional (`--uf BR`) das 9 fontes já em cache local**:
   - `RAIS 2025` (vínculos e CNAE 2 dígitos), `CNES 2025` (leitos e estabelecimentos), `INEP Escolar 2024`, `INEP Superior 2025`, `INEP IDEB 2025`, `ANEEL/EPE Usinas`, `InfraSA/ANTAQ Portos`, `TSE 2024` (eleitorado e comparecimento para 5.570 municípios) e `IPEA/PNUD IDHM & Gini 2010` (com os 5 municípios emancipados pós-2010 explicitamente nulos).
3. **Consolidação determinística e invariantes**:
   - Gerar `data/processed/br_municipios_indicators.parquet` (5.570 linhas) e `data/checkpoints/br_sources.json` com cobertura `N/5.570`, conservação por UF/Brasil (`±0,1%`) e 0 downloads na 2ª execução.
   - Zero regressão na UI atual e no piloto SP (`make check`, `make verify`, `make e2e` verdes).
