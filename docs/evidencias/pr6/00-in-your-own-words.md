# PR 6 — Base Brasil (`--uf BR`: 5.570 municípios, H3 res 3 + res 5, Arranjos, Censo e PIB BR)

## Entendimento do problema

No PR 5 colocamos o piloto de São Paulo (645 municípios, 1.091 hexes H3 res 5, 11 lentes, CSP estrita) em produção na Vercel. O PR 6 é o gate estrutural da expansão nacional:

1. **Generalizar a ingestão e reconciliação base para as 27 UFs (`--uf BR`)**:
   - Baixar e cachear em `data/raw/` (com manifesto SHA-256 e zero re-download na 2ª execução) as malhas municipais IBGE (`qualidade=intermediaria`), listas de municípios, Censo 2022 (SIDRA 4714) e PIB Municipal 2021 (SIDRA 5938) para todas as 27 UFs (`5.570` municípios, incluindo Fernando de Noronha).
   - Reaproveitar `data/raw/ibge_grade/BR1KM_20251002.zip` em streaming por UF (recorte por bounding box via `pyogrio`), mantendo pico de RAM baixo e determinismo byte-a-byte.
   - Ingerir os Arranjos Populacionais oficiais do IBGE e gerar `data/processed/br_arranjos.parquet`.
2. **Grade nacional em dois níveis (LOD H3 res 3 → H3 res 5 sob demanda)**:
   - Agregar as 27 UFs em `web/public/data/br/br_res3.json` (~618 hexes H3 res 3, cobrindo fronteiras interestaduais sem dupla contagem e mantendo carga inicial Brasil `<= 500 KB` raw).
   - Exportar para cada UF `web/public/data/br/<uf>_grid.json` (H3 res 5 compacto, maior UF `AM <= 1,0 MB` raw) e as 4 lentes base (`ouro`, `populacao`, `producao`, `densidade`, cada uma `<= 80 KB` raw em AM).
   - Garantir que o recorte de SP permaneça idêntico ao piloto (`<= 1e-9`) e que `web/public/data/sp/*` não sofra regressão.
3. **Invariantes nacionais obrigatórias**:
   - Exatamente `5.570` municípios; área total `8.510.417,771 km² ±0,5%`; hexes H3 res 5 únicos em `[33.000, 36.500]`; população Brasil `203.080.756 ±0,1%` e cada UF `±0,1%`.
4. **UI Brasil + LOD sob demanda**:
   - Adicionar alternância Brasil (H3 res 3) ↔ UF (H3 res 5 sob demanda, incluindo SP piloto completo e qualquer outra UF como AM e PE), com suporte em URL (`?uf=BR`, `?uf=AM`, `?uf=PE`, `?uf=SP`) e teste E2E Playwright abrindo vista Brasil e clicando em SP, AM e PE sem erros.
