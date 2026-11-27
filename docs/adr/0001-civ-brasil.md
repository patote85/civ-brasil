# ADR 0001 — Arquitetura inicial do civ-brasil

## Problema

Precisamos transformar dados públicos brasileiros (inicialmente a malha municipal do estado de São Paulo) em uma visualização hexagonal inspirada no USA Civ, garantindo reprodutibilidade determinística, transparência matemática nas reconciliações espaciais e custo zero de hospedagem e manutenção.

## Forma escolhida

- **Grade H3 resolução 5**: cobre o estado de São Paulo com ~1.000 hexágonos (incluindo bordas que tocam o estado), equilibrando legibilidade visual e granularidade territorial.
- **Projeção de área igual**: todas as áreas e frações de interseção município→hex são calculadas em Albers Equal Area (`+proj=aea +lat_0=-32 +lon_0=-60 +lat_1=-5 +lat_2=-42 +ellps=GRS80 +units=m`), preservando a soma das áreas.
- **Pipeline determinístico sem banco de dados**: scripts Python 3.13 produzem artefatos estáticos (`data/processed/sp_municipio_hex.parquet`, `web/public/data/sp_hex.json` e `data/manifest.json` com SHA-256). Nenhum modelo de linguagem lê ou transforma os dados.
- **Fronteira modular**: `pipeline.sources.*` não importa `pipeline.grid` nem `pipeline.reconcile`, e nada em `pipeline` importa `web`, garantido por `import-linter`.
- **Site estático na Vercel Hobby**: frontend Vite + TypeScript estrito + deck.gl (`H3HexagonLayer`) sem mapa base e sem requisições externas além do JSON estático versionado.

## Trade-offs

- **Versionar o JSON estático** evita executar Python no build da Vercel, mas exige manter `web/public/data/sp_hex.json` sincronizado via `make data-sp` e verificado no CI por `make verify`.
- **Sem mapa base externo** elimina dependência de chaves/APIs de tiles e serviços pagos, ao custo de menor contexto cartográfico imediato (compensado por tooltips e futuras camadas vetoriais próprias).
- **Resolução H3 fixa (5)** simplifica reconciliações e peso do payload, mas municípios muito pequenos podem compartilhar o mesmo hexágono.

## Alternativas consideradas

- **PostGIS / banco de dados em nuvem**: descartado por adicionar custo operacional, estado mutável e complexidade desnecessária para dados públicos publicados periodicamente.
- **Tiles vetoriais com Mapbox/MapTiler**: descartado para manter zero dependência de serviços pagos ou contas de terceiros no navegador.
- **Resolução H3 6 ou 7**: descartada no piloto por multiplicar o número de polígonos no cliente sem ganho proporcional para a escala estadual.
