# In Your Own Words — PR 5 (UX Civ Completo, Almanaque/Fontes, URL Shareable, CSP/Headers e 1ª Produção SP)

## 1. Problema que estamos resolvendo
O piloto de São Paulo já possui 11 lentes reais, camada de pontos, City View, Explorer dos 645 municípios e E2E Playwright no CI. Para concluir a 1ª versão de produção pública do piloto SP em `*.vercel.app`, precisamos entregar:

1. **Almanaque / Sobre & Fontes (`web/public/data/sp/sources.json`, `web/src/almanac/almanac.ts`):**
   - Gerado automaticamente de `data/manifest.json` + `pipeline/civ/civ_rules.yaml` no pipeline determinístico, exibindo 100% das fontes oficiais (órgão, URL, licença, ano de referência, cobertura e hash SHA-256) e o resumo estadual (UF/State View de SP).
2. **URL Shareable (`web/src/url-state/urlState.ts`):**
   - Serialização e restauração limpa de `lente`, `modo` (`atlas`/`civ`), câmera (`x`, `y`, `z`), `cidade` (código IBGE para reabrir o City View diretamente) e `pontos` (`auto`/`on`/`off`), além de botão **Compartilhar** copiando a URL atual.
3. **Hardening de produção (`vercel.json`, `web/public/404.html`, OG meta tags, `README.md`):**
   - CSP estrita sem origens externas (`default-src 'self'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, cache imutável em `/assets/*`, página 404 estática e metadados OpenGraph.
4. **Verificação ponta a ponta (`pipeline/verify.py`, `tests/test_pr5_invariants.py`, `web/e2e/app.spec.ts`):**
   - Teste que falha se qualquer fonte de `data/manifest.json` faltar em `sources.json` ou estiver sem licença; testes de serialização/restauração de URL state; orçamento inicial SP `≤ 600 KB` raw e total SP `≤ 2,0 MB` raw; E2E Playwright testando URL shareable + Almanaque/Sobre & Fontes em `1280×800` e `375×812`.
