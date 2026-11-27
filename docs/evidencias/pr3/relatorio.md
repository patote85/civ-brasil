# Relatório Empírico — PR 3 (Economia, Serviços e City View SP)

## 1. Totais Estaduais Reconciliados (SP · 645 municípios · 1.091 hexes H3 res 5)
- **RAIS 2025 (MTE):** `16.158.390` vínculos formais em `3.212.529` estabelecimentos (`87` divisões CNAE 2 dígitos; `0` CNAE ausente; `0` linhas puladas).
- **INEP Censo Escolar 2024:** `30.746` escolas, `9.998.443` matrículas na educação básica.
- **INEP Censo Educação Superior 2025:** `1.312.418` matrículas no ensino superior (`ces2025_microdados_tabela_curso.csv`).
- **INEP IDEB 2025:** séries municipais de Anos Iniciais, Anos Finais e Ensino Médio integradas ao perfil de cada cidade.
- **DataSUS CNES 2025 (OpenDataSUS S3 CSV, sem `.dbc`/AGPL):** `155.367` estabelecimentos, `115.512` leitos existentes, `1.713` hospitais aceitos no grid H3 de SP.
- **EPE/ANEEL (usinas em operação):** `261` usinas em SP totalizando `22.628,46 MW` (`22,63 GW`).
- **InfraSA/ONTL (instalações portuárias):** `10` instalações em SP (Santos, São Sebastião, DP World Santos, TIPLAM, Cutrale, Dow, TMPC, Almirante Barroso, Base Logística de Dutos, LDC Pederneiras).

## 2. Auditoria de Pontos Rejeitados (`data/processed/sp/rejected_points.json`)
Total de `174` pontos rejeitados com registro explícito de fonte e motivo:
- `cnes` · `coordenada_invalida_ou_ausente`: `170`
- `cnes` · `fora_da_grade_uf`: `2`
- `aneel_siga` · `fora_da_grade_uf`: `2`
- `antaq`: `0` rejeitados em SP

## 3. Exemplos Reais no City View SP
- **São José dos Campos:** `228.391` vínculos · Distritos: *Aeroespacial e Transporte* (`CNAE 30`, `30,24x QL`), *Mídia e Editorial* (`3,04x QL`), *Engenharia e Arquitetura* (`2,36x QL`) · IDEB AI `6,9` / AF `5,7` / EM `4,6` · `20` IES (`22.617` matrículas) · `1.932` leitos.
- **Campinas:** `480.388` vínculos · Distritos: *Campus e Pesquisa (P&D)* (`CNAE 72`, `8,69x QL`), *Aviação* (`CNAE 51`, `5,93x QL`), *Energia e Eletricidade* (`4,40x QL`) · `19` IES (`57.324` matrículas) · `3.739` leitos.
- **São Bernardo do Campo:** `299.252` vínculos · Distritos: *Polo Automotivo* (`CNAE 29`, `5,76x QL`) · `889,0 MW` (UHE Henry Borden) · `2.269` leitos.
- **Santos:** `214.142` vínculos · Distritos: *Apoio à Extração e Pré-Sal* (`CNAE 09`, `42,89x QL`), *Transporte Aquaviário* (`CNAE 50`, `26,85x QL`), *Logística Portuária e Armazenagem* (`CNAE 52`, `8,84x QL`) · `2` instalações portuárias · `2.065` leitos.

## 4. Notas de Endpoints Oficiais
- **INEP (`download.inep.gov.br`):** o servidor omite o certificado intermediário `RNP ICPEdu GR46 OV TLS CA 2025`; o loader baixa e armazena em cache o certificado oficial GlobalSign em `data/raw/_certs/` mantendo verificação TLS integral (`build_inep_ssl_context`).
- **ANEEL SIGA:** os hosts `dadosabertos.aneel.gov.br` e `sigel.aneel.gov.br` deram timeout no ambiente; o loader usa por padrão o endpoint oficial do **EPE WebMap ArcGIS REST** (camadas `14–21`, usinas em operação oriundas do ANEEL SIGA) mantendo compatibilidade com `siga.csv` local.
- **ANTAQ:** `web3.antaq.gov.br` (DNS) e `ea.antaq.gov.br` (HTTP 403) indisponíveis; o loader usa o shapefile oficial do **InfraSA / ONTL Geoportal** (`Instalacoes_portuarias-1.zip`) mantendo suporte a `antaq_carga.csv` local.
