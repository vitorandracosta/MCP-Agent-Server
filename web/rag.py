"""
API da aba "RAG": fontes (pastas e arquivos), envio de arquivos, o que foi
indexado, trechos de cada arquivo, busca de teste e opções do RAG.

Tudo que toca o índice vetorial passa pelo servidor MCP "rag" (o único
processo que abre o Chroma). Este módulo só edita a configuração
(dados/rag_config.json) e os arquivos enviados (dados/enviados/).
"""
import json
import os
import re
import string
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import config

MAX_ENVIO_BYTES = 50 * 1024 * 1024
MODELOS_SUGERIDOS = [
    {"nome": "all-MiniLM-L6-v2", "nota": "inglês, leve e rápido (padrão)"},
    {"nome": "paraphrase-multilingual-MiniLM-L12-v2", "nota": "multilíngue, bom para português"},
    {"nome": "intfloat/multilingual-e5-small", "nota": "multilíngue, mais preciso e um pouco mais lento"},
]


class NovaFonte(BaseModel):
    caminho: str


class Busca(BaseModel):
    pergunta: str
    k: int | None = None


class OpcoesRag(BaseModel):
    chunk_size: int
    chunk_overlap: int
    top_k: int
    extensoes: list[str]
    embedding_model: str


def _origem(p: Path, extras: list) -> str:
    if p == config.ENVIADOS_DIR:
        return "enviados"
    if str(p) in extras:
        return "tela"
    return "env" if os.environ.get("MCP_PASTAS") else "padrao"


def _fontes() -> list:
    config.sincronizar()
    extras = config.opcoes_rag()["fontes_extras"]
    return [{"caminho": str(p), "origem": _origem(p, extras), "existe": p.exists(),
             "tipo": "arquivo" if p.is_file() else "pasta"} for p in config.WATCHED_PATHS]


def _validar_fonte(caminho: str) -> Path:
    bruto = caminho.strip().strip('"').strip("'")
    if not bruto:
        raise HTTPException(400, "Informe o caminho de uma pasta ou arquivo.")
    p = Path(os.path.expanduser(bruto))
    if not p.is_absolute():
        raise HTTPException(400, "Use o caminho completo (ex.: C:\\Users\\voce\\Documentos\\Disciplinas).")
    p = p.resolve()
    if not p.exists():
        raise HTTPException(400, f"Não encontrei {p}.")
    if p.parent == p:
        raise HTTPException(400, "Não é possível adicionar a raiz de um disco inteiro: escolha uma pasta.")
    if p.is_file() and p.suffix.lower() not in config.EXTENSOES_CONHECIDAS:
        raise HTTPException(400, f"Formato {p.suffix or '(sem extensão)'} não suportado. "
                                 f"Suportados: {', '.join(sorted(config.EXTENSOES_CONHECIDAS))}.")
    for atual in config.WATCHED_PATHS:
        if p == atual or p.is_relative_to(atual):
            if config.excluido(p):
                raise HTTPException(400, "Este caminho está excluído do índice: inclua-o de novo na lista de excluídos.")
            raise HTTPException(400, f"Já está coberto pela fonte {atual}.")
    return p


def _fonte_que_contem(p: Path):
    return next((f for f in config.WATCHED_PATHS if p != f and p.is_relative_to(f)), None)


def _nome_livre(nome: str) -> Path:
    destino = config.ENVIADOS_DIR / nome
    n = 2
    while destino.exists():
        destino = config.ENVIADOS_DIR / f"{Path(nome).stem} ({n}){Path(nome).suffix}"
        n += 1
    return destino


def rotas(estado: dict) -> APIRouter:
    r = APIRouter(prefix="/api/rag")

    async def _resource(uri: str):
        try:
            return json.loads(await estado["hub"].ler_resource(uri, "rag"))
        except Exception as e:
            raise HTTPException(500, f"Falha ao ler {uri}: {e}")

    @r.get("")
    async def visao_geral():
        opcoes = config.opcoes_rag()
        return {
            "fontes": _fontes(),
            "fontes_removidas": opcoes["fontes_removidas"],
            "exclusoes": opcoes["exclusoes"],
            "opcoes": {k: v for k, v in opcoes.items() if k in config._PADROES_RAG},
            "padroes": config._PADROES_RAG,
            "extensoes_conhecidas": sorted(config.EXTENSOES_CONHECIDAS),
            "modelos_sugeridos": MODELOS_SUGERIDOS,
            "enviados_dir": str(config.ENVIADOS_DIR),
            "status": await _resource("rag://status"),
        }

    @r.get("/arquivos")
    async def arquivos():
        return await _resource("rag://arquivos")

    @r.get("/trechos")
    async def trechos(caminho: str):
        return await _resource("rag://arquivo/" + quote(caminho, safe=""))

    @r.post("/busca")
    async def busca(b: Busca):
        if not b.pergunta.strip():
            raise HTTPException(400, "Digite uma pergunta.")
        args = {"pergunta": b.pergunta}
        if b.k:
            args["k"] = max(1, min(b.k, 30))
        texto, erro = await estado["hub"].chamar("buscar_trechos", args)
        if erro:
            raise HTTPException(500, texto)
        return json.loads(texto)

    @r.post("/fontes")
    async def adicionar_fonte(f: NovaFonte):
        config.sincronizar()
        p = _validar_fonte(f.caminho)
        op = config.opcoes_rag()
        if str(p) in op["fontes_removidas"]:  # fonte do .env que tinha sido removida: só religa
            config.salvar_rag_config({"fontes_removidas": [e for e in op["fontes_removidas"] if e != str(p)]})
            return {"fontes": _fontes()}
        # Uma pasta nova que contém fontes adicionadas antes passa a substituí-las.
        extras = [e for e in op["fontes_extras"] if not Path(e).is_relative_to(p)]
        config.salvar_rag_config({"fontes_extras": extras + [str(p)]})
        return {"fontes": _fontes()}

    @r.delete("/fontes")
    async def remover_fonte(caminho: str):
        """Tira uma fonte inteira do RAG (e do alcance dos agentes). Nada é apagado do disco."""
        config.sincronizar()
        op = config.opcoes_rag()
        p = Path(caminho)
        if p == config.ENVIADOS_DIR:
            raise HTTPException(400, "Para tirar arquivos enviados, apague-os na lista do índice.")
        # Exclusões de dentro da fonte removida não servem mais para nada.
        alteracoes = {"exclusoes": [e for e in op["exclusoes"] if not Path(e).is_relative_to(p)]}
        if caminho in op["fontes_extras"]:
            alteracoes["fontes_extras"] = [e for e in op["fontes_extras"] if e != caminho]
        elif p in config.PASTAS_ENV:
            alteracoes["fontes_removidas"] = sorted(set(op["fontes_removidas"]) | {caminho})
        else:
            raise HTTPException(404, "Fonte não encontrada.")
        config.salvar_rag_config(alteracoes)
        return {"fontes": _fontes()}

    @r.post("/exclusoes")
    async def excluir_do_indice(f: NovaFonte):
        """Deixa de indexar uma subpasta ou arquivo que está dentro de uma fonte."""
        config.sincronizar()
        p = Path(f.caminho.strip().strip('"')).resolve()
        if p in config.WATCHED_PATHS:
            raise HTTPException(400, "Isto é uma fonte inteira: use Remover na lista de fontes.")
        if _fonte_que_contem(p) is None:
            raise HTTPException(400, "Só dá para excluir pastas ou arquivos que estão dentro de uma fonte.")
        if config.excluido(p):
            raise HTTPException(400, "Já está excluído.")
        # Excluir uma pasta torna redundantes as exclusões que estavam dentro dela.
        exclusoes = [e for e in config.opcoes_rag()["exclusoes"] if not Path(e).is_relative_to(p)]
        config.salvar_rag_config({"exclusoes": exclusoes + [str(p)]})
        return {"exclusoes": exclusoes + [str(p)]}

    @r.delete("/exclusoes")
    async def incluir_de_novo(caminho: str):
        exclusoes = config.opcoes_rag()["exclusoes"]
        if caminho not in exclusoes:
            raise HTTPException(404, "Este caminho não está na lista de excluídos.")
        config.salvar_rag_config({"exclusoes": [e for e in exclusoes if e != caminho]})
        return {"ok": True}

    @r.post("/enviar")
    async def enviar(nome: str, request: Request):
        nome = Path(nome).name.strip()
        if Path(nome).suffix.lower() not in config.EXTENSOES_CONHECIDAS:
            raise HTTPException(400, f"Formato não suportado: {nome}. "
                                     f"Suportados: {', '.join(sorted(config.EXTENSOES_CONHECIDAS))}.")
        conteudo = await request.body()
        if not conteudo:
            raise HTTPException(400, "Arquivo vazio.")
        if len(conteudo) > MAX_ENVIO_BYTES:
            raise HTTPException(400, "Arquivo maior que 50 MB.")
        config.ENVIADOS_DIR.mkdir(parents=True, exist_ok=True)
        destino = _nome_livre(nome)
        destino.write_bytes(conteudo)
        config.salvar_rag_config({})  # avisa os outros processos de que a pasta de enviados existe
        return {"caminho": str(destino)}

    @r.delete("/enviados")
    async def apagar_enviado(caminho: str):
        p = Path(caminho).resolve()
        if p.parent != config.ENVIADOS_DIR.resolve() or not p.is_file():
            raise HTTPException(400, "Só dá para apagar arquivos enviados pela tela.")
        p.unlink()
        return {"ok": True}

    @r.put("/opcoes")
    async def salvar_opcoes(o: OpcoesRag):
        extensoes = sorted({e.lower() if e.startswith(".") else "." + e.lower() for e in o.extensoes})
        if not 100 <= o.chunk_size <= 4000:
            raise HTTPException(400, "Tamanho do trecho deve ficar entre 100 e 4000 caracteres.")
        if not 0 <= o.chunk_overlap <= o.chunk_size // 2:
            raise HTTPException(400, "A sobreposição deve ficar entre 0 e metade do tamanho do trecho.")
        if not 1 <= o.top_k <= 20:
            raise HTTPException(400, "Trechos por busca (top-k) deve ficar entre 1 e 20.")
        if not extensoes or not set(extensoes) <= config.EXTENSOES_CONHECIDAS:
            raise HTTPException(400, "Escolha ao menos uma extensão entre as suportadas.")
        modelo = o.embedding_model.strip()
        if not re.fullmatch(r"[\w./-]{3,200}", modelo):
            raise HTTPException(400, "Nome de modelo de embedding inválido.")
        antes = config.opcoes_rag()
        config.salvar_rag_config({"chunk_size": o.chunk_size, "chunk_overlap": o.chunk_overlap,
                                  "top_k": o.top_k, "extensoes": extensoes, "embedding_model": modelo})
        refazer = (antes["chunk_size"], antes["chunk_overlap"], antes["embedding_model"]) != \
                  (o.chunk_size, o.chunk_overlap, modelo)
        return {"refazer_indice": refazer, "mudou_extensoes": sorted(antes["extensoes"]) != extensoes}

    @r.get("/navegar")
    async def navegar(caminho: str = ""):
        """Navegador de pastas para escolher uma fonte (o navegador web não informa caminhos locais)."""
        if not caminho:
            raizes = [Path.home()] + [Path(f"{l}:\\") for l in string.ascii_uppercase
                                       if os.name == "nt" and Path(f"{l}:\\").exists()]
            if os.name != "nt":
                raizes.append(Path("/"))
            return {"caminho": "", "pai": None,
                    "itens": [{"nome": str(p), "caminho": str(p), "tipo": "pasta"} for p in raizes]}
        p = Path(caminho).resolve()
        if not p.is_dir():
            raise HTTPException(400, "Pasta não encontrada.")
        itens = []
        try:
            for i in sorted(p.iterdir(), key=lambda i: (not i.is_dir(), i.name.lower())):
                if i.name.startswith((".", "~$", "$")):
                    continue
                if i.is_dir():
                    itens.append({"nome": i.name, "caminho": str(i), "tipo": "pasta"})
                elif i.suffix.lower() in config.EXTENSOES_CONHECIDAS:
                    itens.append({"nome": i.name, "caminho": str(i), "tipo": "arquivo"})
        except PermissionError:
            raise HTTPException(403, "Sem permissão para abrir esta pasta.")
        return {"caminho": str(p), "pai": str(p.parent) if p.parent != p else "", "itens": itens[:500]}

    return r
