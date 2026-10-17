"""
Allowlist de caminhos compartilhada pelos servidores MCP.

Nenhuma tool lê ou escreve fora das pastas permitidas. Sem essa checagem,
texto vindo do usuário ou de um documento indexado poderia induzir o
modelo a acessar arquivos fora do escopo (prompt injection via documento).
"""
import os
from pathlib import Path
from typing import Iterable, Optional


def dentro_de(path: Path, bases: Iterable[Path]) -> bool:
    # is_relative_to compara componentes do caminho, então
    # "...\Disciplinas_outra" NÃO passa como filho de "...\Disciplinas"
    # (o que acontecia com a comparação por startswith).
    return any(path == base or path.is_relative_to(base) for base in bases)


def resolver(caminho: str, bases: list) -> Optional[Path]:
    """
    Converte o caminho pedido pelo modelo num Path absoluto permitido, ou
    None se cair fora das pastas permitidas. Caminhos relativos são
    procurados dentro de cada pasta permitida (modelos pequenos costumam
    mandar só "pasta/arquivo.pdf").
    """
    bruto = Path(os.path.expanduser(caminho.strip().strip('"').strip("'")))
    candidatos = [bruto] if bruto.is_absolute() else [base / bruto for base in bases]
    escolhido = next((c for c in candidatos if c.exists()), candidatos[0])
    try:
        resolvido = escolhido.resolve()
    except OSError:
        return None
    return resolvido if dentro_de(resolvido, bases) else None
