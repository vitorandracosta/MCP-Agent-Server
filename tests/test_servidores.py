"""Tools dos servidores chamadas como funções Python (sem subir o MCP)."""
import pytest

from servers import arquivos_server as arq
from servers import escrita_server as esc


def test_buscar_arquivos_ignora_acento_e_maiuscula(pastas):
    assert "Resumo de CÁLCULO.md" in arq.buscar_arquivos("calculo")
    assert "lista_derivadas.txt" in arq.buscar_arquivos("DERIVADAS")
    assert "Nenhum arquivo" in arq.buscar_arquivos("inexistente")


def test_ler_arquivo_fora_da_allowlist_e_negado(pastas):
    assert arq.ler_arquivo(str(pastas["fora"] / "senhas.txt")).startswith("Acesso negado")


def test_ler_arquivo_relativo(pastas):
    assert "entrega ordenada" in arq.ler_arquivo("Redes/protocolo_tcp.md")


def test_ler_arquivo_trunca(pastas):
    texto = arq.ler_arquivo("Redes/protocolo_tcp.md", max_chars=10)
    assert "truncado" in texto


def test_visao_geral_pasta(pastas):
    texto = arq.visao_geral_pasta("Cálculo 1")
    assert "### lista_derivadas.txt" in texto and "taxa de variação" in texto


def test_visao_geral_pasta_inclui_subpastas(pastas):
    # A raiz só tem subpastas: antes isso devolvia "nenhum arquivo".
    texto = arq.visao_geral_pasta(str(pastas["fonte"]))
    assert "### Redes/protocolo_tcp.md" in texto and "### Cálculo 1/lista_derivadas.txt" in texto


def test_criar_arquivo_e_extensao_padrao(pastas):
    assert "Arquivo criado" in esc.criar_arquivo("notas", "conteúdo")
    assert (pastas["saidas"] / "notas.md").read_text(encoding="utf-8") == "conteúdo"


def test_criar_arquivo_nao_sobrescreve(pastas):
    esc.criar_arquivo("a.txt", "1")
    with pytest.raises(ValueError, match="Já existe"):
        esc.criar_arquivo("a.txt", "2")
    esc.criar_arquivo("a.txt", "2", sobrescrever=True)
    assert (pastas["saidas"] / "a.txt").read_text(encoding="utf-8") == "2"


@pytest.mark.parametrize("nome", ["../fuga.txt", "..\\..\\fuga.txt", "C:/Windows/x.txt", "/etc/x.txt"])
def test_criar_arquivo_bloqueia_fuga_da_pasta(pastas, nome):
    with pytest.raises(ValueError, match="dentro da pasta saidas"):
        esc.criar_arquivo(nome, "x")


def test_criar_arquivo_bloqueia_extensao(pastas):
    with pytest.raises(ValueError, match="Extensão não permitida"):
        esc.criar_arquivo("virus.exe", "x")


def test_criar_docx(pastas):
    esc.criar_arquivo("relatorio.docx", "# Título\nParágrafo")
    import docx
    doc = docx.Document(str(pastas["saidas"] / "relatorio.docx"))
    assert [p.text for p in doc.paragraphs] == ["Título", "Parágrafo"]


def test_resource_lista_ignora_ocultos(pastas):
    (pastas["saidas"] / ".gitkeep").write_text("")
    assert esc.resource_arquivos_gerados() == "(nenhum arquivo gerado ainda)"
