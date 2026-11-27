## Resumo — PR #3: Economia, Serviços de SP e City View SP

Expande o `civ-brasil` em São Paulo de 4 para **8 lentes temáticas**, integra 7 novas fontes públicas oficiais (totalizando **11 fontes reais em cache atômico**), adiciona camada vetorial de pontos de infraestrutura (usinas, portos e hospitais) e entrega o painel interativo **City View** por município.

### O que entrou
1. **7 novas fontes oficiais (`pipeline/sources/`):**
   - `rais`: RAIS Estabelecimentos 2025 (`16.158.390` vínculos em `3.212.529` estabelecimentos de SP, agregação por CNAE 2 dígitos).
   - `inep_escolar`: Censo Escolar 2024 (`30.746` escolas, `9.998.443` matrículas).
   - `inep_superior`: Censo da Educação Superior 2025 (`1.312.418` matrículas via `ces2025_microdados_tabela_curso.csv`).
   - `inep_ideb`: IDEB 2025 municipal (AI, AF, EM).
   - `cnes`: OpenDataSUS S3 CSV 2025 (`155.367` estabelecimentos, `115.512` leitos, sem `.dbc`/AGPL).
   - `aneel_siga`: EPE/ANEEL WebMap ArcGIS (`261` usinas em operação em SP, `22.628,46 MW`) com fallback para `siga.csv` local.
   - `antaq`: InfraSA/ONTL shapefile (`10` instalações portuárias em SP) com suporte a `antaq_carga.csv` local.
2. **Reconciliação de pontos + Quociente Locacional (`pipeline/reconcile/points.py`, `pipeline/civ/districts.py`):**
   - Validação de coordenadas e atribuição ao grid H3 res 5 com relatório de rejeitados (`data/processed/sp/rejected_points.json`: `174` pontos rejeitados).
   - Cálculo de **Quociente Locacional (QL)** por divisão CNAE 2 dígitos (`QL ≥ 2,0`) e composição setorial de Cidadãos.
3. **8 lentes em `civ_rules.yaml` + Export Web (`web/public/data/sp/`):**
   - Novas lentes: `distritos` (`6,2 KB`), `ciencia_educacao` (`5,8 KB`), `saude` (`5,9 KB`), `infra` (`4,7 KB`).
   - Novos payloads: `pontos.json` (`60,3 KB ≤ 200 KB`) e `cities.json` (`81,6 KB`, top 80 municípios de SP).
4. **Frontend Canvas 2D + City View (`web/src/`):**
   - Paletas e formatação pt-BR para `QL` e `MW`/`GW`.
   - Camada de pontos (`Pontos: AUTO / ON / OFF`) renderizando usinas, portos e hospitais no Canvas 2D.
   - Drawer **City View** (`web/src/city-view/cityView.ts`) ao clicar em banners de cidade, hexágonos ou resultado da busca (`/`), exibindo yields, Distritos (CNAE 2 dígitos + QL), Cidadãos por setor, Educação/IDEB, Saúde/CNES, Infraestrutura e fontes/anos.
5. **Verificação (`pipeline/verify.py`):**
   - Valida os 5 novos Parquets PR 3, conservação de somas (`1e-6`), zero pontos fora do grid H3 de SP, mínimo de 8 lentes, orçamentos de `pontos.json` e `cities.json`, mantendo intactos todos os artefatos de PR 1 e PR 2.

### Evidências
- [00-in-your-own-words.md](docs/evidencias/pr3/00-in-your-own-words.md)
- [tdd.md](docs/evidencias/pr3/tdd.md)
- [verify.md](docs/evidencias/pr3/verify.md)
- [relatorio.md](docs/evidencias/pr3/relatorio.md)
