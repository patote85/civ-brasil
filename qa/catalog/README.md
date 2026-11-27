# Catálogo de QA — civ-brasil

Lista de drives de verificação relevantes para o projeto e cobertura atual no PR 1.

| Drive | Risco endereçado | Status no PR 1 | Como é verificado |
| --- | --- | --- | --- |
| **Rede não-ok no fetch** | HTTP != 200, timeout ou falha de rede ao baixar brutos do IBGE deixando arquivos parciais ou erros silenciosos | **Coberto (unitário)** | Testes unitários em `tests/test_ibge_malhas.py` com cliente injetado simulando falha de rede/HTTP sem acessar rede real; erro explícito na fronteira sem gravar arquivo corrompido. |
| **Storage corrompido no cache e manifesto** | Arquivo local alterado/truncado ou `data/manifest.json` com hash divergente/JSON inválido | **Coberto (unitário)** | Testes unitários em `tests/test_ibge_malhas.py` validando detecção de SHA-256 divergente e recusa/re-obtenção segura, além de falha explícita em manifesto inválido. |
| **Viewport 1280 px e 375 px** | Mapa, legenda ou tooltip quebrarem ou ficarem inacessíveis em desktop (1280 px) ou mobile (375 px) | **Coberto (unitário/CSS + build)** | Testes Vitest com `jsdom` em `web/src/` validando layout responsivo, legenda e formatação de tooltip em 1280 px e 375 px, somado a `make web-build` e `make verify`. Verificação visual em browser real fica para evolução com Playwright. |
| **I/O interrompido no meio do `data-sp`** | Escrita parcial de `sp_municipio_hex.parquet`, `sp_hex.json` ou `manifest.json` corrompendo saídas anteriores | **Coberto (escrita atômica)** | Escrita via arquivo temporário no mesmo diretório seguida de `os.replace`, testada em unidade contra falha intermediária para garantir que o arquivo final não fique corrompido. |
