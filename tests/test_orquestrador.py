"""
Lógica do orquestrador com um LLM e um hub MCP falsos: valida roteamento,
leitura de resources, loop de tools, exige_tool e limite de iterações
sem precisar do Ollama.
"""
import asyncio
import json
from types import SimpleNamespace

import config
from orquestrador import Orquestrador


def msg_texto(texto):
    return SimpleNamespace(content=texto, tool_calls=None)


def msg_tool(nome, args, id_="c1"):
    chamada = SimpleNamespace(id=id_, function=SimpleNamespace(name=nome, arguments=json.dumps(args)))
    return SimpleNamespace(content="", tool_calls=[chamada])


class LLMRoteirizado:
    """Devolve as mensagens do roteiro em ordem, registrando cada pedido."""

    def __init__(self, roteiro):
        self.roteiro, self.pedidos = list(roteiro), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.pedidos.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.roteiro.pop(0))])


class HubFalso:
    def __init__(self):
        self.tools = {n: {"servidor": s, "schema": {"type": "function", "function": {"name": n}}}
                      for n, s in [("buscar_arquivos", "arquivos"), ("ler_arquivo", "arquivos"),
                                   ("criar_arquivo", "escrita"), ("buscar_contexto_local", "rag")]}
        self.resources = {"arquivos://pastas-permitidas": "arquivos", "saidas://lista": "escrita",
                          "rag://status": "rag"}
        self.chamadas = []

    def tools_do_agente(self, nome):
        from agents.registry import AGENTS
        a = AGENTS[nome]
        return [t for t, i in self.tools.items()
                if i["servidor"] in a["servidores"] and (a.get("tools") is None or t in a["tools"])]

    async def chamar(self, nome, args):
        self.chamadas.append((nome, args))
        return f"resultado de {nome}", False

    async def ler_resource(self, uri, servidor=None):
        return f"conteúdo de {uri}"


def rodar(orq, mensagem, agente=None):
    async def coletar():
        return [e async for e in orq.executar(mensagem, [], agente)]
    return asyncio.run(coletar())


def orquestrador(roteiro):
    orq = Orquestrador(HubFalso())
    orq.llm = LLMRoteirizado(roteiro)
    return orq


def test_fluxo_completo_roteador_resource_tool_resposta():
    orq = orquestrador([
        msg_texto('{"agente": "explorador", "motivo": "procurar arquivo"}'),
        msg_tool("buscar_arquivos", {"termo": "tcp"}),
        msg_texto("Achei protocolo_tcp.md"),
    ])
    eventos = rodar(orq, "onde está o arquivo de tcp?")
    tipos = [e["tipo"] for e in eventos]
    assert tipos == ["roteamento", "resource_lido", "tool_chamada", "tool_resultado", "resposta"]
    assert eventos[0]["motivo"] == "procurar arquivo"
    assert eventos[-1]["conteudo"] == "Achei protocolo_tcp.md"
    assert all("t_ms" in e for e in eventos)
    # O resource do agente entra no system prompt.
    assert "conteúdo de arquivos://pastas-permitidas" in orq.llm.pedidos[1]["messages"][0]["content"]
    # O agente só recebe as tools do servidor dele.
    nomes = {t["function"]["name"] for t in orq.llm.pedidos[1]["tools"]}
    assert nomes == {"buscar_arquivos", "ler_arquivo"}


def test_exige_tool_envia_lembrete():
    orq = orquestrador([
        msg_texto("Vou criar o arquivo, ok?"),               # escritor tenta só conversar
        msg_tool("criar_arquivo", {"nome": "a.md", "conteudo": "x"}),
        msg_texto("Arquivo a.md criado."),
    ])
    eventos = rodar(orq, "crie a.md", agente="escritor")
    assert [e["tipo"] for e in eventos].count("aviso") == 1
    assert orq.hub.chamadas == [("criar_arquivo", {"nome": "a.md", "conteudo": "x"})]
    assert eventos[-1]["tipo"] == "resposta"


def test_tool_de_outro_agente_e_recusada():
    orq = orquestrador([msg_tool("criar_arquivo", {"nome": "x"}), msg_texto("ok")])
    eventos = rodar(orq, "liste a pasta", agente="explorador")
    resultado = next(e for e in eventos if e["tipo"] == "tool_resultado")
    assert resultado["erro"] and "não está disponível" in resultado["resultado"]
    assert orq.hub.chamadas == []


def test_limite_de_iteracoes(monkeypatch):
    monkeypatch.setattr(config, "MAX_ITERACOES_TOOLS", 2)
    orq = orquestrador([
        msg_tool("buscar_arquivos", {"termo": "a"}, "c1"),
        msg_tool("buscar_arquivos", {"termo": "b"}, "c2"),
        msg_texto("resposta forçada"),
    ])
    eventos = rodar(orq, "procure", agente="explorador")
    assert any(e["tipo"] == "aviso" and "Limite" in e["mensagem"] for e in eventos)
    assert eventos[-1]["tipo"] == "resposta" and eventos[-1]["conteudo"] == "resposta forçada"
    assert "tools" not in orq.llm.pedidos[-1]  # a última chamada não oferece tools


def test_erro_do_llm_vira_evento_de_erro():
    orq = Orquestrador(HubFalso())

    async def falha(**kwargs):
        raise ConnectionError("Ollama offline")
    orq.llm = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=falha)))
    eventos = rodar(orq, "oi", agente="geral")
    assert eventos[-1]["tipo"] == "erro" and "Ollama offline" in eventos[-1]["mensagem"]
