"""
Configuração central do projeto (LLM, pastas, RAG, servidores MCP).

Valores pessoais (pastas do seu PC, chaves de API) NÃO ficam neste arquivo:
vão no arquivo .env na raiz (fora do git). Veja .env.example.
Variáveis de ambiente já definidas têm prioridade sobre o .env.

As opções do RAG editáveis pela tela (fontes extras, chunking, top-k,
extensões, modelo de embedding) ficam em dados/rag_config.json e
sobrepõem os valores abaixo. Como cada servidor MCP é um processo
separado, quem usa essas opções chama sincronizar() antes, que relê o
arquivo só quando ele muda.
"""
import json
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
PASTAS_ENV = [
    Path(os.path.expanduser(p.strip())).resolve() for p in _pastas_env
] or [RAIZ / "exemplos" / "documentos"]
WATCHED_PATHS = list(PASTAS_ENV)  # + fontes extras adicionadas pela tela (veja sincronizar)

# Única pasta onde o agente escritor pode criar arquivos.
OUTPUT_DIR = Path(os.path.expanduser(os.environ.get("MCP_SAIDAS", str(RAIZ / "saidas")))).resolve()

# Pastas que as tools de leitura aceitam (fontes + arquivos gerados).
PASTAS_LEITURA = WATCHED_PATHS + [OUTPUT_DIR]

# Dados da aplicação (histórico de conversas).
DADOS_DIR = Path(os.path.expanduser(os.environ.get("MCP_DADOS", str(RAIZ / "dados")))).resolve()
HISTORICO_DB = DADOS_DIR / "historico.sqlite3"
# Arquivos enviados pela tela (aba RAG): vira uma fonte do RAG automaticamente.
ENVIADOS_DIR = DADOS_DIR / "enviados"

# --- RAG --------------------------------------------------------------------
EXTENSOES_CONHECIDAS = {".txt", ".md", ".py", ".pdf", ".docx"}  # as que extrair_texto entende
SUPPORTED_EXTENSIONS = set(EXTENSOES_CONHECIDAS)
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
PERSIST_DIR = Path(os.path.expanduser(os.environ.get("MCP_INDICE", str(RAIZ / "rag_index")))).resolve()
COLLECTION_NAME = "documentos_locais"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TOP_K_DEFAULT = 4

RAG_CONFIG = DADOS_DIR / "rag_config.json"
# Valores do código/.env, usados quando o rag_config.json não define a opção.
_PADROES_RAG = {"chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP, "top_k": TOP_K_DEFAULT,
                "extensoes": sorted(SUPPORTED_EXTENSIONS), "embedding_model": EMBEDDING_MODEL}
_versao_rag = None  # mtime do rag_config.json já aplicado


def ler_rag_config() -> dict:
    try:
        return json.loads(RAG_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def opcoes_rag() -> dict:
    """
    Opções efetivas do RAG (rag_config.json por cima dos padrões) e as listas
    de caminhos editadas pela tela:
    - fontes_extras: pastas/arquivos adicionados como fonte;
    - fontes_removidas: fontes do .env desligadas pela tela (o .env não muda);
    - exclusoes: subpastas/arquivos de dentro de uma fonte que não são indexados.
    """
    salvo = ler_rag_config()
    return {**_PADROES_RAG, **{k: v for k, v in salvo.items() if k in _PADROES_RAG},
            **{k: salvo.get(k, []) for k in ("fontes_extras", "fontes_removidas", "exclusoes")}}


EXCLUSOES = []  # caminhos (Path) que o indexador ignora


def excluido(caminho: Path) -> bool:
    return any(caminho == e or caminho.is_relative_to(e) for e in EXCLUSOES)


def _aplicar_rag():
    global WATCHED_PATHS, PASTAS_LEITURA, CHUNK_SIZE, CHUNK_OVERLAP, TOP_K_DEFAULT
    global SUPPORTED_EXTENSIONS, EMBEDDING_MODEL, EXCLUSOES
    op = opcoes_rag()
    fontes = [p for p in PASTAS_ENV if str(p) not in op["fontes_removidas"]]
    EXCLUSOES = [Path(e) for e in op["exclusoes"]]
    for extra in [Path(f) for f in op["fontes_extras"]] + [ENVIADOS_DIR]:
        if extra not in fontes and (extra != ENVIADOS_DIR or extra.is_dir()):
            fontes.append(extra)
    WATCHED_PATHS = fontes
    PASTAS_LEITURA = WATCHED_PATHS + [OUTPUT_DIR]
    CHUNK_SIZE, CHUNK_OVERLAP, TOP_K_DEFAULT = op["chunk_size"], op["chunk_overlap"], op["top_k"]
    SUPPORTED_EXTENSIONS = set(op["extensoes"])
    EMBEDDING_MODEL = op["embedding_model"]


def sincronizar():
    """Reaplica o rag_config.json se ele mudou desde a última leitura (custa um stat)."""
    global _versao_rag
    try:
        versao = RAG_CONFIG.stat().st_mtime_ns
    except OSError:
        versao = None
    if versao != _versao_rag:
        _versao_rag = versao
        _aplicar_rag()


def salvar_rag_config(alteracoes: dict):
    """Grava opções no rag_config.json (as não informadas continuam como estão)."""
    RAG_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    RAG_CONFIG.write_text(json.dumps({**ler_rag_config(), **alteracoes}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    sincronizar()

# --- Servidores MCP ---------------------------------------------------------
# nome lógico -> módulo Python executado com "python -m <módulo>".
SERVIDORES_MCP = {
    "arquivos": "servers.arquivos_server",
    "rag": "servers.rag_server",
    "escrita": "servers.escrita_server",
    "sistema": "servers.sistema_server",
}

sincronizar()
