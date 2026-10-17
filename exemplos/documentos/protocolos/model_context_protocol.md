# Model Context Protocol (MCP)

O Model Context Protocol é um protocolo aberto, proposto pela Anthropic em
novembro de 2024, que padroniza como aplicações fornecem contexto e
ferramentas a modelos de linguagem. A ideia é parecida com a de uma porta
USB-C: em vez de cada aplicação criar uma integração própria para cada
fonte de dados, todas falam o mesmo protocolo.

## Papéis

- **Host**: a aplicação com que o usuário interage (um chat, uma IDE).
- **Cliente MCP**: componente dentro do host que mantém uma conexão 1:1
  com um servidor.
- **Servidor MCP**: processo que expõe capacidades (dados e ações).

## Primitivas expostas pelo servidor

1. **Tools (ferramentas)**: funções que o *modelo* decide chamar, com
   argumentos descritos por um JSON Schema. Exemplo: buscar um arquivo.
2. **Resources (recursos)**: dados identificados por URI que a *aplicação*
   lê e entrega como contexto. Exemplo: `rag://status`. Podem ser estáticos
   ou templates com parâmetros, como `rag://busca/{pergunta}`.
3. **Prompts**: modelos de mensagem reutilizáveis, escolhidos pelo
   *usuário*, com argumentos.

## Transporte

As mensagens seguem JSON-RPC 2.0. Os transportes mais comuns são **stdio**
(o cliente inicia o servidor como subprocesso e conversa pela entrada e
saída padrão) e **HTTP com streaming**, para servidores remotos.

No transporte stdio o servidor nunca deve escrever logs na saída padrão,
porque ela é o canal das mensagens do protocolo; logs vão para o stderr.

## Ciclo de vida

1. `initialize`: cliente e servidor negociam versão e capacidades.
2. Descoberta: `tools/list`, `resources/list`, `prompts/list`.
3. Uso: `tools/call`, `resources/read`, `prompts/get`.
4. Encerramento da conexão.
