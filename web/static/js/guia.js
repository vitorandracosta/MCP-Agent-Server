// Painel lateral: estado real do sistema + o que cada agente faz, com exemplos
// preenchidos com nomes reais das suas pastas.
import { el, api } from "./util.js";

function linhaStatus(ok, titulo, detalhe, extra) {
  return el("div", "status-linha " + (ok ? "ok" : "falha"),
    el("span", "status-icone", ok ? "●" : "○"),
    el("div", "", el("b", "", titulo), el("div", "status-detalhe", detalhe), extra));
}

function blocoStatus(s, totais, aoReindexar) {
  const indice = s.indice || {};
  const botao = el("button", "pequeno", indice.indice_construido ? "Atualizar índice" : "Construir índice");
  botao.type = "button";
  botao.addEventListener("click", () => aoReindexar(botao));

  const pastasOk = s.pastas.every((p) => p.existe);
  const pastas = el("ul", "status-pastas", ...s.pastas.map((p) => el("li", p.existe ? "" : "falha", (p.existe ? "✓ " : "✗ ") + p.caminho)));

  return el("section", "guia-bloco",
    el("h3", "", "Estado agora"),
    linhaStatus(s.llm.ok, "LLM " + s.llm.modelo, s.llm.detalhe),
    linhaStatus(indice.indice_construido && indice.total_chunks > 0, "Índice RAG",
      indice.indice_construido
        ? `${indice.arquivos_no_manifest} arquivos · ${indice.total_chunks} trechos`
        : "ainda não construído: o pesquisador não terá o que buscar", botao),
    linhaStatus(!/não encontrado|Falha|indisponível/.test(s.gpu), "GPU", s.gpu),
    linhaStatus(pastasOk, "Pastas monitoradas", pastasOk ? `${s.pastas.length} pasta(s) acessível(is)` : "há pastas inexistentes (veja o .env)", pastas),
    linhaStatus(true, "Servidores MCP", `${totais.servidores} servidores · ${totais.tools} tools · ${totais.resources} resources · ${totais.prompts} prompts`),
  );
}

// Só informativo: descreve cada agente e o tipo de pedido que ele atende.
function blocoAgentes(agentes) {
  const cards = agentes.map((a) => el("div", `guia-agente agente-borda-${a.nome}`,
    el("b", "", a.nome), el("p", "", a.descricao),
    a.exemplos.length
      ? el("ul", "guia-exemplos", ...a.exemplos.map((texto) => el("li", "", texto)))
      : el("p", "aviso-texto", "Sem exemplos: não encontrei arquivos nas pastas monitoradas.")));
  return el("section", "guia-bloco",
    el("h3", "", "O que dá para fazer agora"),
    el("p", "guia-nota", "Cada agente e exemplos de pedidos que ele atende, com nomes reais das suas pastas. O agente que estiver trabalhando fica destacado."),
    ...cards);
}

export async function carregarGuia(container) {
  container.replaceChildren(el("div", "carregando", "Verificando o sistema"));
  let dados;
  try {
    dados = await api("/api/guia");
  } catch (e) {
    container.replaceChildren(el("div", "caixa-erro", "Falha ao carregar o guia: " + e.message));
    return null;
  }

  const aoReindexar = async (botao) => {
    botao.disabled = true;
    botao.textContent = "Indexando… (pode levar minutos)";
    try {
      await api("/api/reindexar", { method: "POST" });
    } catch (e) {
      alert("Falha ao indexar: " + e.message);
    }
    carregarGuia(container);
  };

  container.replaceChildren(
    blocoStatus(dados.status, dados.totais, aoReindexar),
    blocoAgentes(dados.agentes),
  );
  return dados;
}
