# In Your Own Words — PR 3 (Economia, Serviços SP e City View SP)

## Problema que estamos resolvendo
O PR 2 entregou o motor Canvas 2D e as 4 lentes fundacionais de São Paulo (Ouro/PIB, Produção/VAB Indústria, Comida/VAB Agropecuária, Cidadãos/População). Agora precisamos dar ao mapa de SP a segunda camada de riqueza do *USA Civ* no contexto brasileiro: **especialização produtiva real por município (Distritos via Quociente Locacional em CNAE 2 dígitos)**, **ciência e educação (INEP)**, **saúde (CNES estabelecimentos e leitos)**, **infraestrutura georreferenciada (usinas ANEEL/EPE e instalações portuárias InfraSA/ANTAQ)** e um **City View** interativo acessível ao clicar nos banners das cidades ou em qualquer hex/município.

## Fontes reais e decisões técnicas deste PR
1. **RAIS 2025 Estabelecimentos (`rais`):** `ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/2025/RAIS_ESTAB_PUB.7z` (lido via `py7zr`). Agrega vínculos ativos em 31/12 por município, seção CNAE (1 letra) e **divisão CNAE 2 dígitos** (01–99), gerando Quociente Locacional (`QL`) sem risco de divisão por zero e classificando Distritos reais (ex.: Aeroespacial/CNAE 30 em SJC, Automotivo/CNAE 29 no ABC, TI/Finanças em SP, Pesquisa/Campus em Campinas).
2. **INEP Educação (`inep_escolar`, `inep_superior`, `inep_ideb`):** Censo Escolar 2024, Censo da Educação Superior 2025 e IDEB 2025 (Anos Iniciais, Anos Finais, Ensino Médio) de `download.inep.gov.br` (validando TLS com o certificado intermediário oficial RNP ICPEdu/GlobalSign sem desabilitar verificação SSL). Escolas e matrículas reconciliadas via `reconcile_sum`; IDEB via `reconcile_rate` ponderado pela população do hex.
3. **CNES Saúde (`cnes`):** OpenDataSUS S3 em CSV puro (`cnes_estabelecimentos_csv.zip` com lat/lon e `cnes_leitos_cadastrados_2025_csv.zip`), evitando `.dbc` (sem wheel Python 3.13 livre de AGPL). Gera estabelecimentos, leitos existentes e pontos de hospitais.
4. **Usinas (`aneel_siga`):** API GeoJSON oficial da EPE WebMap (`gisepeprd2.epe.gov.br`, base oficial ANEEL SIGA, 8 camadas de usinas em operação: UHE, PCH, CGH, UTE Biomassa/Fóssil, EOL, UFV, UTN) com suporte também a `siga.csv` local. Pontos caem diretamente na célula H3 da coordenada; coordenadas inválidas ou fora da grade de SP vão para relatório explícito de rejeitados (`data/processed/sp/rejected_points.json`), nunca somem em silêncio.
5. **Portos e Terminais (`antaq`):** Shapefile oficial InfraSA/ONTL (`Instalacoes_portuarias-1.zip`, 248 instalações nacionais, 10 em SP) com suporte opcional a arquivos locais ANTAQ (`Atracacao.txt`/`Carga.txt` ou `antaq_carga.csv`) para tonelagem movimentada quando disponíveis.

## Entregáveis e invariantes obrigatórios
- **Pipeline determinístico (`make data-sp`):** novos parquets em `data/processed/sp/` (`mun_trabalho.parquet`, `mun_distritos.parquet`, `mun_servicos.parquet`, `hex_economia.parquet`, `pontos_infra.parquet`), preservando byte-a-byte os artefatos de PR 1 (`sp_municipio_hex.parquet`, `sp_hex.json`) e PR 2 (`dasymetric_weights.parquet`, `mun_base.parquet`, `hex_base.parquet`).
- **Invariantes verificados em teste (`tests/test_pr3_invariants.py`) e em `pipeline/verify.py`:**
  - Conservação exata municipal (`rel_tol = 1e-6`) e estadual (`±0,1%`) em vínculos, matrículas básicas, matrículas superiores, estabelecimentos, leitos e MW aceitos.
  - `QL(SP inteiro, divisão) == 1.0` para toda divisão CNAE presente em SP; município sem vínculos tem `QL = 0.0` (zero divisão por zero).
  - Todo ponto aceito cai num hex da grade de SP; pontos inválidos/fora de SP aparecem no relatório de rejeitados com motivo.
  - Orçamentos web: cada lente SP `≤ 50 KB` raw; `pontos.json` SP `≤ 200 KB` raw; `cities.json` compacto para City View.
- **Frontend Canvas 2D + City View (`web/src/city-view/`):**
  - 4 novas lentes posicionais (`distritos`, `ciencia_educacao`, `saude`, `infra`) totalizando 8 lentes no seletor.
  - Camada de pontos de infraestrutura (usinas, portos, hospitais) renderizada no Canvas quando ativa (`infra` ou toggle de pontos).
  - Banners clicáveis dos principais polos de SP (e botão no hex selecionado) abrindo o drawer **City View** com yields da cidade, Distritos especializados (`QL > 2` em CNAE 2 dígitos), perfil de Cidadãos (composição setorial de vínculos), educação/saúde/infra e fontes/anos de referência.
