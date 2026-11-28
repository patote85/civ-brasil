# ADR 0003 — Lentes Sensíveis: Neutralidade, Anos de Referência e Pequenos Denominadores

- **Status:** Aceito (PR #4)
- **Contexto:** As lentes de participação eleitoral (TSE), desenvolvimento humano/desigualdade (IDHM/Gini) e segurança pública (SSP-SP) exigem salvaguardas metodológicas explícitas para evitar viés editorial, anacronismo ou distorção estatística.

## Decisões
1. **Lealdade (`lealdade` · TSE 2024):**
   - Mede exclusivamente **Participação Eleitoral (%)** no 1º turno das eleições municipais de 2024 (`100 × comparecimento / eleitorado`), com reconciliação exata de votos (`validos + brancos + nulos + anulados_sub_judice == comparecimento`).
   - Proibido qualquer adjetivo político, juízo de valor ou ranking partidário na lente, legenda, tooltip ou Explorer.
2. **Desenvolvimento (`desenvolvimento` · IPEA/PNUD Atlas Brasil 2010):**
   - Exibe **IDHM** e **Gini** em `[0, 1]` com `ano_ref=2010` explícito no título/nota, informando que é a última série censitária oficial completa para todos os municípios.
   - Reconciliado para o grid H3 por taxa ponderada pela população (`reconcile_rate`), nunca por soma.
3. **Descontentamento (`descontentamento` · SSP-SP 2025):**
   - Calcula taxas por 100 mil habitantes (`homicidio_100k` e `roubo_100k`) sobre a população censitária oficial.
   - Aplica flag explícito `baixa_populacao = True` para municípios com população `< 20.000` habitantes (onde poucos eventos produzem grande oscilação na taxa).
   - Exibe nota obrigatória de **subnotificação** e de que os números refletem **boletins de ocorrência registrados** (não vitimização total).
   - Escopo restrito a SP; na expansão nacional (PR #7), nunca será misturada à série nacional do Atlas da Violência.
