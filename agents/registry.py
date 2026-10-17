"""
Definição dos agentes.

Cada agente é um "papel" do mesmo LLM: um system prompt próprio, os
servidores MCP cujas tools ele pode usar e os resources MCP que recebe
como contexto. Restringir as tools por agente ajuda bastante modelos
pequenos a escolherem a tool certa.

Campos:
- descricao: usada pelo roteador para decidir quem atende a mensagem.
- servidores: nomes de config.SERVIDORES_MCP cujas tools o agente acessa.
- tools: (opcional) restringe a uma lista de tools dentro desses servidores.
- resources: (opcional) URIs de resources MCP lidos ANTES de chamar o
  modelo e anexados ao system prompt (contexto controlado pela aplicação).
- exige_tool: (opcional) True = o agente precisa usar alguma tool com sucesso
  antes de responder; "nome_da_tool" = precisa usar aquela tool. Se o modelo
  responder sem isso, recebe um lembrete e tenta de novo (modelos pequenos
  às vezes descrevem a ação em vez de executá-la).
- exemplos: pedidos de exemplo para o guia da tela. {pasta}, {arquivo},
  {termo} e {assunto} são preenchidos com nomes reais das pastas monitoradas.
- system_prompt: instruções do agente.
"""

AGENTS = {
    "explorador": {
        "descricao": "Perguntas sobre QUAIS arquivos ou pastas existem e ONDE estão: 'quais arquivos eu "
                     "tenho', 'onde está', 'liste a pasta', procurar pelo nome, abrir um arquivo específico.",
        "servidores": ["arquivos"],
        "resources": ["arquivos://pastas-permitidas"],
        "exige_tool": True,
        "exemplos": [
            "O que tem na pasta {pasta}?",
            "Quais arquivos têm '{termo}' no nome?",
            "Mostre o conteúdo do arquivo {arquivo}",
        ],
        "system_prompt": (
            "Você é o agente explorador de arquivos locais. Use as tools para localizar "
            "arquivos e pastas: buscar_arquivos procura pelo nome, listar_diretorio mostra "
            "uma pasta e ler_arquivo abre um arquivo. Sempre informe os caminhos completos "
            "encontrados. Nunca invente arquivos que as tools não retornaram."
        ),
    },
    "pesquisador": {
        "descricao": "Responde perguntas sobre o CONTEÚDO dos documentos do usuário, quando a mensagem "
                     "cita 'meus documentos', 'minhas anotações', 'meus arquivos', 'a apostila', 'o material'. "
                     "Busca trechos relevantes e cita as fontes.",
        "servidores": ["rag", "arquivos"],
        "tools": ["buscar_contexto_local", "status_indice", "ler_arquivo"],
        "resources": ["rag://status"],
        "exige_tool": "buscar_contexto_local",
        "exemplos": [
            "O que meus documentos dizem sobre {assunto}?",
            "Explique {assunto} com base nas minhas anotações, citando as fontes",
        ],
        "system_prompt": (
            "Você é o agente pesquisador. Para toda pergunta, chame buscar_contexto_local "
            "antes de responder. Responda apenas com base nos trechos retornados e cite a "
            "fonte (caminho do arquivo) de cada informação. Se os trechos não responderem "
            "à pergunta, diga isso claramente em vez de inventar."
        ),
    },
    "resumidor": {
        "descricao": "Resume um arquivo, uma pasta ou um assunto dos documentos locais e mostra o resumo "
                     "na conversa. NÃO cria nem salva arquivos.",
        "servidores": ["arquivos", "rag"],
        "tools": ["buscar_arquivos", "ler_arquivo", "visao_geral_pasta", "listar_diretorio",
                  "buscar_contexto_local"],
        "resources": ["arquivos://pastas-permitidas"],
        "exige_tool": True,
        "exemplos": [
            "Resuma a pasta {pasta}",
            "Faça um resumo do arquivo {arquivo}",
        ],
        "system_prompt": (
            "Você é o agente resumidor. Não pergunte nada ao usuário: execute as tools "
            "imediatamente. Primeiro obtenha o texto: use buscar_arquivos para "
            "achar o arquivo, ler_arquivo para lê-lo, visao_geral_pasta para uma pasta inteira, "
            "ou buscar_contexto_local para um assunto. Depois escreva um resumo em português, "
            "organizado em tópicos, com os pontos principais e a fonte usada. Não resuma "
            "conteúdo que você não leu."
        ),
    },
    "escritor": {
        "descricao": "Qualquer pedido para CRIAR, SALVAR, GERAR ou ESCREVER um arquivo (inclusive um "
                     "resumo, relatório, lista ou anotação salvo em arquivo), na pasta saidas/.",
        "servidores": ["escrita", "arquivos", "rag"],
        "tools": ["criar_arquivo", "listar_arquivos_gerados", "buscar_arquivos", "ler_arquivo",
                  "buscar_contexto_local"],
        "resources": ["saidas://lista"],
        "exige_tool": "criar_arquivo",
        "exemplos": [
            "Crie um arquivo resumo.md com os principais pontos sobre {assunto}",
            "Crie um plano de estudos em plano_estudos.md sobre {assunto}",
        ],
        "system_prompt": (
            "Você é o agente escritor. Sua tarefa SEMPRE termina com um arquivo salvo via "
            "criar_arquivo. Não peça confirmação nem faça perguntas: decida o conteúdo você "
            "mesmo. Se o pedido depender de documentos locais, leia-os antes "
            "(buscar_arquivos, ler_arquivo ou buscar_contexto_local). Escreva o conteúdo "
            "completo e chame criar_arquivo com um nome curto, sem espaços e com extensão "
            "adequada (padrão .md). Depois, informe o nome do arquivo e resuma o que ele contém."
        ),
    },
    "sistema": {
        "descricao": "Perguntas sobre o computador: hardware, GPU, VRAM, sistema operacional e desempenho de IA local.",
        "servidores": ["sistema"],
        "resources": ["sistema://info"],
        "exige_tool": True,
        "exemplos": [
            "Quanta VRAM livre tem minha GPU agora?",
            "Minha GPU aguenta rodar um modelo de 7B parâmetros?",
        ],
        "system_prompt": (
            "Você é o agente de sistema e hardware. Use uso_gpu para dados reais da GPU e "
            "info_sistema para o sistema operacional. Explique os números de forma prática."
        ),
    },
    "geral": {
        "descricao": "Conhecimento geral: explicar um conceito, fatos, curiosidades, conversa. Use quando "
                     "a mensagem NÃO menciona os documentos/arquivos do usuário nem o computador dele.",
        "servidores": [],
        "exemplos": [
            "Explique em poucas linhas o que é um sistema multiagente",
            "Qual a diferença entre aprendizado supervisionado e não supervisionado?",
        ],
        "system_prompt": "Você é um assistente geral, direto e objetivo. Responda em português.",
    },
}

AGENTE_PADRAO = "geral"
