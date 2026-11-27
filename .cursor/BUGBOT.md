# Regras de revisão — Bugbot (civ-brasil)

Ao revisar pull requests neste repositório, verifique obrigatoriamente:

1. **Nenhum segredo no repositório**: este repositório é público. Recuse chaves de API, tokens, credenciais, `.env` ou caminhos locais privados em arquivos versionados (exceto detecção opcional condicional no `Makefile` via `wildcard`).
2. **Testes sem rede**: nenhum teste Python ou TypeScript pode fazer chamadas HTTP/DNS externas. Testes de integração dependentes de dados brutos locais devem ler `CIVBR_RAW` e usar skip quando o diretório não existir.
3. **Invariantes de soma obrigatórios em qualquer reconciliação**: toda tabela de reconciliação espacial (ex.: município→hex) deve testar cobertura completa das unidades de origem, soma das frações igual a 1 dentro da tolerância definida, conservação de área/total e determinismo entre execuções.
4. **Nenhum modelo lê dados**: não deve haver chamadas a LLMs ou APIs de IA no pipeline de dados; toda ingestão, reconciliação e geração de saídas é 100% determinística.
5. **Nenhuma dependência de serviço pago**: o projeto não pode depender de bancos gerenciados, provedores pagos de mapas base/tiles ou APIs comerciais com chave paga.
