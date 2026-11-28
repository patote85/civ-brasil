## Resumo — PR #4: Lentes Sensíveis SP (TSE 2024, IDHM/Gini 2010, SSP-SP 2025), Explorer 645 Municípios e Playwright E2E

Entrega as 3 lentes sensíveis de São Paulo com salvaguardas metodológicas explícitas (`docs/adr/0003-lentes-sensiveis.md`), o **Explorer** interativo dos 645 municípios (tabela ordenável/filtrável sem acento + scatter Canvas X×Y com escala log segura para zero) e verificação E2E real via **Playwright** integrada ao CI.

### O que entrou
1. **3 novas fontes oficiais (`pipeline/sources/{tse,ipea_idhm,ssp_sp}/`, total 14/14 fontes em cache):**
   - **TSE 2024 (`lealdade`):** `34.558.108` eleitores aptos, `25.799.855` comparecimentos (`74,66%`), correspondência TSE↔IBGE `645/645` sem colisão, reconciliação exata de votos (`validos + brancos + nulos + anulados_sub_judice == comparecimento`) e varredura automatizada garantindo **zero adjetivos ou ranking de partidos**.
   - **IPEA / PNUD Atlas Brasil (`desenvolvimento`):** IDHM e Gini em `[0, 1]` para `645/645` municípios com `ano_ref=2010` explícito e reconciliação por taxa ponderada pela população.
   - **SSP-SP 2025 (`descontentamento`):** `2.437` homicídios (`5,49/100k`), `161.310` roubos, flag `baixa_populacao` para `393` municípios `< 20k` hab e nota obrigatória de subnotificação.
2. **Explorer (`web/src/explorer/explorer.ts` + `web/public/data/sp/explorer.json` = `179 KB ≤ 350 KB`):**
   - 645 linhas ordenáveis por qualquer indicador, busca sem acento e scatter Canvas 2D com seleção de eixos X/Y e escala linear/log segura para zero, sincronizado com o mapa hexagonal e o City View.
3. **Verificação E2E Playwright (`web/e2e/app.spec.ts`, `qa/verification/SKILL.md`, `Makefile`, `.github/workflows/ci.yml`):**
   - `make e2e` rodando sobre `vite preview` em `1280×800` e `375×812`: valida 11 lentes, notas obrigatórias, City View, Explorer (`645` linhas e `645` pontos no scatter), zero requisições externas e zero erros de console.

### Evidências
- [00-in-your-own-words.md](docs/evidencias/pr4/00-in-your-own-words.md)
- [tdd.md](docs/evidencias/pr4/tdd.md)
- [verify.md](docs/evidencias/pr4/verify.md)
- [relatorio.md](docs/evidencias/pr4/relatorio.md)
- [ADR 0003](docs/adr/0003-lentes-sensiveis.md)
