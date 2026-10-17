"""
Servidor MCP "sistema": informações do sistema e da GPU.
"""
import platform
import shutil
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("sistema")


def _info_sistema() -> str:
    return (
        f"SO: {platform.system()} {platform.release()} | "
        f"Python: {platform.python_version()} | "
        f"Máquina: {platform.machine()} | "
        f"Processador: {platform.processor() or 'desconhecido'}"
    )


def _uso_gpu() -> str:
    if not shutil.which("nvidia-smi"):
        return "nvidia-smi não encontrado (sem GPU NVIDIA ou driver não instalado)."
    campos = "name,memory.total,memory.used,memory.free,utilization.gpu"
    try:
        saida = subprocess.run(
            ["nvidia-smi", f"--query-gpu={campos}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError) as e:
        return f"Falha ao consultar nvidia-smi: {e}"
    linhas = []
    for linha in saida.splitlines():
        nome, total, usada, livre, util = [c.strip() for c in linha.split(",")]
        linhas.append(f"{nome}: VRAM {usada}/{total} MB usada ({livre} MB livre), utilização {util}%")
    return "\n".join(linhas)


@mcp.resource("sistema://info", name="Informações do sistema", mime_type="text/plain")
def resource_info_sistema() -> str:
    """Sistema operacional, versão do Python e arquitetura da máquina."""
    return _info_sistema()


@mcp.resource("sistema://gpu", name="Estado da GPU", mime_type="text/plain")
def resource_gpu() -> str:
    """Leitura atual da GPU NVIDIA via nvidia-smi."""
    return _uso_gpu()


@mcp.tool()
def info_sistema() -> str:
    """Retorna informações básicas do sistema operacional, Python e hardware."""
    return _info_sistema()


@mcp.tool()
def uso_gpu() -> str:
    """Lê da GPU NVIDIA (via nvidia-smi) o nome, a VRAM total/usada/livre e a utilização atual."""
    return _uso_gpu()


@mcp.tool()
def calcular_vram_disponivel(vram_total_mb: int, vram_usada_mb: int) -> str:
    """Calcula a VRAM livre a partir de valores informados (para valores reais, use uso_gpu)."""
    livre = vram_total_mb - vram_usada_mb
    pct = (livre / vram_total_mb) * 100 if vram_total_mb else 0
    return f"VRAM livre: {livre} MB ({pct:.1f}%)"


if __name__ == "__main__":
    mcp.run(transport="stdio")
