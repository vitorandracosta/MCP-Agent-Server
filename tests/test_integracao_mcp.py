"""
Integração real: sobe os 4 servidores MCP como subprocessos (stdio) e
conversa com eles pelo protocolo. Não precisa de LLM.

O teste marcado com "llm" roda o pipeline completo com o Ollama e só
executa com a variável de ambiente RODAR_LLM=1.
"""
import asyncio
import os

import pytest

from orquestrador import HubMCP, Orquestrador


def com_hub(fn):
    async def rodar():
        hub = HubMCP()
        await hub.iniciar()
        try:
            return await fn(hub)
        finally:
            await hub.fechar()
    return asyncio.run(rodar())


def test_servidores_expoem_tools_resources_e_prompts():
    async def verificar(hub):
        assert set(hub.sessoes) == {"arquivos", "rag", "escrita", "sistema"}
        cat = hub.catalogo
        assert "buscar_contexto_local" in [t["nome"] for t in cat["rag"]["tools"]]
        assert "rag://busca/{pergunta}" in [t["uri"] for t in cat["rag"]["templates"]]
        assert "relatorio" in [p["nome"] for p in cat["escrita"]["prompts"]]
        assert (await hub.ler_resource("arquivos://pastas-permitidas")).strip()
        prompt = await hub.obter_prompt("escrita", "relatorio", {"assunto": "MCP"})
        assert "MCP" in prompt
        texto, erro = await hub.chamar("criar_arquivo", {"nome": "../fuga.txt", "conteudo": "x"})
        assert erro and "saidas" in texto
    com_hub(verificar)


@pytest.mark.llm
@pytest.mark.skipif(os.environ.get("RODAR_LLM") != "1", reason="defina RODAR_LLM=1 com o Ollama rodando")
def test_pipeline_completo_com_llm():
    async def verificar(hub):
        orq = Orquestrador(hub)
        eventos = [e async for e in orq.executar("Quanta VRAM livre tem minha GPU agora?", [])]
        rot = next(e for e in eventos if e["tipo"] == "roteamento")
        assert rot["agente"] == "sistema"
        assert any(e["tipo"] == "tool_chamada" for e in eventos)
        assert eventos[-1]["tipo"] == "resposta"
    com_hub(verificar)
