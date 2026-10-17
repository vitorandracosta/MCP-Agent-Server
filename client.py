"""
Cliente de terminal: mesmo orquestrador da tela web, em modo REPL.

Comandos:
  /agente <nome>  fixa um agente até você trocar
  /agente auto    volta à escolha automática
  Enter vazio     sai
"""
import asyncio

from agents.registry import AGENTS
from agents.router import interpretar_comando
from orquestrador import HubMCP, Orquestrador


def mostrar(evento: dict):
    tipo = evento["tipo"]
    if tipo == "roteamento":
        print(f"→ Agente: {evento['agente']} ({evento['metodo']}) — {evento['motivo']}")
    elif tipo == "resource_lido":
        print(f"  📚 [{evento['servidor']}] resource {evento['uri']}")
    elif tipo == "tool_chamada":
        print(f"  🔧 [{evento['servidor']}] {evento['tool']}({evento['args']})")
    elif tipo == "tool_resultado" and evento["erro"]:
        print(f"  ⚠️  {evento['resultado'][:200]}")
    elif tipo == "aviso":
        print(f"  ⚠️  {evento['mensagem']}")
    elif tipo == "erro":
        print(f"❌ {evento['mensagem']}")
    elif tipo == "resposta":
        print(f"Assistente: {evento['conteudo']}\n")


async def main():
    hub = HubMCP()
    await hub.iniciar()
    orquestrador = Orquestrador(hub)
    try:
        print("🟢 Conectado aos servidores MCP:", ", ".join(hub.sessoes))
        print("Agentes:", ", ".join(AGENTS))
        print("Comandos: '/agente <nome>', '/agente auto'. Enter vazio para sair.\n")

        historico = []
        agente_fixado = None

        while True:
            pergunta = (await asyncio.to_thread(input, "Você: ")).strip()
            if not pergunta:
                break

            acao, agente, aviso = interpretar_comando(pergunta)
            if acao:
                if acao in ("fixar", "auto"):
                    agente_fixado = agente
                print(f"→ {aviso}\n")
                continue

            resposta = None
            async for evento in orquestrador.executar(pergunta, historico, agente_fixado):
                mostrar(evento)
                if evento["tipo"] == "resposta":
                    resposta = evento["conteudo"]

            if resposta is not None:
                historico += [{"role": "user", "content": pergunta},
                              {"role": "assistant", "content": resposta}]
    finally:
        await hub.fechar()


if __name__ == "__main__":
    asyncio.run(main())
