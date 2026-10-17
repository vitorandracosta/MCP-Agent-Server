"""
Avaliação do roteador: acurácia da escolha de agente num conjunto rotulado.

Uso (a partir da raiz do projeto, com o LLM rodando):
    python -m avaliacao.avaliar_roteador            # 1 rodada
    python -m avaliacao.avaliar_roteador --rodadas 3

Gera um relatório no terminal (acurácia geral, por agente e matriz de
confusão) e salva o detalhe em avaliacao/resultados/roteador_<data>.json.
"""
import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

import config
from agents.registry import AGENTS
from agents.router import classificar_agente

PASTA = Path(__file__).resolve().parent


async def avaliar(rodadas: int) -> dict:
    casos = json.loads((PASTA / "casos_roteador.json").read_text(encoding="utf-8"))
    llm = AsyncOpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resultados = []
    for rodada in range(1, rodadas + 1):
        for caso in casos:
            inicio = time.perf_counter()
            escolha = await classificar_agente(caso["mensagem"], llm, config.LLM_MODEL)
            resultados.append({
                "rodada": rodada, **caso, "escolhido": escolha.agente, "metodo": escolha.metodo,
                "motivo": escolha.motivo, "acertou": escolha.agente == caso["esperado"],
                "ms": round((time.perf_counter() - inicio) * 1000),
            })
            marca = "✓" if escolha.agente == caso["esperado"] else "✗"
            print(f"{marca} [{caso['esperado']:>11} → {escolha.agente:<11}] {caso['mensagem']}")
    return {"modelo": config.LLM_MODEL, "data": datetime.now().isoformat(timespec="seconds"),
            "rodadas": rodadas, "resultados": resultados}


def relatorio(dados: dict):
    res = dados["resultados"]
    acertos = sum(r["acertou"] for r in res)
    print(f"\nModelo: {dados['modelo']} · {len(res)} classificações · {dados['rodadas']} rodada(s)")
    print(f"Acurácia geral: {acertos}/{len(res)} = {acertos / len(res):.1%}")
    print(f"Fallback para o agente padrão: {sum(r['metodo'] == 'padrao' for r in res)}")
    print(f"Tempo médio por classificação: {sum(r['ms'] for r in res) / len(res) / 1000:.2f} s\n")

    por_agente = defaultdict(list)
    for r in res:
        por_agente[r["esperado"]].append(r["acertou"])
    print("Acurácia por agente esperado:")
    for nome in AGENTS:
        if por_agente[nome]:
            v = por_agente[nome]
            print(f"  {nome:<12} {sum(v)}/{len(v)} = {sum(v) / len(v):.0%}")

    confusao = Counter((r["esperado"], r["escolhido"]) for r in res)
    nomes = list(AGENTS)
    print("\nMatriz de confusão (linhas = esperado, colunas = escolhido):")
    print(" " * 13 + "".join(f"{n[:6]:>8}" for n in nomes))
    for esperado in nomes:
        print(f"  {esperado:<11}" + "".join(f"{confusao[(esperado, e)] or '·':>8}" for e in nomes))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rodadas", type=int, default=1, help="quantas vezes repetir cada caso")
    args = parser.parse_args()

    dados = asyncio.run(avaliar(args.rodadas))
    relatorio(dados)
    saida = PASTA / "resultados" / f"roteador_{datetime.now():%Y%m%d_%H%M%S}.json"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalhes salvos em {saida.relative_to(config.RAIZ)}")


if __name__ == "__main__":
    main()
