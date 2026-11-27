# ADR 0002 — Motor Canvas 2D, Grade Estatística 1 km e Schema Parametrizado por UF

## Problema
Ao projetar o PR 2 e escalar para os 5.570 municípios do Brasil (~34.200 hexes H3 res 5), três gargalos apareceram nos dados reais do PR 1:
1. O bundle web com `@deck.gl/*` já custava `1.062 kB` JS (`303 kB` gzip) para uma camada plana e carregava fallback latente `https://unpkg.com/@loaders.gl`.
2. O formato `sp_hex.json` (`327 KB` formatado) e lentes repetindo strings `h3` de 15 caracteres estouram os limites de `1,5 MB` e `150 KB` no Amazonas (~6.763 hexes).
3. A Grade Estatística 2022 mista (200 m/1 km) exige selecionar manualmente 57 arquivos por quadrante, enquanto o IBGE publica uma grade homogênea de 1 km para o Brasil inteiro em 1 único ZIP.

## Decisões
- **Motor Canvas 2D em TypeScript puro (sem `deck.gl` nem `h3-js` no cliente):** o pipeline pré-projeta os centros e o template hexagonal (erro máximo `0,4 px` em SP). O bundle JS cai para `< 40 kB`, sem WebGL no CI headless e sem nenhuma URL externa. A UI oferece toggle entre **Atlas Estratégico** (alto contraste) e **Modo Civ**.
- **Layout `--uf` + lentes posicionais compactas:** artefatos em `data/processed/<uf>/` e `web/public/data/<uf>/grid.json` + `lentes/<id>.json` (vetor posicional alinhado à ordem canônica de `h3`). SP caiu de `327 KB` para `65,7 KB` no grid e `~9–10 KB` por lente.
- **IBGE Grade 1 km (`BR1KM_20251002.zip`) via `pyogrio` com filtro `bbox` + `TOTAL > 0`:** 1 única URL determinística cobre SP (203.983 células populadas, `0` fallbacks por área) e o Brasil, com ~259 sub-células por hex H3 res 5.
- **SIDRA 5938 ano `2021` fixado para PIB + 4 VABs:** na tabela 5938 do IBGE, 2022–2023 publicam apenas o PIB total (`...` nos VABs setoriais); `2021` garante consistência completa entre PIB e VABs com `ano_ref` explícito no manifesto e na legenda.
- **Checkpointing por etapa (`data/checkpoints/<uf>.json`) e pin Python `>=3.13,<3.14`:** isola divergências entre `raw`, `municipal`, `dasymetric`, `hex_base` e `web_json`, e trava compatibilidade de wheels binários entre local e CI.
