# civ-brasil

O Brasil em linguagem de Civilization, com dados públicos reais (IBGE, INEP, DATASUS, TSE, IPEA e outros) reconciliados numa grade hexagonal H3.

Inspirado no [USA Civ](https://karpathy.ai/usaciv/) de Andrej Karpathy. Piloto: estado de São Paulo.

## Arquitetura

- **Pipeline determinístico (`pipeline/`)**: Python 3.13 (`uv`), `h3`, `shapely`, `pyproj` e `pyarrow`. Sem banco de dados e sem leitura de dados por modelos de linguagem.
- **Grade espacial**: células H3 resolução 5 com interseções municipais calculadas em projeção de área igual (Albers Equal Area para o Brasil).
- **Site estático (`web/`)**: Vite + TypeScript estrito + deck.gl (`H3HexagonLayer`), consumindo apenas JSON estático versionado, sem mapa base e sem chamadas externas de rede.

## Comandos principais

- `make setup`: instala dependências Python e web.
- `make check`: executa `ruff`, `mypy --strict`, `lint-imports`, `pytest` e lint/typecheck/test do `web/`.
- `make data-sp`: verifica ou baixa os brutos do IBGE, gera `data/processed/sp_municipio_hex.parquet`, `web/public/data/sp_hex.json` e atualiza `data/manifest.json`.
- `make web-build`: compila o site estático em `web/dist/`.
- `make verify`: verifica o build e os invariantes do JSON publicado.

## Atribuição das fontes

- **IBGE — Malhas Territoriais (API v3)**: malha municipal do estado de São Paulo (`https://servicodados.ibge.gov.br/api/v3/malhas/estados/35?intrarregiao=municipio&formato=application/vnd.geo+json&qualidade=intermediaria`).
- **IBGE — Localidades (API v1)**: relação oficial de municípios de São Paulo (`https://servicodados.ibge.gov.br/api/v1/localidades/estados/35/municipios`).
