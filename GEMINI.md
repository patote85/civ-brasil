# Regras de execução — civ-brasil

Estas regras governam qualquer execução automatizada neste repositório:

1. Antes de escrever código para uma nova tarefa/PR, registre o entendimento do problema com `/in-your-own-words` em `docs/evidencias/<pr>/00-in-your-own-words.md`.
2. Execute comandos um por vez, em foreground e síncronos, usando caminhos absolutos quando necessário e sem encadeamento opaco.
3. Instale dependências apenas por `make setup`. Não grave caminhos específicos de máquina local em `pyproject.toml`, `package.json` ou `.npmrc`.
4. Nenhum teste pode acessar a rede. Testes de integração que dependam de arquivos brutos locais usam `CIVBR_RAW` e são pulados quando o diretório não existe.
5. Toda reconciliação espacial ou estatística exige testes de invariantes pela interface pública (cobertura total, conservação de somas/frações e determinismo).
6. Nenhum modelo de linguagem lê ou transforma dados do pipeline; todo processamento de dados é feito por scripts determinísticos.
7. Comentários no código apenas quando indispensáveis; evite documentação ou arquivos markdown não solicitados.
8. Pare e reporte após 3 falhas consecutivas no mesmo gate (testes, lint, tipos, build ou verify).
9. Valide sempre os artefatos reais gerados (`make check`, `make data-sp`, `make web-build`, `make verify`).
