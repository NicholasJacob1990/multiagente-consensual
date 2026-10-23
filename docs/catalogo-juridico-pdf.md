# Catálogo jurídico e PDF

O repositório reúne dois plugins: `multiagente-consensual` e `legal-br`.
As fontes jurídicas locais foram incorporadas sem backups, caches, recibos de
sincronização ou arquivos dos casos usados para desenvolvê-las. As adaptações
de distribuição preservam os originais da máquina de origem.

## Skills do plugin principal

| Skill | Função |
|---|---|
| `bridge-agentes` | Transporte local para os fluxos autorizados do Cowork. |
| `consenso` | Deliberação sobre versão congelada e verificável. |
| `loop-debate-agentes` | Rodadas de melhoria, inclusive emendas consensuais. |
| `workflow-agentes` | Equipes, papéis e dependências de execução. |
| `redacao-juridica-consensual` | Pareceres, peças, recursos e outros trabalhos jurídicos com o motor consensual. |
| `minuta-juridica-fundamentada` | Redação jurídica direta e fundamentada. |
| `analise-juridica-epistemica` | Rastreabilidade de fatos, fontes, inferências e autoridade humana. |
| `auditoria-juridica-de-minutas` | Auditoria e comparação de versões, com leitura das revisões de DOCX. |
| `pdf` | Leitura, OCR, geração, operações e formulários PDF com conferência final. |

As nove skills são descobertas pelo plugin principal e pelo instalador NPM a
partir de `skills/`. O catálogo de 29 comandos multiagente permanece separado:
ter uma skill disponível não inicia agentes nem modifica a equipe selecionada.

## Plugin Legal BR

Em `plugins/legal-br/` estão os metadados Claude/Codex, o agente jurídico, hooks,
referências e scripts, além de dez skills:

`parecer`, `pesquisa-juridica`, `busca-acervo`, `resposta-juridica`,
`revisar-contrato`, `triagem-nda`, `risco-juridico`, `compliance-check`,
`verificacao-fornecedor` e `briefing-reuniao`.

O plugin pode ser instalado separadamente. No Claude, o namespace diferencia
as skills de `legal-br` das skills do plugin principal. MCPs de tribunais,
acervo local, indexadores, credenciais e assinaturas de provedores são
dependências opcionais do ambiente; não estão incluídos no repositório.

O hook jurídico apenas informa a disponibilidade das skills. Não escolhe uma
delas automaticamente, não autoriza ferramentas nem impõe aprovação extra.
Seu formato segue a [referência oficial de hooks do Claude](https://code.claude.com/docs/en/hooks).

Para o acervo legado, configurar `LEGALBR_ACERVO_RAW` e, se necessário,
`LEGALBR_CHROMA_DIR`. O índice unificado opcional continua em
`~/.local/share/ssd-index`; a ausência desse serviço não prova ausência da fonte.

## Instalar a partir deste checkout

```bash
git clone https://github.com/NicholasJacob1990/multiagente-consensual.git
cd multiagente-consensual
node npm/cli.mjs install --all
```

O instalador preserva extensões existentes. `--clean-managed` substitui os
diretórios das skills do pacote depois de fazer backup integral; usar somente
quando a intenção for restaurar a cópia distribuída.

O marketplace gerado pelo NPM disponibiliza ambos os plugins. O instalador
ativa o plugin principal; para selecionar o Legal BR no Claude:

```bash
claude plugin install legal-br@multiagente-npm
```

Alternativamente, registrar diretamente o marketplace do GitHub:

```bash
claude plugin marketplace add NicholasJacob1990/multiagente-consensual
claude plugin install multiagente-consensual@multiagente-local
claude plugin install legal-br@multiagente-local
```

Escolher uma das rotas de instalação evita ativar cópias do mesmo plugin por
marketplaces diferentes. Publicação no GitHub e publicação no registro NPM são
operações separadas; o checkout permite usar esta versão antes de seu envio ao NPM.

## Origem e verificação

`catalogo-origens.json` registra os hashes das fontes locais antes das
adaptações de portabilidade. O plugin Legal BR conserva a atribuição à base
Anthropic e sua licença de origem. A skill de PDF é uma entrada portátil desta
distribuição e não depende de marcadores internos de um aplicativo específico.

Os testes de distribuição verificam o caminho real dos dois plugins no
marketplace e as cópias instaladas. Os testes de leitura de DOCX, dos controles
epistêmicos e do hook usam documentos sintéticos; nenhum dossiê jurídico é
necessário para executá-los.
