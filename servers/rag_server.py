"""
Servidor MCP "rag": busca semântica nos documentos locais indexados.

Primitivas expostas:
- Tools: buscar_contexto_local, reindexar_documentos, status_indice e
  buscar_trechos (mesma busca, em JSON, para a aba RAG da tela).
- Resources: rag://status e rag://arquivos (estáticos), rag://busca/{pergunta}
  e rag://arquivo/{caminho} (templates), para clientes que leem contexto por
  URI em vez de chamar tools.
- Prompt: pergunta_com_fontes.

O índice (Chroma) só é aberto por este processo; a tela web administra o
RAG através destas primitivas, nunca abrindo o banco vetorial diretamente.
"""
import json
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP

from rag import indexer

mcp = FastMCP("rag")


def _buscar(pergunta: str, k: int = None) -> str:
    hits = indexer.query(pergunta, k=k)
    if not hits:
        if indexer.status()["total_chunks"] == 0:
            return "O índice está vazio. É preciso rodar reindexar_documentos antes de buscar."
        return "Nenhum contexto relevante encontrado nos documentos locais."
    partes = [f"[fonte: {h['fonte']} | similaridade={h['score']:.2f}]\n{h['texto']}" for h in hits]
    return "\n\n---\n\n".join(partes)


# --- Resources ---------------------------------------------------------------

@mcp.resource("rag://status", name="Status do índice", mime_type="application/json")
def resource_status() -> str:
    """Se o índice foi construído, quantos arquivos e trechos contém e qual modelo de embedding usa."""
    return json.dumps(indexer.status(), ensure_ascii=False)


@mcp.resource("rag://busca/{pergunta}", name="Busca no RAG", mime_type="text/plain")
def resource_busca_rag(pergunta: str) -> str:
    """Os trechos mais relevantes para a pergunta (a mesma busca da tool, exposta como Resource)."""
    # Numa URI a pergunta chega codificada (espaços viram %20 etc.).
    return _buscar(unquote(pergunta))


@mcp.resource("rag://arquivos", name="Arquivos indexados", mime_type="application/json")
def resource_arquivos() -> str:
    """Cada arquivo do índice com quantos trechos gerou, e o que mudou nas fontes desde a última indexação."""
    return json.dumps(indexer.inventario(), ensure_ascii=False)


@mcp.resource("rag://arquivo/{caminho}", name="Trechos de um arquivo", mime_type="application/json")
def resource_trechos(caminho: str) -> str:
    """Os trechos (chunks) que um arquivo gerou no índice, exatamente como o modelo os recebe."""
    return json.dumps(indexer.trechos_do_arquivo(unquote(caminho)), ensure_ascii=False)


# --- Prompts -----------------------------------------------------------------

@mcp.prompt(name="pergunta_com_fontes", description="Pergunta sobre os documentos exigindo citação das fontes.")
def prompt_pergunta_com_fontes(pergunta: str) -> str:
    return (f"Com base apenas nos meus documentos locais, responda: {pergunta}\n"
            "Cite o caminho do arquivo de cada informação. Se os documentos não "
            "responderem, diga isso claramente.")


# --- Tools -------------------------------------------------------------------

@mcp.tool()
def buscar_contexto_local(pergunta: str, k: int | None = None) -> str:
    """Busca nos documentos locais indexados (RAG) os trechos mais relevantes para a pergunta, com a fonte de cada um."""
    return _buscar(pergunta, k)


@mcp.tool()
def buscar_trechos(pergunta: str, k: int | None = None) -> str:
    """Busca semântica que devolve JSON (trecho, fonte, número do trecho e similaridade). Usada pela aba RAG da tela."""
    return json.dumps(indexer.query(pergunta, k=k), ensure_ascii=False)


@mcp.tool()
def reindexar_documentos(forcar: bool = False) -> str:
    """Reprocessa as pastas monitoradas e atualiza o índice vetorial (incremental; forcar=true refaz tudo)."""
    return json.dumps(indexer.build_index(force=forcar), ensure_ascii=False)


@mcp.tool()
def status_indice() -> str:
    """Informa se o índice RAG já foi construído, quantos arquivos e trechos ele contém."""
    return resource_status()


if __name__ == "__main__":
    mcp.run(transport="stdio")
