// Aba "Histórico": conversas salvas (SQLite), detalhe de cada turno e estatísticas.
import { $, el, api, formatarData, formatarDuracao, emitir, ouvir } from "./util.js";
import { Turno } from "./turno.js";

let conversas = [];
let selecionada = null;

function itemConversa(c) {
  const item = el("button", "item-conversa" + (c.id === selecionada ? " ativo" : ""),
    el("b", "", c.titulo),
    el("span", "item-meta", `${formatarData(c.atualizada_em)} · ${c.n_turnos} turno(s)`),
    el("span", "item-agentes", ...c.agentes.map((a) => el("span", `chip agente-${a}`, a))));
  item.type = "button";
  item.addEventListener("click", () => abrir(c.id));
  return item;
}

function renderLista() {
  const termo = $("#busca-historico").value.trim().toLowerCase();
  const filtradas = conversas.filter((c) => !termo || c.titulo.toLowerCase().includes(termo));
  $("#lista-conversas").replaceChildren(
    ...(filtradas.length ? filtradas.map(itemConversa)
      : [el("p", "vazio-texto", conversas.length ? "Nenhuma conversa encontrada." : "Nenhuma conversa ainda. Faça um pedido na aba Conversa.")]));
}

async function renderEstatisticas() {
  const { geral, por_agente } = await api("/api/estatisticas");
  const detalhe = $("#detalhe-conversa");
  if (!geral.turnos) {
    detalhe.replaceChildren(el("p", "vazio-texto", "Ainda não há conversas salvas. Cada pedido feito na aba Conversa fica registrado aqui com todos os passos."));
    return;
  }
  const cartao = (rotulo, valor) => el("div", "metrica", el("span", "metrica-valor", valor), el("span", "metrica-rotulo", rotulo));
  const linhas = por_agente.map((a) => el("tr", "",
    el("td", "", el("span", `chip agente-${a.agente}`, a.agente || "—")),
    el("td", "num", a.turnos), el("td", "num", a.pelo_roteador), el("td", "num", a.manual),
    el("td", "num", a.fallback), el("td", "num", a.erros), el("td", "num", formatarDuracao(a.duracao_media_ms))));
  detalhe.replaceChildren(
    el("h2", "", "Estatísticas de uso"),
    el("p", "vazio-texto", "Selecione uma conversa à esquerda para ver os turnos. Estes números ajudam a avaliar o roteador e os agentes."),
    el("div", "metricas",
      cartao("conversas", geral.conversas), cartao("turnos", geral.turnos),
      cartao("tempo médio", formatarDuracao(geral.duracao_media_ms)), cartao("com erro", geral.erros)),
    el("div", "tabela-rolagem", el("table", "tabela",
      el("thead", "", el("tr", "", ...["Agente", "Turnos", "Pelo roteador", "Manual", "Fallback", "Erros", "Tempo médio"].map((t, i) => el("th", i ? "num" : "", t)))),
      el("tbody", "", ...linhas))));
}

async function abrir(id) {
  selecionada = id;
  renderLista();
  history.replaceState(null, "", `#historico/${id}`);  // link direto para esta conversa
  let c;
  try { c = await api(`/api/conversas/${id}`); }
  catch (e) { $("#detalhe-conversa").replaceChildren(el("div", "caixa-erro", e.message)); return; }
  const continuar = el("button", "primario", "Continuar esta conversa");
  continuar.type = "button";
  continuar.addEventListener("click", () => emitir("continuar-conversa", id));
  const excluir = el("button", "perigo", "Excluir");
  excluir.type = "button";
  excluir.addEventListener("click", async () => {
    if (!confirm("Excluir esta conversa do histórico?")) return;
    await api(`/api/conversas/${id}`, { method: "DELETE" });
    selecionada = null;
    history.replaceState(null, "", "#historico");
    await atualizar();
  });

  const turnos = el("div", "mensagens historico-turnos");
  for (const t of c.turnos) {
    turnos.append(el("div", "turno-data", formatarData(t.criado_em)));
    const turno = new Turno(turnos, t.pergunta, { aoVivo: false });
    t.eventos.forEach((ev) => turno.aplicar(ev));
    turno.finalizar(t.duracao_ms);
  }
  $("#detalhe-conversa").replaceChildren(
    el("div", "detalhe-cabecalho",
      el("div", "", el("h2", "", c.titulo),
        el("span", "item-meta", `Criada ${formatarData(c.criada_em)} · ${c.turnos.length} turno(s)`)),
      el("div", "acoes", continuar, excluir)),
    turnos);
}

async function atualizar() {
  conversas = await api("/api/conversas");
  renderLista();
  if (selecionada && conversas.some((c) => c.id === selecionada)) await abrir(selecionada);
  else await renderEstatisticas();
}

export function iniciarHistorico() {
  $("#busca-historico").addEventListener("input", renderLista);
  ouvir("historico-alterado", atualizar);
  ouvir("aba-aberta", ({ aba, parametro }) => {
    if (aba !== "historico") return;
    if (parametro) selecionada = parametro;
    atualizar();
  });
}
