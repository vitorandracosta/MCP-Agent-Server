"""
Configuração central do projeto (LLM, pastas, RAG, servidores MCP).

Valores pessoais (pastas do seu PC, chaves de API) NÃO ficam neste arquivo:
vão no arquivo .env na raiz (fora do git). Veja .env.example.
Variáveis de ambiente já definidas têm prioridade sobre o .env.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _carregar_env(caminho: Path):
    """Leitor mínimo de .env (CHAVE=valor por linha, # para comentários)."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env(RAIZ / ".env")

# --- LLM (qualquer endpoint compatível com a API da OpenAI) -----------------
# Padrão: Ollama local. Para o Qwen na nuvem (DashScope), veja .env.example.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "ollama")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b")

# Limite de rodadas de tool-calling por pergunta (evita loop infinito).
MAX_ITERACOES_TOOLS = 6
# Quantas mensagens anteriores da conversa são enviadas ao modelo.
MAX_HISTORICO = 10

# --- Pastas -----------------------------------------------------------------
# Pastas que viram contexto (RAG) e que os agentes podem ler. Defina no .env:
#   MCP_PASTAS=C:\Users\voce\Documentos\Disciplinas;~/Downloads
# Sem configuração, usa os documentos de exemplo do repositório.
_pastas_env = [p for p in os.environ.get("MCP_PASTAS", "").split(";") if p.strip()]
WATCHED_PATHS = [
    Path(os.path.expanduser(p.strip())).resolve() for p in _pastas_env
] or [RAIZ / "exemplos" / "documentos"]

# Única pasta onde o agente escritor pode criar arquivos.
OUTPUT_DIR = Path(os.path.expanduser(os.environ.get("MCP_SAIDAS", str(RAIZ / "saidas")))).resolve()

# Pastas que as tools de leitura aceitam (fontes + arquivos gerados).
PASTAS_LEITURA = WATCHED_PATHS + [OUTPUT_DIR]

# Dados da aplicação (histórico de conversas).
DADOS_DIR = Path(os.path.expanduser(os.environ.get("MCP_DADOS", str(RAIZ / "dados")))).resolve()
HISTORICO_DB = DADOS_DIR / "historico.sqlite3"

# --- RAG --------------------------------------------------------------------
SUPPORTED_EXTENSIONS = {".txt", ".md", ".py", ".pdf", ".docx"}
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
PERSIST_DIR = Path(os.path.expanduser(os.environ.get("MCP_INDICE", str(RAIZ / "rag_index")))).resolve()
COLLECTION_NAME = "documentos_locais"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TOP_K_DEFAULT = 4

# --- Servidores MCP ---------------------------------------------------------
# nome lógico -> módulo Python executado com "python -m <módulo>".
SERVIDORES_MCP = {
    "arquivos": "servers.arquivos_server",
    "rag": "servers.rag_server",
    "escrita": "servers.escrita_server",
    "sistema": "servers.sistema_server",
}
