"""
Extração de texto de arquivos suportados. Usada tanto pelo indexador
quanto pela tool ler_arquivo (assim PDFs e .docx são lidos como texto,
e não como bytes crus).
"""
import sys
from pathlib import Path


def log(msg: str):
    # Servidores MCP via stdio usam o stdout como canal do protocolo:
    # qualquer print() lá corrompe a comunicação. Logs vão para o stderr.
    print(msg, file=sys.stderr, flush=True)


def extrair_texto(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext == ".docx":
            import docx
            document = docx.Document(str(path))
            return "\n".join(p.text for p in document.paragraphs)
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log(f"[rag] Falha ao ler {path}: {e}")
    return ""
