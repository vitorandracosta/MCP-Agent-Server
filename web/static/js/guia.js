// Painel "O que dá para fazer agora": estado real do sistema + exemplos
// preenchidos com nomes reais das suas pastas + limitações honestas.
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

function blocoAgentes(agentes, aoEscolher, aoSortear) {
  const sortear = el("button", "pequeno", "↻ Outras sugestões");
  sortear.type = "button";
  sortear.addEventListener("click", aoSortear);
  const cards = agentes.map((a) => {
    const exemplos = a.exemplos.map((texto) => {
      const b = el("button", "exemplo", texto);
      b.type = "button";
      b.title = `Enviar (o roteador deve escolher: ${a.nome})`;
      b.addEventListener("click", () => aoEscolher(texto));
      return b;
    });
    return el("div", `guia-agente agente-borda-${a.nome}`, el("b", "", a.nome), el("p", "", a.descricao),
      ...(exemplos.length ? exemplos : [el("p", "aviso-texto", "Sem exemplos: não encontrei arquivos nas pastas monitoradas.")]));
  });
  return el("section", "guia-bloco",
    el("div", "guia-cabecalho", el("h3", "", "O que dá para fazer agora"), sortear),
    el("p", "guia-nota", "Os exemplos usam nomes reais das suas pastas. Ao clicar, o pedido passa pelo roteador: veja se ele escolhe o agente esperado."),
    ...cards);
}

function blocoLista(titulo, itens, classe) {
  return el("section", "guia-bloco", el("h3", "", titulo), el("ul", classe, ...itens.map((i) => el("li", "", i))));
}

export async function carregarGuia(container, { aoEscolher, semente } = {}) {
  container.replaceChildren(el("div", "carregando", "Verificando o sistema"));
  let dados;
  try {
    dados = await api("/api/guia" + (semente !== undefined ? `?semente=${semente}` : ""));
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
    carregarGuia(container, { aoEscolher });
  };
  const aoSortear = () => carregarGuia(container, { aoEscolher, semente: Math.floor(Math.random() * 1e6) });

  container.replaceChildren(
    blocoStatus(dados.status, dados.totais, aoReindexar),
    blocoAgentes(dados.agentes, aoEscolher, aoSortear),
    blocoLista("Ainda não faz", dados.limitacoes, "lista-limites"),
    blocoLista("Dicas", dados.dicas, "lista-dicas"),
  );
  return dados;
}
