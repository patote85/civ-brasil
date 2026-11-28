## Resumo — PR #5: Almanaque/Fontes, URL Shareable, CSP/Headers e 1ª Produção SP

Fecha o piloto de São Paulo para produção pública estática na Vercel (`*.vercel.app`):

### O que entrou
1. **Almanaque / Sobre & Fontes + UF View (`pipeline/civ/almanac.py`, `web/src/almanac/almanac.ts`, `web/public/data/sp/sources.json`):**
   - Catálogo determinístico gerado de `data/manifest.json` + `pipeline/civ/civ_rules.yaml` com 100% das fontes oficiais (órgão, artefato/URL, ano de referência, cobertura, licença e SHA-256) + resumo estadual (UF View SP).
2. **URL Shareable (`web/src/url-state/urlState.ts`, botão `Compartilhar`):**
   - Serializa e restaura `lente`, `modo` (`atlas`/`civ`), `pontos`, câmera (`x, y, z`) e `cidade` (reabrindo o City View automaticamente).
3. **Hardening de Produção (`vercel.json`, `web/public/404.html`, `web/public/og-sp.svg`, OG meta tags):**
   - CSP estrita (`default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control` imutável em `/assets/*` e página `404.html`.
4. **Verificação (`pipeline/verify.py`, `tests/test_pr5_invariants.py`, `web/e2e/app.spec.ts`):**
   - `make check` (`32` Python + `13` Vitest), `make web-build` (`44,77 KB` JS), `make verify` (payload inicial `~135 KB ≤ 600 KB`) e `make e2e` (`4 passed` em `1280×800` e `375×812`).
