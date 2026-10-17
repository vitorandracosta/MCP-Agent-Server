"""
Decide qual agente atende cada mensagem e POR QUÊ.

1. Se o usuário escolheu um agente (comando '/agente nome' no terminal ou
   seletor na tela), essa escolha vale e o LLM não é consultado.
2. Senão, o LLM classifica a mensagem entre os agentes, devolvendo JSON
   com o nome e o motivo. A resposta é normalizada (acentos, aspas,
   pontuação, maiúsculas) para tolerar as variações de modelos pequenos.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, asdict

from .registry import AGENTS, AGENTE_PADRAO

COMANDO = "/agente"
MODO_AUTOMATICO = "auto"


@dataclass
class Escolha:
    agente: str
    motivo: str
    metodo: str  # "manual", "llm" ou "padrao"

    def to_dict(self):
        return asdict(self)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z_ ]", " ", sem_acento.lower()).strip()


def _achar_agente(texto: str):
    """Encontra um nome de agente válido dentro de um texto qualquer."""
    normalizado = _normalizar(texto)
    if normalizado in AGENTS:
        return normalizado
    posicoes = [(m.start(), nome) for nome in AGENTS
                for m in [re.search(rf"\b{nome}\b", normalizado)] if m]
    return min(posicoes)[1] if posicoes else None


def interpretar_comando(mensagem: str):
    """
    Trata '/agente <nome>' e '/agente auto'. Retorna (acao, agente, aviso), onde
    acao é None (não é comando), "fixar", "auto" ou "erro".
    """
    texto = mensagem.strip()
    if not texto.lower().startswith(COMANDO):
        return None, None, ""
    argumento = texto[len(COMANDO):].strip()
    if _normalizar(argumento) == MODO_AUTOMATICO:
        return "auto", None, "Modo automático reativado."
    nome = _achar_agente(argumento) if argumento else None
    if nome is None:
        return "erro", None, f"Agente desconhecido. Opções: {', '.join(AGENTS)} ou auto."
    return "fixar", nome, f"Agente fixado: {nome} (use '/agente auto' para voltar ao automático)."


def _extrair_json(texto: str) -> dict:
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        trecho = re.search(r"\{.*\}", texto, re.S)
        if trecho:
            try:
                return json.loads(trecho.group(0))
            except json.JSONDecodeError:
                pass
    return {}


async def classificar_agente(mensagem: str, llm_client, model: str, historico=None) -> Escolha:
    """Usa o LLM para escolher o agente mais adequado e justificar a escolha."""
    opcoes = "\n".join(f"- {nome}: {info['descricao']}" for nome, info in AGENTS.items())

    contexto = ""
    if historico:
        ultimas = historico[-4:]
        contexto = "Contexto recente da conversa:\n" + "\n".join(
            f"{m['role']}: {m['content'][:300]}" for m in ultimas
        ) + "\n\n"

    prompt = (
        "Você é o roteador de um sistema multiagente. Escolha o agente mais adequado "
        "para atender a mensagem do usuário.\n\n"
        f"Agentes disponíveis:\n{opcoes}\n\n"
        f"{contexto}"
        f"Mensagem do usuário: {mensagem}\n\n"
        'Responda SOMENTE com um JSON no formato {"agente": "<nome>", "motivo": "<uma frase '
        'curta em português explicando por que esse agente é o adequado>"}.'
    )
    try:
        resposta = await llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        bruto = resposta.choices[0].message.content or ""
    except Exception as e:
        return Escolha(AGENTE_PADRAO, f"Falha ao consultar o roteador ({e}); usando o agente padrão.", "padrao")

    dados = _extrair_json(bruto)
    nome = _achar_agente(str(dados.get("agente", ""))) or _achar_agente(bruto)
    if nome is None:
        return Escolha(AGENTE_PADRAO, "O roteador não indicou um agente válido; usando o agente padrão.", "padrao")
    motivo = str(dados.get("motivo") or "").strip() or "O roteador não informou o motivo."
    return Escolha(nome, motivo, "llm")
