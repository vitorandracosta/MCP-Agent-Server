"""
Orquestrador multiagente.

- HubMCP: inicia cada servidor MCP de config.SERVIDORES_MCP como
  subprocesso (stdio), mantém as sessões abertas e cataloga as três
  primitivas de cada servidor: tools, resources (e templates) e prompts.
- Orquestrador: para cada mensagem, escolhe o agente (roteador), lê os
  resources que o agente recebe como contexto, e roda o loop de
  tool-calling com o LLM. Tudo é emitido como eventos (dicts), consumidos
  pelo terminal (client.py) e pela tela web (web/app.py).

Eventos emitidos por Orquestrador.executar() (todos têm "t_ms", o tempo
desde o início do pedido):
  {"tipo": "roteamento", "agente", "motivo", "metodo", "servidores", "tools", "resources"}
  {"tipo": "resource_lido", "uri", "servidor", "conteudo", "erro"}
  {"tipo": "tool_chamada", "tool", "servidor", "args"}
  {"tipo": "tool_resultado", "tool", "resultado", "erro"}
  {"tipo": "aviso", "mensagem"}
  {"tipo": "resposta", "agente", "conteudo"}
  {"tipo": "erro", "mensagem"}
"""
import json
import os
import sys
import time
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

import config
from agents.registry import AGENTS
from agents.router import Escolha, classificar_agente

MAX_CHARS_PREVIEW = 2000


def _preview(texto: str) -> str:
    return texto if len(texto) <= MAX_CHARS_PREVIEW else texto[:MAX_CHARS_PREVIEW] + " [...]"


class HubMCP:
    def __init__(self):
        self._pilha = AsyncExitStack()
        self.sessoes = {}    # servidor -> ClientSession
        self.catalogo = {}   # servidor -> {"tools", "resources", "templates", "prompts"}
        self.tools = {}      # nome da tool -> {"servidor", "descricao", "schema" (formato OpenAI)}
        self.resources = {}  # uri -> servidor

    async def iniciar(self):
        ambiente = {**os.environ, "PYTHONUNBUFFERED": "1"}
        for servidor, modulo in config.SERVIDORES_MCP.items():
            params = StdioServerParameters(
                command=sys.executable, args=["-m", modulo], cwd=str(config.RAIZ), env=ambiente,
            )
            read, write = await self._pilha.enter_async_context(stdio_client(params))
            sessao = await self._pilha.enter_async_context(ClientSession(read, write))
            await sessao.initialize()
            self.sessoes[servidor] = sessao
            await self._catalogar(servidor, sessao)
        self._validar_agentes()

    async def _catalogar(self, servidor: str, sessao: ClientSession):
        tools = (await sessao.list_tools()).tools
        resources = (await sessao.list_resources()).resources
        templates = (await sessao.list_resource_templates()).resourceTemplates
        prompts = (await sessao.list_prompts()).prompts

        for t in tools:
            if t.name in self.tools:
                raise RuntimeError(f"Tool '{t.name}' duplicada nos servidores "
                                   f"{self.tools[t.name]['servidor']} e {servidor}.")
            self.tools[t.name] = {
                "servidor": servidor,
                "descricao": t.description,
                "schema": {"type": "function",
                           "function": {"name": t.name, "description": t.description,
                                        "parameters": t.inputSchema}},
            }
        for r in resources:
            self.resources[str(r.uri)] = servidor

        self.catalogo[servidor] = {
            "tools": [{"nome": t.name, "descricao": t.description, "parametros": t.inputSchema}
                      for t in tools],
            "resources": [{"uri": str(r.uri), "nome": r.name, "descricao": r.description,
                           "mime": r.mimeType} for r in resources],
            "templates": [{"uri": t.uriTemplate, "nome": t.name, "descricao": t.description,
                           "mime": t.mimeType} for t in templates],
            "prompts": [{"nome": p.name, "descricao": p.description,
                         "argumentos": [{"nome": a.name, "obrigatorio": bool(a.required)}
                                        for a in (p.arguments or [])]}
                        for p in prompts],
        }

    def _validar_agentes(self):
        for nome, agente in AGENTS.items():
            for servidor in agente["servidores"]:
                if servidor not in self.sessoes:
                    raise RuntimeError(f"Agente '{nome}' usa servidor desconhecido '{servidor}'.")
            exigida = agente.get("exige_tool")
            obrigatoria = [exigida] if isinstance(exigida, str) else []
            for tool in (agente.get("tools") or []) + obrigatoria:
                if tool not in self.tools:
                    raise RuntimeError(f"Agente '{nome}' usa tool inexistente '{tool}'.")
            for uri in agente.get("resources") or []:
                if uri not in self.resources:
                    raise RuntimeError(f"Agente '{nome}' usa resource inexistente '{uri}'.")

    def tools_do_agente(self, nome_agente: str) -> list:
        agente = AGENTS[nome_agente]
        permitidas = agente.get("tools")
        return [
            nome for nome, info in self.tools.items()
            if info["servidor"] in agente["servidores"] and (permitidas is None or nome in permitidas)
        ]

    async def chamar(self, nome_tool: str, args: dict):
        """Executa a tool no servidor dono dela. Retorna (texto, houve_erro)."""
        info = self.tools[nome_tool]
        resultado = await self.sessoes[info["servidor"]].call_tool(nome_tool, args)
        texto = "\n".join(c.text for c in resultado.content if getattr(c, "text", None))
        return texto, bool(resultado.isError)

    async def ler_resource(self, uri: str, servidor: str = None) -> str:
        """Lê um resource (estático ou de template). Sem servidor, usa o dono registrado da URI."""
        servidor = servidor or self.resources.get(uri)
        if servidor not in self.sessoes:
            raise KeyError(f"Não sei qual servidor atende '{uri}'.")
        resultado = await self.sessoes[servidor].read_resource(uri)
        return "\n".join(getattr(c, "text", "") or "" for c in resultado.contents)

    async def obter_prompt(self, servidor: str, nome: str, argumentos: dict) -> str:
        resultado = await self.sessoes[servidor].get_prompt(nome, argumentos)
        return "\n\n".join(getattr(m.content, "text", "") for m in resultado.messages)

    async def fechar(self):
        await self._pilha.aclose()


class Orquestrador:
    def __init__(self, hub: HubMCP):
        self.hub = hub
        self.llm = AsyncOpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
        self.modelo = config.LLM_MODEL

    def _system_prompt(self, nome_agente: str, contextos: list) -> str:
        agente = AGENTS[nome_agente]
        partes = [agente["system_prompt"]]
        for uri, conteudo in contextos:
            partes.append(f"Contexto do resource {uri}:\n{conteudo}")
        if "escrita" in agente["servidores"]:
            partes.append(f"Arquivos criados vão para: {config.OUTPUT_DIR}")
        partes.append("Responda sempre em português.")
        return "\n\n".join(partes)

    async def escolher(self, mensagem: str, historico: list, agente_forcado: str = None) -> Escolha:
        if agente_forcado:
            return Escolha(agente_forcado, "Agente escolhido manualmente pelo usuário.", "manual")
        return await classificar_agente(mensagem, self.llm, self.modelo, historico)

    async def executar(self, mensagem: str, historico: list, agente_forcado: str = None):
        """
        Processa uma mensagem e emite eventos. NÃO altera o histórico; quem
        chama decide guardar a pergunta e a resposta final.
        """
        inicio = time.perf_counter()
        async for evento in self._executar(mensagem, historico[-config.MAX_HISTORICO:], agente_forcado):
            evento["t_ms"] = round((time.perf_counter() - inicio) * 1000)
            yield evento

    async def _executar(self, mensagem: str, historico: list, agente_forcado: str):
        try:
            escolha = await self.escolher(mensagem, historico, agente_forcado)
            nome_agente = escolha.agente
            agente = AGENTS[nome_agente]
            tools = self.hub.tools_do_agente(nome_agente)
            yield {"tipo": "roteamento", **escolha.to_dict(), "servidores": agente["servidores"],
                   "tools": tools, "resources": agente.get("resources") or []}

            contextos = []
            for uri in agente.get("resources") or []:
                try:
                    conteudo, erro = await self.hub.ler_resource(uri), False
                    contextos.append((uri, conteudo))
                except Exception as e:
                    conteudo, erro = f"Falha ao ler resource: {e}", True
                yield {"tipo": "resource_lido", "uri": uri, "servidor": self.hub.resources.get(uri),
                       "conteudo": _preview(conteudo), "erro": erro}

            async for evento in self._loop_tools(nome_agente, mensagem, historico, tools, contextos):
                yield evento
        except Exception as e:
            yield {"tipo": "erro", "mensagem": f"{type(e).__name__}: {e}"}

    async def _loop_tools(self, nome_agente, mensagem, historico, tools, contextos):
        schemas = [self.hub.tools[t]["schema"] for t in tools]
        mensagens = (
            [{"role": "system", "content": self._system_prompt(nome_agente, contextos)}]
            + historico
            + [{"role": "user", "content": mensagem}]
        )
        exigida = AGENTS[nome_agente].get("exige_tool")
        sucesso = set()  # tools que já rodaram sem erro nesta pergunta
        lembrete_enviado = False

        for _ in range(config.MAX_ITERACOES_TOOLS):
            resposta = await self.llm.chat.completions.create(
                model=self.modelo, messages=mensagens, tools=schemas or None,
            )
            msg = resposta.choices[0].message
            if not msg.tool_calls:
                pendente = exigida and (exigida not in sucesso if isinstance(exigida, str) else not sucesso)
                if pendente and not lembrete_enviado:
                    # Modelos pequenos às vezes descrevem a ação em vez de executá-la.
                    lembrete_enviado = True
                    alvo = f"a tool {exigida}" if isinstance(exigida, str) else "as tools necessárias"
                    yield {"tipo": "aviso", "mensagem": f"O agente respondeu sem usar {alvo}; "
                                                         "pedindo que execute a ação."}
                    mensagens += [
                        {"role": "assistant", "content": msg.content or ""},
                        {"role": "user", "content": f"Não pergunte nada e não simule resultados: "
                                                    f"chame agora {alvo} para concluir o pedido."},
                    ]
                    continue
                yield {"tipo": "resposta", "agente": nome_agente, "conteudo": msg.content or ""}
                return

            mensagens.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                async for evento in self._executar_tool_call(tc, tools, mensagens):
                    if evento["tipo"] == "tool_resultado" and not evento["erro"]:
                        sucesso.add(evento["tool"])
                    yield evento

        # Limite atingido: pede a resposta final sem oferecer mais tools.
        yield {"tipo": "aviso", "mensagem": f"Limite de {config.MAX_ITERACOES_TOOLS} rodadas "
                                             "de ferramentas atingido; gerando resposta final."}
        mensagens.append({"role": "user", "content": (
            "Você atingiu o limite de chamadas de ferramentas. Responda agora, "
            "usando apenas as informações que já obteve."
        )})
        resposta = await self.llm.chat.completions.create(model=self.modelo, messages=mensagens)
        yield {"tipo": "resposta", "agente": nome_agente,
               "conteudo": resposta.choices[0].message.content or ""}

    async def _executar_tool_call(self, tc, tools_permitidas: list, mensagens: list):
        nome = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = None

        servidor = self.hub.tools.get(nome, {}).get("servidor")
        yield {"tipo": "tool_chamada", "tool": nome, "servidor": servidor,
               "args": args if args is not None else tc.function.arguments}

        if nome not in tools_permitidas:
            texto, erro = f"A tool '{nome}' não está disponível para este agente.", True
        elif args is None:
            texto, erro = "Argumentos inválidos (JSON malformado). Tente novamente.", True
        else:
            try:
                texto, erro = await self.hub.chamar(nome, args)
            except Exception as e:
                texto, erro = f"Erro ao executar a tool: {e}", True

        yield {"tipo": "tool_resultado", "tool": nome, "resultado": _preview(texto), "erro": erro}
        mensagens.append({"role": "tool", "tool_call_id": tc.id, "content": texto})
