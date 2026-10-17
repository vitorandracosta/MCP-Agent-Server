"""RAG de ponta a ponta numa pasta temporária (usa o modelo de embedding real)."""
import pytest

import config
from rag import indexer


@pytest.fixture
def indice(pastas, monkeypatch):
    # Cada teste começa com cliente/coleção novos apontando para a pasta temporária.
    monkeypatch.setattr(indexer, "_client", None)
    monkeypatch.setattr(indexer, "_collection", None)
    return pastas


def test_chunk_com_sobreposicao(monkeypatch):
    monkeypatch.setattr(config, "CHUNK_SIZE", 10)
    monkeypatch.setattr(config, "CHUNK_OVERLAP", 4)
    pedacos = indexer._chunk("abcdefghijklmnopqrst")
    assert pedacos[0] == "abcdefghij" and pedacos[1].startswith("ghij")
    assert pedacos[-1].endswith("t")


def test_indexacao_incremental_e_remocao(indice):
    primeiro = indexer.build_index()
    assert primeiro["atualizados"] == 3 and primeiro["removidos"] == 0

    segundo = indexer.build_index()
    assert segundo["atualizados"] == 0 and segundo["sem_alteracao"] == 3

    (indice["fonte"] / "Redes" / "protocolo_tcp.md").unlink()
    terceiro = indexer.build_index()
    assert terceiro["removidos"] == 1
    fontes = {h["fonte"] for h in indexer.query("TCP pacotes", k=10)}
    assert not any("protocolo_tcp" in f for f in fontes)


def test_busca_retorna_fonte_e_similaridade_de_cosseno(indice):
    indexer.build_index()
    hits = indexer.query("taxa de variação de uma função", k=2)
    assert hits and "lista_derivadas" in hits[0]["fonte"]
    assert all(-1 <= h["score"] <= 1 for h in hits)


def test_indice_vazio_retorna_lista_vazia(indice):
    assert indexer.query("qualquer coisa") == []
    assert indexer.status()["indice_construido"] is False
