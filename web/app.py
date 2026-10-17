"""
API e tela web do sistema multiagente.

Rode a partir da raiz do projeto com:  python -m web.app
e abra http://127.0.0.1:8000 (outra porta: variável MCP_PORTA).

(Não use "uvicorn --reload": no Windows o modo reload troca o event loop
por um que não suporta subprocessos, e os servidores MCP não sobem.)
"""
import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from agents.registry import AGENTS
from orquestrador import HubMCP, Orquestrador
from web.guia import montar_guia
from web.historico import Historico

PASTA_STATIC = config.RAIZ / "web" / "static"

estado = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub = HubMCP()
    await hub.iniciar()
    estado["hub"] = hub
    estado["orquestrador"] = Orquestrador(hub)
    estado["historico"] = Historico(config.HISTORICO_DB)
    try:
        yield
    finally:
        estado["historico"].fechar()
        await hub.fechar()


app = FastAPI(title="Rede MCP multiagente", lifespan=lifespan)
config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/saidas", StaticFiles(directory=str(config.OUTPUT_DIR)), name="saidas")
app.mount("/static", StaticFiles(directory=str(PASTA_STATIC)), name="static")


class Pergunta(BaseModel):
    mensagem: str
    conversa_id: str | None = None
    agente: str = "auto"  # "auto" ou o nome de um agente


class LeituraResource(BaseModel):
    uri: str
    servidor: str | None = None


class PedidoPrompt(BaseModel):
    servidor: str
    nome: str
    argumentos: dict = {}


@app.get("/")
async def index():
    return FileResponse(PASTA_STATIC / "index.html")


# --- Informações do sistema ---------------------------------------------------

async def _status_llm() -> dict:
    info = {"modelo": config.LLM_MODEL, "url": config.LLM_BASE_URL, "ok": False}
    try:
        pagina = await asyncio.wait_for(estado["orquestrador"].llm.models.list(), timeout=4)
        ids = [m.id for m in pagina.data]
        info["ok"] = config.LLM_MODEL in ids
        info["detalhe"] = "online" if info["ok"] else f"modelo não encontrado (disponíveis: {', '.join(ids[:5])})"
    except Exception as e:
        info["detalhe"] = f"sem conexão ({type(e).__name__})"
    return info


async def _ler_resource_seguro(uri: str) -> str:
    try:
        return await estado["hub"].ler_resource(uri)
    except Exception as e:
        return f"indisponível ({e})"


@app.get("/api/status")
async def status():
    hub = estado["hub"]
    llm, indice, gpu = await asyncio.gather(
        _status_llm(), _ler_resource_seguro("rag://status"), _ler_resource_seguro("sistema://gpu"),
    )
    try:
        indice = json.loads(indice)
    except json.JSONDecodeError:
        indice = {"indice_construido": False, "erro": indice}
    return {
        "llm": llm,
        "indice": indice,
        "gpu": gpu,
        "pastas": [{"caminho": str(p), "existe": p.is_dir()} for p in config.WATCHED_PATHS],
        "saidas": str(config.OUTPUT_DIR),
        "servidores": list(hub.sessoes),
    }


@app.get("/api/guia")
async def guia(semente: int | None = None):
    return montar_guia(await status(), estado["hub"].catalogo, semente)


@app.get("/api/agentes")
async def listar_agentes():
    hub = estado["hub"]
    return {
        "modelo": config.LLM_MODEL,
        "agentes": [
            {"nome": nome, "descricao": a["descricao"], "servidores": a["servidores"],
             "tools": hub.tools_do_agente(nome), "resources": a.get("resources") or [],
             "exige_tool": a.get("exige_tool")}
            for nome, a in AGENTS.items()
        ],
    }


# --- Primitivas MCP -----------------------------------------------------------

@app.get("/api/mcp")
async def catalogo_mcp():
    return {"servidores": [{"nome": nome, "modulo": config.SERVIDORES_MCP[nome], **cat}
                           for nome, cat in estado["hub"].catalogo.items()]}


@app.post("/api/mcp/resource")
async def ler_resource(pedido: LeituraResource):
    try:
        conteudo = await estado["hub"].ler_resource(pedido.uri, pedido.servidor)
    except Exception as e:
        raise HTTPException(400, f"Falha ao ler {pedido.uri}: {e}")
    return {"uri": pedido.uri, "conteudo": conteudo}


@app.post("/api/mcp/prompt")
async def obter_prompt(pedido: PedidoPrompt):
    if pedido.servidor not in estado["hub"].sessoes:
        raise HTTPException(404, f"Servidor desconhecido: {pedido.servidor}")
    try:
        texto = await estado["hub"].obter_prompt(pedido.servidor, pedido.nome, pedido.argumentos)
    except Exception as e:
        raise HTTPException(400, f"Falha ao gerar o prompt: {e}")
    return {"texto": texto}


@app.post("/api/reindexar")
async def reindexar(forcar: bool = False):
    texto, erro = await estado["hub"].chamar("reindexar_documentos", {"forcar": forcar})
    if erro:
        raise HTTPException(500, texto)
    return json.loads(texto)


# --- Conversas ------------------------------------------------------------------

@app.get("/api/conversas")
async def listar_conversas():
    return estado["historico"].listar()


@app.get("/api/estatisticas")
async def estatisticas():
    return estado["historico"].estatisticas()


@app.get("/api/conversas/{conversa_id}")
async def obter_conversa(conversa_id: str):
    conversa = estado["historico"].obter(conversa_id)
    if conversa is None:
        raise HTTPException(404, "Conversa não encontrada.")
    return conversa


@app.delete("/api/conversas/{conversa_id}")
async def excluir_conversa(conversa_id: str):
    if not estado["historico"].excluir(conversa_id):
        raise HTTPException(404, "Conversa não encontrada.")
    return {"ok": True}


@app.post("/api/perguntar")
async def perguntar(p: Pergunta):
    if not p.mensagem.strip():
        raise HTTPException(400, "Mensagem vazia.")
    if p.agente != "auto" and p.agente not in AGENTS:
        raise HTTPException(400, f"Agente desconhecido: {p.agente}")

    historico = estado["historico"]
    conversa_id = p.conversa_id or uuid.uuid4().hex
    mensagens_anteriores = historico.mensagens_para_llm(conversa_id)
    agente_forcado = None if p.agente == "auto" else p.agente

    async def eventos():
        # NDJSON: um evento JSON por linha, enviado assim que acontece.
        registrados = []
        inicio = time.perf_counter()
        yield json.dumps({"tipo": "inicio", "conversa_id": conversa_id}) + "\n"
        try:
            async for evento in estado["orquestrador"].executar(p.mensagem, mensagens_anteriores,
                                                                agente_forcado):
                registrados.append(evento)
                yield json.dumps(evento, ensure_ascii=False) + "\n"
        finally:
            # Salva mesmo se o navegador fechar no meio (o turno fica sem resposta).
            if not any(e["tipo"] in ("resposta", "erro") for e in registrados):
                registrados.append({"tipo": "erro", "mensagem": "Execução interrompida."})
            historico.registrar_turno(conversa_id, p.mensagem, registrados,
                                      round((time.perf_counter() - inicio) * 1000))
        yield json.dumps({"tipo": "fim"}) + "\n"

    return StreamingResponse(eventos(), media_type="application/x-ndjson")


if __name__ == "__main__":
    porta = int(os.environ.get("MCP_PORTA", "8000"))
    print(f"Abra http://127.0.0.1:{porta}")
    uvicorn.run(app, host="127.0.0.1", port=porta)
