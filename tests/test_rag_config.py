"""Opções do RAG editáveis pela tela (dados/rag_config.json) e o que o indexador expõe para a aba RAG."""
import pytest

import config
from rag import indexer

GLOBAIS = ["WATCHED_PATHS", "PASTAS_LEITURA", "CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K_DEFAULT",
           "SUPPORTED_EXTENSIONS", "EMBEDDING_MODEL", "EXCLUSOES", "_versao_rag"]


@pytest.fixture
def rag_config(pastas, tmp_path, monkeypatch):
    """rag_config.json numa pasta temporária; os globais do config voltam ao normal no fim."""
    for nome in GLOBAIS:
        monkeypatch.setattr(config, nome, getattr(config, nome))
    monkeypatch.setattr(config, "PASTAS_ENV", [pastas["fonte"]])
    monkeypatch.setattr(config, "RAG_CONFIG", tmp_path / "dados" / "rag_config.json")
    monkeypatch.setattr(config, "ENVIADOS_DIR", tmp_path / "dados" / "enviados")
    monkeypatch.setattr(config, "_versao_rag", "forçar releitura")
    monkeypatch.setattr(indexer, "_client", None)
    monkeypatch.setattr(indexer, "_collection", None)
    config.sincronizar()
    return pastas


def test_fontes_extras_e_opcoes_valem_depois_de_salvar(rag_config, tmp_path):
    extra = tmp_path / "extra.md"
    extra.write_text("conteúdo extra", encoding="utf-8")
    assert extra not in config.WATCHED_PATHS

    config.salvar_rag_config({"fontes_extras": [str(extra)], "chunk_size": 300, "top_k": 7})
    assert config.WATCHED_PATHS == [rag_config["fonte"], extra]
    assert extra in config.PASTAS_LEITURA and rag_config["saidas"] in config.PASTAS_LEITURA
    assert (config.CHUNK_SIZE, config.TOP_K_DEFAULT) == (300, 7)
    assert config.CHUNK_OVERLAP == config._PADROES_RAG["chunk_overlap"]  # não informado: padrão


def test_pasta_de_enviados_so_vira_fonte_quando_existe(rag_config):
    assert config.ENVIADOS_DIR not in config.WATCHED_PATHS
    config.ENVIADOS_DIR.mkdir(parents=True)
    config.salvar_rag_config({})
    assert config.ENVIADOS_DIR in config.WATCHED_PATHS


def test_arquivo_solto_como_fonte_e_inventario(rag_config, tmp_path):
    solto = tmp_path / "solto.txt"
    solto.write_text("Redes neurais aprendem pesos por retropropagação.", encoding="utf-8")
    vazio = rag_config["fonte"] / "Redes" / "vazio.md"
    vazio.write_text("", encoding="utf-8")
    config.salvar_rag_config({"fontes_extras": [str(solto)]})

    inv = indexer.inventario()
    assert str(solto) in inv["novos"] and inv["arquivos"] == []

    indexer.build_index()
    inv = indexer.inventario()
    trechos = {a["caminho"]: a["trechos"] for a in inv["arquivos"]}
    assert trechos[str(solto)] == 1 and trechos[str(vazio)] == 0  # vazio: "sem texto"
    assert not inv["novos"] and not inv["modificados"]
    assert indexer.trechos_do_arquivo(str(solto))[0]["texto"].startswith("Redes neurais")

    config.salvar_rag_config({"fontes_extras": []})
    assert str(solto) in indexer.inventario()["apagados"]


def test_excluir_subpasta_e_remover_fonte_do_env(rag_config):
    fonte = rag_config["fonte"]
    indexer.build_index()
    config.salvar_rag_config({"exclusoes": [str(fonte / "Cálculo 1")]})
    assert config.excluido(fonte / "Cálculo 1" / "lista_derivadas.txt")
    assert indexer.build_index()["removidos"] == 2
    assert {a["caminho"] for a in indexer.inventario()["arquivos"]} == {str(fonte / "Redes" / "protocolo_tcp.md")}

    # Fonte do .env removida pela tela: sai do índice e do alcance dos agentes.
    config.salvar_rag_config({"fontes_removidas": [str(fonte)]})
    assert fonte not in config.WATCHED_PATHS and fonte not in config.PASTAS_LEITURA
    assert indexer.build_index()["removidos"] == 1 and indexer.inventario()["arquivos"] == []


def test_mudar_chunking_refaz_o_indice(rag_config):
    indexer.build_index()
    assert indexer.build_index()["atualizados"] == 0

    config.salvar_rag_config({"chunk_size": 100, "chunk_overlap": 10})
    resumo = indexer.build_index()
    assert resumo["atualizados"] == 3 and resumo["sem_alteracao"] == 0
