# In Your Own Words — PR 4 (Lentes Sensíveis SP, Explorer e Verificação E2E)

## 1. Problema que estamos resolvendo
O piloto de São Paulo já possui 8 lentes (PIB, Indústria, Agro, População, Distritos/QL, Ciência/Educação, Saúde e Infraestrutura) e o City View. Faltam três dimensões essenciais — que exigem rigor metodológico e neutralidade estrita — além da visão tabular/estatística integrada dos 645 municípios e de testes E2E reais em browser headless:

1. **Lentes Sensíveis SP (`docs/adr/0003-lentes-sensiveis.md`):**
   - **Lealdade / Participação Eleitoral (TSE 2024):** comparecimento/abstenção e reconciliação exata de votos municipais (incluindo votos válidos, brancos, nulos e `anulados_sub_judice`), com correspondência TSE↔IBGE cobrindo `645/645` municípios sem colisão e **zero adjetivos ou ranking de partidos**.
   - **Desenvolvimento / IDHM & Gini (Atlas Brasil / PNUD / IPEA 2010):** `ano_ref=2010` explícito em todas as notas, valores estritamente em `[0, 1]` e reconciliação por taxa ponderada pela população (`reconcile_rate`).
   - **Descontentamento / Segurança Pública (SSP-SP):** taxas recalculáveis por 100 mil habitantes, flag explícito `baixa_populacao` para municípios `< 20.000` hab (evitando distorção de pequenos denominadores) e nota obrigatória de subnotificação/registro policial.
2. **Explorer dos 645 municípios (`web/src/explorer/`):**
   - Tabela interativa com os 645 municípios de SP (`web/public/data/sp/explorer.json ≤ 350 KB` raw), busca sem acento, ordenação por qualquer indicador e **scatter plot Canvas X×Y** (com escala linear ou log segura para zero) clicável e sincronizado com o mapa hexagonal e o City View.
3. **Verificação E2E Playwright (`web/e2e/`, `qa/verification/SKILL.md`, `Makefile`, `.github/workflows/ci.yml`):**
   - Testes E2E rodando sobre `vite preview` em `1280×800` e `375×812` validando 645 linhas no Explorer, 645 pontos no scatter, busca `"São José dos Campos"`, troca de todas as lentes (com notas obrigatórias visíveis), zero requisições externas e zero erros de console.

## 2. Invariantes e restrições obrigatórias
- **Neutralidade estrita:** teste automatizado varrendo `civ_rules.yaml`, labels e notas da lente Lealdade garantindo zero adjetivos/juízos de valor ou ranking de partido.
- **TSE 2024:** correspondência TSE↔IBGE `645/645` sem colisão; `comparecimento ≤ eleitorado`; soma exata de votos (`validos + brancos + nulos + anulados_sub_judice == comparecimento`).
- **IDHM/Gini:** `0 <= idhm <= 1`, `0 <= gini <= 1`, `ano_ref=2010` explícito.
- **SSP-SP:** taxa por 100 mil hab recalculável (`1e-6`), flag `baixa_populacao` para `pop < 20_000`, nota de subnotificação obrigatória.
- **Orçamentos:** `explorer.json ≤ 350 KB` raw; total de dados SP `≤ 1,5 MB` raw; zero regressão nos artefatos de PR 1, PR 2 e PR 3.
- **Regras do repositório:** zero LLM tocando dados; zero rede nos testes unitários; `make check`, `make data-sp` ×2 (determinismo), `make web-build`, `make verify` e `make e2e` todos com exit `0`.
