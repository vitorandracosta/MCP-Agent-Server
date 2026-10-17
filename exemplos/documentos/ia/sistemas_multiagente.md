# Sistemas multiagente com LLMs

Um sistema multiagente divide uma tarefa entre agentes especializados.
Com modelos de linguagem, um "agente" costuma ser a combinação de:

- um **papel** (instruções de sistema),
- um conjunto de **ferramentas** que ele pode usar,
- um **laço de execução**: o modelo pede uma ferramenta, recebe o
  resultado e decide o próximo passo até produzir a resposta final.

## Roteamento

Um componente roteador decide qual agente atende cada pedido. Pode ser
feito por regras (palavras-chave), por classificação com o próprio LLM ou
por um modelo de embeddings. Pedir ao LLM que justifique a escolha torna
o sistema mais transparente e ajuda a depurar erros de roteamento.

## Por que restringir ferramentas por agente

Modelos pequenos (3 a 8 bilhões de parâmetros) erram mais quando recebem
muitas ferramentas de uma vez. Oferecer a cada agente só as ferramentas
do seu papel reduz chamadas erradas e o tamanho do prompt.

## Problemas comuns

- O modelo descreve a ação em vez de executá-la ("vou criar o arquivo...").
- Laços infinitos de chamadas de ferramenta.
- Alucinação de resultados de ferramentas que não foram chamadas.

Mitigações: limitar o número de rodadas, exigir que certas ferramentas
sejam chamadas antes da resposta e registrar cada passo para auditoria.
