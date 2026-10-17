# Arquitetura e decisões técnicas

Este documento detalha o funcionamento interno do sistema e o porquê de
cada decisão. Para uma visão geral e instruções de uso, veja o
[README](../README.md).

## 1. Componentes

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| Configuração | `config.py` | Lê o `.env` e centraliza LLM, pastas, RAG e a lista de servidores MCP; aplica as opções do RAG editadas pela tela (`dados/rag_config.json`) |
| HubMCP | `orquestrador.py` | Inicia cada servidor MCP como subprocesso, mantém as sessões e cataloga tools, resources, templates e prompts |
| Orquestrador | `orquestrador.py` | Para cada pedido: roteia, lê resources, roda o loop de tool-calling e emite eventos |
| Roteador | `agents/router.py` | Pede ao LLM `{agente, motivo}` em JSON e normaliza a resposta |
| Registro de agentes | `agents/registry.py` | Papel de cada agente: prompt, servidores, tools, resources, `exige_tool`, exemplos |
| Servidores MCP | `servers/*_server.py` | Um processo por domínio, com FastMCP |
| RAG | `rag/` | Extração de texto, chunking, embeddings e ChromaDB |
| API web | `web/app.py`, `web/rag.py` | REST + stream NDJSON; histórico, guia e administração do RAG |
| Interface | `web/static/` | HTML/CSS/JS sem frameworks, em módulos ES |

## 2. Por que "um LLM, vários papéis"

Rodar vários modelos ao mesmo tempo numa GPU de 4 GB não é viável. Cada
agente é, portanto, o **mesmo LLM** com:

- um *system prompt* próprio;
- um **subconjunto de tools**. Modelos pequenos erram mais quando recebem
  muitas ferramentas, e restringir também reduz o tamanho do prompt;
- **resources** que viram contexto antes da primeira chamada ao modelo.

A especialização vem do contexto, não dos pesos.

## 3. Uso das três primitivas do MCP

| Primitiva | Quem decide | Como o sistema usa |
|---|---|---|
| **Tool** | o modelo | O orquestrador envia ao LLM só as tools do agente; o LLM pede a chamada; o HubMCP faz `tools/call` no servidor dono |
| **Resource** | a aplicação | Antes de chamar o LLM, o orquestrador faz `resources/read` dos URIs do agente e anexa o conteúdo ao system prompt (ex.: o explorador recebe `arquivos://pastas-permitidas` e já sabe onde procurar) |
| **Prompt** | o usuário | A aba "Recursos MCP" lista os prompts, preenche os argumentos (`prompts/get`) e envia o texto para a conversa |

O template `rag://busca/{pergunta}` expõe a busca semântica também como
resource, para clientes MCP que montam URIs dinamicamente.

A aba RAG da tela também é um cliente dessas primitivas: lê
`rag://arquivos` (inventário do índice), `rag://arquivo/{caminho}` (trechos
de um arquivo) e chama `buscar_trechos` (busca em JSON). Nenhum agente
recebe essas três, porque os agentes que usam o servidor `rag` têm lista
fechada de tools.

## 4. Roteamento

1. O prompt do roteador lista `nome: descrição` de cada agente, as últimas
   mensagens da conversa (para perguntas de continuação) e a mensagem atual.
2. A chamada usa `temperature=0` e `response_format={"type": "json_object"}`.
3. A resposta é normalizada: remove acentos, aspas e pontuação, procura um
   nome válido no campo `agente` e, se não achar, no texto inteiro.
4. Se ainda assim não houver agente válido, ou o LLM estiver fora do ar, a
   escolha cai no agente padrão (`geral`) com `metodo: "padrao"`.

O usuário pode forçar um agente (seletor na tela ou `/agente <nome>` no
terminal); nesse caso `metodo: "manual"` e o LLM não é consultado.

As descrições dos agentes são o principal ponto de ajuste da acurácia. Veja
`avaliacao/` e os resultados no README.

## 5. Loop de tool-calling e salvaguardas

```
para cada rodada (máx. MAX_ITERACOES_TOOLS = 6):
    resposta = LLM(mensagens, tools do agente)
    se não há tool_calls:
        se o agente exige uma tool e ela ainda não rodou com sucesso
           e o lembrete ainda não foi enviado:
            envia lembrete ("não pergunte, chame a tool") e continua
        senão: retorna a resposta
    para cada tool_call:
        recusa se a tool não pertence ao agente
        recusa se os argumentos não são JSON válido
        executa via HubMCP; o resultado (ou erro) volta como mensagem "tool"
limite atingido: pede a resposta final sem oferecer tools
```

- **`exige_tool`** (`True` = qualquer tool; `"nome"` = uma específica) ataca
  a falha mais comum de modelos pequenos: descrever a ação em vez de executá-la.
- Erros das tools são levantados como exceção no servidor; o FastMCP os
  devolve com `isError=True`, então o orquestrador distingue falha de sucesso.
- **Evitar erros recuperáveis**: modelos pequenos raramente se recuperam de
  um erro de tool. Por isso, quando dá, a tool resolve sozinha em vez de
  falhar: `criar_arquivo` com nome já existente salva como `nome_2.md` e
  avisa no resultado.
- **Cada agente precisa das tools do pedido inteiro**: só um agente atende
  cada turno. Por isso o escritor também tem `listar_diretorio` e recebe
  `arquivos://pastas-permitidas`; sem isso, "escreva um arquivo com as
  matérias que tenho" (nomes de pastas) era impossível e o modelo inventava
  caminhos.

### Janela de contexto do Ollama

A janela de contexto é configurada **no Ollama** (`OLLAMA_CONTEXT_LENGTH`),
não pela API compatível com OpenAI. Um turno do escritor soma system prompt,
resources, schemas de 6 tools, até 6000 caracteres de `ler_arquivo` e até
10 mensagens de histórico, o que passa do padrão menor do Ollama. Quando passa,
o Ollama descarta o início da conversa **sem erro**, às vezes levando junto
as instruções do agente. O projeto recomenda 8192 tokens: no `qwen2.5:3b`
(Q4_K_M) isso ocupa ~2,3 GB e cabe inteiro numa GPU de 4 GB.

## 6. Eventos

Toda execução é uma sequência de eventos (dicts), cada um com `t_ms`, o
tempo desde o início do pedido:

| Evento | Campos |
|---|---|
| `roteamento` | `agente`, `motivo`, `metodo` (`llm`/`manual`/`padrao`), `servidores`, `tools`, `resources` |
| `resource_lido` | `uri`, `servidor`, `conteudo` (prévia), `erro` |
| `tool_chamada` | `tool`, `servidor`, `args` |
| `tool_resultado` | `tool`, `resultado` (prévia), `erro` |
| `aviso` | `mensagem` (lembrete do `exige_tool`, limite de rodadas) |
| `resposta` | `agente`, `conteudo` |
| `erro` | `mensagem` |

A API transmite os eventos em **NDJSON** (um JSON por linha), e a tela os
desenha conforme chegam. O mesmo vetor de eventos é salvo no SQLite, e o
histórico e o fluxograma reconstroem a execução a partir dele.

## 7. RAG

- **Extração**: `pypdf` (PDF), `python-docx` (DOCX) e leitura direta (txt, md, py).
  PDFs escaneados (imagem) não geram texto: aparecem como "sem texto" na aba RAG.
- **Chunking**: por caracteres; padrão 800 com 120 de sobreposição.
- **Embeddings**: `sentence-transformers` (padrão `all-MiniLM-L6-v2`, 384
  dimensões), normalizados.
- **Banco**: ChromaDB persistente com distância de **cosseno**, então
  `similaridade = 1 - distância` fica em [-1, 1].
- **Reindexação incremental**: `manifest.json` guarda o `mtime` de cada
  arquivo; só o que mudou é reprocessado, e arquivos apagados (ou que saíram
  das fontes) saem do índice.
- **Troca de métrica ou de modelo**: o modelo de embedding fica nos metadados
  da coleção; se mudar (ou se a coleção for antiga, com L2), ela é recriada
  e reindexada, porque vetores de modelos diferentes não são comparáveis.
- **Troca de chunking**: `parametros.json` guarda tamanho e sobreposição da
  última indexação; se mudarem, tudo é refeito (trechos de tamanhos
  diferentes no mesmo índice distorcem a busca).

### Opções editáveis pela tela

Fontes, chunking, top-k, extensões e modelo de embedding podem ser mudados
na aba RAG. Eles ficam em `dados/rag_config.json` e sobrepõem os valores do
código e do `.env`:

| Chave | Efeito |
|---|---|
| `chunk_size`, `chunk_overlap`, `top_k`, `extensoes`, `embedding_model` | sobrepõem os padrões do `config.py` / `.env` |
| `fontes_extras` | pastas ou arquivos soltos adicionados como fonte |
| `fontes_removidas` | fontes do `.env` desligadas pela tela (o `.env` não muda; dá para restaurar) |
| `exclusoes` | subpastas/arquivos de dentro de uma fonte que não são indexados |

Arquivos enviados pela tela vão para `dados/enviados/`, que vira uma fonte
automaticamente.

**Problema de processos separados**: cada servidor MCP é um processo que
importou o `config` na inicialização. Para que uma fonte adicionada pela tela
valha na hora (para o indexador e para a allowlist do servidor `arquivos`),
quem usa essas opções chama `config.sincronizar()`, que compara o `mtime` do
`rag_config.json` com o da última leitura e só relê quando ele mudou (custa
um `stat`). O índice Chroma continua sendo aberto **só** pelo servidor `rag`:
a API web nunca abre o banco, só edita a configuração e pede a reindexação
pela tool `reindexar_documentos`.

**Remover vs. excluir**: remover uma fonte tira os arquivos do índice e do
alcance dos agentes. Excluir uma subpasta ou arquivo só o tira do índice
(o indexador nem entra na pasta); o explorador ainda consegue abri-lo pelo nome.

## 8. Segurança

- **Leitura** só dentro de `PASTAS_LEITURA` (pastas monitoradas + `saidas/`).
  A checagem usa `Path.is_relative_to` após `resolve()`, comparando
  componentes do caminho: `.../Docs_privados` não passa como filho de `.../Docs`.
- **Escrita** só em `saidas/`: rejeita `..`, caminhos absolutos e extensões
  fora da lista, e não sobrescreve sem `sobrescrever=true` (nome repetido
  vira `nome_2.md`).
- **Fontes pela tela**: a API recusa caminhos relativos, inexistentes, a raiz
  de um disco e formatos não suportados. A tela só escuta em `127.0.0.1`.
  Quem a acessa pode ampliar o que os agentes leem, então não a exponha na rede.
- **Envio de arquivos**: o nome é reduzido ao nome base (sem diretórios),
  limitado às extensões suportadas e a 50 MB; só arquivos de
  `dados/enviados/` podem ser apagados pela tela.
- **stdio**: nos servidores MCP o stdout é o canal do protocolo, por isso
  todos os logs vão para o stderr.
- **Prompt injection via documento**: um texto indexado pode tentar induzir o
  modelo a ler ou escrever fora do escopo; a allowlist limita o estrago ao
  que já é permitido.
- Configuração pessoal (pastas, chaves) fica no `.env`, fora do git.

## 9. Histórico

SQLite (`dados/historico.sqlite3`), duas tabelas:

- `conversas(id, titulo, pasta, criada_em, atualizada_em)`
- `turnos(id, conversa_id, pergunta, agente, motivo, metodo, resposta, erro, eventos JSON, duracao_ms, criado_em)`

O título pode ser renomeado pela tela, e um novo turno não o sobrescreve.
`pasta` é um texto livre (`NULL` = sem pasta): uma pasta existe enquanto
houver conversas nela, e renomear ou desfazer a pasta atualiza todas as
conversas de uma vez. Bancos criados antes dessa coluna ganham a coluna
automaticamente na abertura (`ALTER TABLE`).

Só os pares pergunta/resposta bem-sucedidos voltam como contexto para o LLM
(no máximo `MAX_HISTORICO` mensagens). Se o navegador fechar no meio, o
turno é salvo mesmo assim, marcado como interrompido.

## 10. Como estender

**Nova tool**: no servidor adequado, uma função com `@mcp.tool()`. A
docstring é a descrição que o LLM lê; tipos anotados viram o JSON Schema.

**Novo resource ou prompt**: `@mcp.resource("esquema://nome")` ou
`@mcp.prompt(name=...)` no servidor.

**Novo servidor**: `servers/<nome>_server.py` com sua instância `FastMCP` e
`mcp.run(transport="stdio")`; registre em `SERVIDORES_MCP` no `config.py`.

**Novo agente**: uma entrada em `AGENTS` (`agents/registry.py`). Na
inicialização, o HubMCP valida que servidores, tools e resources citados
existem. Depois de mudar descrições, rode `python -m avaliacao.avaliar_roteador`
e acrescente casos ao `avaliacao/casos_roteador.json`.
