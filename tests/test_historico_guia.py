import random

from web import guia
from web.historico import Historico


def eventos_turno(agente, resposta=None, erro=None, metodo="llm"):
    evs = [{"tipo": "roteamento", "agente": agente, "motivo": "m", "metodo": metodo}]
    evs.append({"tipo": "resposta", "conteudo": resposta} if resposta else {"tipo": "erro", "mensagem": erro})
    return evs


def test_historico_persiste_e_reconstroi(tmp_path):
    caminho = tmp_path / "h.sqlite3"
    h = Historico(caminho)
    h.registrar_turno("c1", "primeira pergunta", eventos_turno("explorador", "r1"), 120)
    h.registrar_turno("c1", "segunda", eventos_turno("pesquisador", erro="falhou"), 80)
    h.fechar()

    h = Historico(caminho)  # reabre: os dados sobrevivem
    [conversa] = h.listar()
    assert conversa["titulo"] == "primeira pergunta" and conversa["n_turnos"] == 2
    assert set(conversa["agentes"]) == {"explorador", "pesquisador"}

    detalhe = h.obter("c1")
    assert detalhe["turnos"][0]["eventos"][0]["tipo"] == "roteamento"
    assert detalhe["turnos"][1]["erro"] == "falhou"

    # Só turnos com resposta voltam como contexto para o LLM.
    assert h.mensagens_para_llm("c1") == [{"role": "user", "content": "primeira pergunta"},
                                          {"role": "assistant", "content": "r1"}]

    stats = h.estatisticas()
    assert stats["geral"]["turnos"] == 2 and stats["geral"]["erros"] == 1

    assert h.excluir("c1") and h.obter("c1") is None and h.listar() == []


def test_guia_preenche_exemplos_com_nomes_reais(pastas):
    amostras = guia.coletar_amostras()
    assert "Cálculo 1" in amostras["pasta"] and "protocolo_tcp.md" in amostras["arquivo"]
    exemplo = guia._preencher("Resuma a pasta {pasta}", amostras, random.Random(1))
    assert exemplo.replace("Resuma a pasta ", "") in amostras["pasta"]


def test_guia_nao_sugere_exemplo_sem_dados():
    assert guia._preencher("Resuma {pasta}", {"pasta": []}, random.Random(1)) is None
