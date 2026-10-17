"""
Servidor MCP "arquivos": navegação e leitura de arquivos locais,
restrita às pastas de config.PASTAS_LEITURA.
"""
import unicodedata

from mcp.server.fastmcp import FastMCP

import config
from rag.extracao import extrair_texto
from servers.seguranca import resolver

mcp = FastMCP("arquivos")

NEGADO = "Acesso negado: caminho fora das pastas permitidas. Use listar_pastas_permitidas."
MAX_ITENS_LISTAGEM = 200


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _bases() -> list:
    """Pastas (ou arquivos soltos) permitidos, já com as fontes adicionadas pela tela."""
    config.sincronizar()
    return config.PASTAS_LEITURA


def _pastas_permitidas() -> str:
    return "\n".join(str(p) for p in _bases())


# --- Resources: contexto que a APLICAÇÃO lê e entrega ao agente -------------

@mcp.resource("arquivos://pastas-permitidas", name="Pastas permitidas", mime_type="text/plain")
def resource_pastas_permitidas() -> str:
    """Pastas raiz que as tools de leitura aceitam (fontes do RAG + saidas/)."""
    return _pastas_permitidas()


# --- Prompts: modelos de pedido que o USUÁRIO escolhe ------------------------

@mcp.prompt(name="resumir_pasta", description="Pede um resumo organizado de todos os arquivos de uma pasta.")
def prompt_resumir_pasta(pasta: str) -> str:
    return (f"Resuma o conteúdo da pasta '{pasta}'. Use visao_geral_pasta para ler os arquivos e "
            "organize o resumo em tópicos, indicando de qual arquivo veio cada ponto.")


# --- Tools: ações que o MODELO decide chamar ---------------------------------

@mcp.tool()
def listar_pastas_permitidas() -> str:
    """Lista as pastas raiz que podem ser lidas. Use primeiro quando não souber onde procurar."""
    return _pastas_permitidas()


@mcp.tool()
def listar_diretorio(caminho: str) -> str:
    """Lista arquivos e subpastas de um diretório (caminho absoluto ou relativo a uma pasta permitida)."""
    p = resolver(caminho, _bases())
    if p is None:
        return NEGADO
    if not p.is_dir():
        return "Diretório não encontrado."
    itens = sorted(p.iterdir(), key=lambda i: (not i.is_dir(), i.name.lower()))
    linhas = [f"{'[pasta] ' if i.is_dir() else ''}{i.name}" for i in itens[:MAX_ITENS_LISTAGEM]]
    if len(itens) > MAX_ITENS_LISTAGEM:
        linhas.append(f"... (+{len(itens) - MAX_ITENS_LISTAGEM} itens)")
    return f"{p}\n" + ("\n".join(linhas) if linhas else "(diretório vazio)")


@mcp.tool()
def buscar_arquivos(termo: str, pasta: str = "", max_resultados: int = 30) -> str:
    """Procura arquivos cujo NOME contém o termo (ex.: 'calculo', '.pdf'; ignora acentos e maiúsculas), em uma pasta ou em todas as permitidas."""
    if pasta:
        base = resolver(pasta, _bases())
        if base is None:
            return NEGADO
        bases = [base]
    else:
        bases = _bases()
    termo = _sem_acento(termo.strip())
    achados = []
    for base in bases:
        if base.is_file():  # fonte que é um arquivo solto
            if termo in _sem_acento(base.name):
                achados.append(str(base))
            continue
        if not base.is_dir():
            continue
        for item in base.rglob("*"):
            if item.is_file() and termo in _sem_acento(item.name):
                achados.append(str(item))
                if len(achados) >= max_resultados:
                    return "\n".join(achados) + "\n(limite de resultados atingido)"
    return "\n".join(achados) if achados else f"Nenhum arquivo com '{termo}' no nome."


@mcp.tool()
def ler_arquivo(caminho: str, max_chars: int = 6000) -> str:
    """Lê o texto de um arquivo (.txt, .md, .py, .pdf, .docx etc.) dentro das pastas permitidas."""
    p = resolver(caminho, _bases())
    if p is None:
        return NEGADO
    if not p.is_file():
        return "Arquivo não encontrado. Use buscar_arquivos para achar o caminho correto."
    texto = extrair_texto(p)
    if not texto.strip():
        return "Não foi possível extrair texto deste arquivo (vazio, imagem ou formato não suportado)."
    if len(texto) > max_chars:
        return texto[:max_chars] + f"\n\n[... truncado: {len(texto)} caracteres no total]"
    return texto


@mcp.tool()
def visao_geral_pasta(caminho: str, max_arquivos: int = 8, chars_por_arquivo: int = 600) -> str:
    """Mostra o início do texto de vários arquivos de uma pasta (incluindo subpastas) de uma vez. Útil para resumir uma pasta."""
    p = resolver(caminho, _bases())
    if p is None:
        return NEGADO
    if not p.is_dir():
        return "Diretório não encontrado."
    # Arquivos da própria pasta primeiro, depois os das subpastas.
    arquivos = sorted(
        (i for i in p.rglob("*") if i.is_file() and i.suffix.lower() in config.SUPPORTED_EXTENSIONS),
        key=lambda i: (len(i.relative_to(p).parts), str(i.relative_to(p)).lower()),
    )
    if not arquivos:
        return "Nenhum arquivo de texto suportado nesta pasta nem nas subpastas."
    partes = []
    for arq in arquivos[:max_arquivos]:
        trecho = " ".join(extrair_texto(arq)[:chars_por_arquivo].split())
        partes.append(f"### {arq.relative_to(p).as_posix()}\n{trecho or '(sem texto extraível)'}")
    if len(arquivos) > max_arquivos:
        partes.append(f"(+{len(arquivos) - max_arquivos} arquivos não mostrados)")
    return "\n\n".join(partes)


if __name__ == "__main__":
    mcp.run(transport="stdio")
