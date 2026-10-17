import asyncio
from types import SimpleNamespace

import pytest

from agents.registry import AGENTE_PADRAO
from agents.router import _achar_agente, _extrair_json, classificar_agente, interpretar_comando


class LLMFalso:
    """Imita AsyncOpenAI: devolve um texto fixo (ou levanta um erro)."""

    def __init__(self, resposta=None, erro=None):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.resposta, self.erro, self.chamadas = resposta, erro, []

    async def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        if self.erro:
            raise self.erro
        msg = SimpleNamespace(content=self.resposta, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.mark.parametrize("bruto, esperado", [
    ("pesquisador", "pesquisador"),
    ("Pesquisador.", "pesquisador"),
    ('"ESCRITOR"', "escritor"),
    ("O agente ideal é o resumidor", "resumidor"),
    ("nenhum", None),
])
def test_achar_agente_normaliza(bruto, esperado):
    assert _achar_agente(bruto) == esperado


def test_extrair_json_com_texto_em_volta():
    assert _extrair_json('Claro! {"agente": "sistema", "motivo": "GPU"} ok')["agente"] == "sistema"
    assert _extrair_json("sem json") == {}


def test_comandos():
    assert interpretar_comando("/agente escritor")[:2] == ("fixar", "escritor")
    assert interpretar_comando("/agente auto")[0] == "auto"
    assert interpretar_comando("/agente batata")[0] == "erro"
    assert interpretar_comando("olá")[0] is None


def test_classificar_usa_json_e_motivo():
    llm = LLMFalso('{"agente": "pesquisador", "motivo": "pergunta sobre o conteúdo"}')
    escolha = asyncio.run(classificar_agente("o que diz minha apostila?", llm, "m"))
    assert (escolha.agente, escolha.motivo, escolha.metodo) == ("pesquisador", "pergunta sobre o conteúdo", "llm")
    assert llm.chamadas[0]["response_format"] == {"type": "json_object"}
    assert llm.chamadas[0]["temperature"] == 0


def test_classificar_resposta_invalida_cai_no_padrao():
    escolha = asyncio.run(classificar_agente("oi", LLMFalso("não sei"), "m"))
    assert (escolha.agente, escolha.metodo) == (AGENTE_PADRAO, "padrao")


def test_classificar_llm_offline_cai_no_padrao():
    escolha = asyncio.run(classificar_agente("oi", LLMFalso(erro=ConnectionError("offline")), "m"))
    assert escolha.agente == AGENTE_PADRAO and "offline" in escolha.motivo


def test_classificar_inclui_historico_no_prompt():
    llm = LLMFalso('{"agente": "geral", "motivo": "x"}')
    historico = [{"role": "user", "content": "falei de cálculo antes"}]
    asyncio.run(classificar_agente("e agora?", llm, "m", historico))
    assert "falei de cálculo antes" in llm.chamadas[0]["messages"][0]["content"]
