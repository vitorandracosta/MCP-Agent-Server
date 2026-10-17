"""
Servidor MCP "rag": busca semântica nos documentos locais indexados.

Primitivas expostas:
- Tools: buscar_contexto_local, reindexar_documentos, status_indice.
- Resources: rag://status (estático) e rag://busca/{pergunta} (template),
  para clientes que leem contexto por URI em vez de chamar tools.
- Prompt: pergunta_com_fontes.
"""
import json
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP

from rag import indexer

mcp = FastMCP("rag")


def _buscar(pergunta: str, k: int) -> str:
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
    return _buscar(unquote(pergunta), k=4)


# --- Prompts -----------------------------------------------------------------

@mcp.prompt(name="pergunta_com_fontes", description="Pergunta sobre os documentos exigindo citação das fontes.")
def prompt_pergunta_com_fontes(pergunta: str) -> str:
    return (f"Com base apenas nos meus documentos locais, responda: {pergunta}\n"
            "Cite o caminho do arquivo de cada informação. Se os documentos não "
            "responderem, diga isso claramente.")


# --- Tools -------------------------------------------------------------------

@mcp.tool()
def buscar_contexto_local(pergunta: str, k: int = 4) -> str:
    """Busca nos documentos locais indexados (RAG) os trechos mais relevantes para a pergunta, com a fonte de cada um."""
    return _buscar(pergunta, k)


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
