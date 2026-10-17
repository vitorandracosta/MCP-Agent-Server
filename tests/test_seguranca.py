from servers.seguranca import dentro_de, resolver


def test_prefixo_igual_nao_passa(pastas):
    # Com startswith, ".../fonte_secreta" passaria como filho de ".../fonte".
    assert not dentro_de(pastas["fora"] / "senhas.txt", [pastas["fonte"]])


def test_caminho_filho_passa(pastas):
    assert dentro_de(pastas["fonte"] / "Redes" / "protocolo_tcp.md", [pastas["fonte"]])


def test_resolver_bloqueia_fuga_e_absoluto_externo(pastas):
    bases = [pastas["fonte"]]
    assert resolver("../fonte_secreta/senhas.txt", bases) is None
    assert resolver(str(pastas["fora"] / "senhas.txt"), bases) is None


def test_resolver_aceita_relativo_a_pasta_permitida(pastas):
    achado = resolver("Redes/protocolo_tcp.md", [pastas["fonte"]])
    assert achado == pastas["fonte"] / "Redes" / "protocolo_tcp.md"


def test_resolver_remove_aspas(pastas):
    assert resolver(f'"{pastas["fonte"]}"', [pastas["fonte"]]) == pastas["fonte"]
