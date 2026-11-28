---
name: civ-brasil-verification
description: Verificação E2E Playwright do civ-brasil sobre o bundle estático (vite preview) em 1280x800 e 375x812.
---

# Verificação E2E — civ-brasil

## Pré-requisitos
1. Artefatos gerados: `make data-sp` e `make web-build`.
2. Integridade estática validada: `make verify`.

## Execução
```bash
make e2e
```

## O que é verificado em `1280×800` e `375×812`
1. Canvas `#map-canvas` visível com `1091 hexes` carregados.
2. Troca por todas as lentes (`≥ 11`), validando exibição de `Fonte:` e `Ano:` na legenda.
3. Notas obrigatórias das lentes sensíveis (`2010` em `desenvolvimento`, `subnotificação` em `descontentamento`).
4. Busca sem acento (`Sao Jose dos Campos`) destacando hex e abrindo o City View com Distritos reais.
5. Explorer abrindo com exatamente `645` linhas na tabela e `645` pontos no scatter Canvas, filtro sem acento e navegação de volta ao mapa/City View.
6. Zero requisições de rede fora de `127.0.0.1:4173` e zero erros de console/página.
