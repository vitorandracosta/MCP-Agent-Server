import pytest

import config


@pytest.fixture
def pastas(tmp_path, monkeypatch):
    """Pastas isoladas: uma "monitorada" com arquivos de exemplo e uma de saídas."""
    fonte = tmp_path / "fonte"
    (fonte / "Cálculo 1").mkdir(parents=True)
    (fonte / "Cálculo 1" / "lista_derivadas.txt").write_text(
        "Derivadas medem a taxa de variação instantânea de uma função.", encoding="utf-8")
    (fonte / "Cálculo 1" / "Resumo de CÁLCULO.md").write_text(
        "Limites, derivadas e integrais.", encoding="utf-8")
    (fonte / "Redes").mkdir()
    (fonte / "Redes" / "protocolo_tcp.md").write_text(
        "# TCP\nO TCP garante entrega ordenada e confiável de pacotes.", encoding="utf-8")
    saidas = tmp_path / "saidas"
    saidas.mkdir()
    fora = tmp_path / "fonte_secreta"  # mesmo prefixo de nome, mas fora da allowlist
    fora.mkdir()
    (fora / "senhas.txt").write_text("segredo", encoding="utf-8")

    monkeypatch.setattr(config, "WATCHED_PATHS", [fonte.resolve()])
    monkeypatch.setattr(config, "OUTPUT_DIR", saidas.resolve())
    monkeypatch.setattr(config, "PASTAS_LEITURA", [fonte.resolve(), saidas.resolve()])
    monkeypatch.setattr(config, "PERSIST_DIR", tmp_path / "indice")
    return {"fonte": fonte.resolve(), "saidas": saidas.resolve(), "fora": fora.resolve()}
