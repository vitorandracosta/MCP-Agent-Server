"""
Guia "o que dá para fazer hoje": monta, a partir do estado REAL do sistema
(pastas monitoradas, arquivos indexados, LLM, GPU), exemplos de pedido que
funcionam agora.
"""
import json
import random
import re
import unicodedata
from pathlib import Path

import config
from agents.registry import AGENTS

PALAVRAS_IGNORADAS = {
    "assinado", "final", "versao", "copia", "arquivo", "documento", "relatorio",
    "atividade", "atividades", "trabalho", "parcial", "anexo", "lista", "download",
    # palavras comuns do português que não servem como termo de busca
    "quando", "sobre", "para", "entre", "depois", "antes", "outro", "outra", "nosso",
    "nossa", "segundo", "primeiro", "parte", "partes", "como", "onde", "porque",
}


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _arquivos_indexados() -> list:
    manifest = Path(config.PERSIST_DIR) / "manifest.json"
    if not manifest.exists():
        return []
    return [Path(p) for p in json.loads(manifest.read_text(encoding="utf-8"))]


def _base_de(caminho: Path):
    return next((b for b in config.WATCHED_PATHS if caminho.is_relative_to(b)), None)


def coletar_amostras() -> dict:
    """Nomes reais de pastas, arquivos e termos para preencher os exemplos."""
    config.sincronizar()
    arquivos = [p for p in _arquivos_indexados() if p.exists()]
    if not arquivos:  # índice ainda não construído: varre só o primeiro nível
        for base in config.WATCHED_PATHS:
            if base.is_dir():
                arquivos += [p for p in base.glob("*/*")
                             if p.suffix.lower() in config.SUPPORTED_EXTENSIONS][:200]

    pastas, nomes, termos = set(), set(), set()
    for arq in arquivos:
        base = _base_de(arq)
        if base is None:
            continue
        relativo = arq.relative_to(base)
        if len(relativo.parts) > 1:
            pastas.add(relativo.parts[0])
        if len(arq.name) <= 60 and not arq.name.startswith("~$"):
            nomes.add(arq.name)
        for palavra in re.split(r"[^A-Za-zÀ-ÿ]+", arq.stem):
            limpa = _sem_acento(palavra).lower()
            if len(limpa) >= 5 and limpa not in PALAVRAS_IGNORADAS:
                termos.add(limpa)

    assuntos = {re.sub(r"[_\-]+", " ", p).strip() for p in pastas}
    assuntos = {a for a in assuntos if a and not a.isdigit()}
    return {"pasta": sorted(pastas), "arquivo": sorted(nomes),
            "termo": sorted(termos), "assunto": sorted(assuntos)}


def _preencher(modelo: str, amostras: dict, sorteio: random.Random):
    campos = re.findall(r"\{(\w+)\}", modelo)
    valores = {}
    for campo in campos:
        opcoes = amostras.get(campo) or []
        if not opcoes:
            return None  # sem dado real para este exemplo: melhor não sugerir
        valores[campo] = sorteio.choice(opcoes)
    return modelo.format(**valores)


def montar_guia(status: dict, catalogo: dict, semente=None) -> dict:
    sorteio = random.Random(semente)
    amostras = coletar_amostras()
    agentes = []
    for nome, agente in AGENTS.items():
        exemplos = [e for e in (_preencher(m, amostras, sorteio) for m in agente.get("exemplos", [])) if e]
        agentes.append({
            "nome": nome,
            "descricao": agente["descricao"],
            "servidores": agente["servidores"],
            "resources": agente.get("resources") or [],
            "exemplos": exemplos,
        })

    return {
        "status": status,
        "agentes": agentes,
        "totais": {
            "servidores": len(catalogo),
            "tools": sum(len(c["tools"]) for c in catalogo.values()),
            "resources": sum(len(c["resources"]) + len(c["templates"]) for c in catalogo.values()),
            "prompts": sum(len(c["prompts"]) for c in catalogo.values()),
        },
    }
