# Núcleo neurossimbólico jurídico

Use este recurso quando agentes precisarem produzir uma análise, minuta ou decisão candidata sujeita a gates epistêmicos determinísticos.

## Contrato

Os modelos executam a parte neural: interpretam linguagem, extraem proposições, sugerem regras, formulam alternativas e redigem. O script `scripts/legal_epistemic_gate.py` executa a parte simbólica: valida identidade e referências, deriva conclusões, aplica exceções e prioridades, verifica proveniência, controla desconhecidos decisivos e confere autoridade.

O script usa apenas a biblioteca padrão do Python. Ele não verifica se uma interpretação jurídica está correta nem transforma texto natural em regra automaticamente. A formalização produzida pelo agente continua sujeita a crítica, fontes primárias, painel e auditoria.

## Representação intermediária

Produzir um documento conforme [legal-epistemic-graph-v1.schema.json](legal-epistemic-graph-v1.schema.json). Usar [exemplo-grafo-minimo.json](exemplo-grafo-minimo.json) como ponto de partida.

Cada conclusão decisiva precisa de uma fonte verificada ou de uma derivação que alcance uma fonte verificada. Consenso, votos e avaliações de agentes não são fontes probatórias. Uma regra pode ser:

- `strict`: prevalece sobre regra derrotável incompatível;
- `defeasible`: pode ser vencida por exceção confirmada ou por regra conflitante de prioridade maior.

Conflitos de mesma força permanecem abertos. O motor não inventa um desempate.

## Execução

```bash
python3 "$HOME/.codex/skills/analise-juridica-epistemica/scripts/legal_epistemic_gate.py" \
  validate grafo.json \
  --artifact minuta.md \
  --out recibo-epistemico.json
```

Omitir `--artifact` quando ainda não houver documento congelado. Quando o parâmetro for usado, `artifact.sha256` no grafo deve corresponder aos bytes do arquivo indicado.

Saídas:

- código `0`: todos os gates fecharam;
- código `2`: o grafo foi processado, mas existem violações materiais;
- código `1`: entrada ilegível, JSON inválido, data inválida ou erro operacional.

O recibo separa conclusões aceitas, condicionais e derrotadas; regras bloqueadas por exceção confirmada; exceções potenciais ainda desconhecidas; violações; autorizações externas pendentes; decisões humanas necessárias; e conferência do artefato. Persistir o recibo junto ao hash da versão avaliada.

Uma conclusão que dependa de desconhecido decisivo aparece em `conditional_conclusions`, nunca em `accepted_conclusions`. Ação `proposed` ou `prepared` pode manter o gate conforme, mas deve aparecer em `pending_authorizations` até existir grant exato. Passar a ação para `authorized`, `executed` ou `verified` sem grant válido produz violação bloqueante.

## Integração no loop

1. O redator ou extrator produz o grafo contra o snapshot comum de fontes.
2. O host congela grafo e artefato e registra seus hashes.
3. O núcleo simbólico emite o recibo.
4. Violações retornam ao responsável pela consolidação como objeções tipadas.
5. Alteração do grafo ou artefato cria novo hash e exige novo recibo.
6. Somente um recibo conforme permite seguir ao painel e à auditoria; ele não os substitui.
7. Uma decisão humana altera o grafo por nova proposição, cenário ou grant verificável; não se edita o recibo.

## Limites da primeira versão

O motor implementa encadeamento positivo, regras estritas e derrotáveis, exceções, prioridade inteira e conflitos binários declarados. Ele não implementa quantificadores, lógica temporal completa, analogia, balanceamento de princípios, ontologias OWL, LegalRuleML integral ou semântica de precedentes. Use-o como controle de consistência e proveniência, não como juiz automatizado.

Formalizar primeiro domínios estreitos e verificáveis: prazos, requisitos, cobertura contratual, admissibilidade, congruência, permissões e estados do fluxo. Questões de credibilidade, proporcionalidade, estratégia, intenção e valores permanecem como decisões humanas ou análises por cenários.
