// Aba "Histórico": conversas salvas (SQLite), organizadas em pastas, detalhe
// de cada turno e estatísticas.
import { $, el, api, formatarData, formatarDuracao, emitir, ouvir } from "./util.js";
import { Turno } from "./turno.js";

let conversas = [];
let selecionada = null;
const pastasFechadas = new Set();

const nomesPastas = () => [...new Set(conversas.map((c) => c.pasta).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR"));

async function editarConversa(id, dados) {
  try { await api(`/api/conversas/${id}`, { method: "PATCH", body: dados }); }
  catch (e) { alert("Falha ao salvar: " + e.message); }
  if (dados.titulo) emitir("conversa-renomeada", { id, titulo: dados.titulo.trim() });
  await atualizar();
}

function botaoPequeno(texto, titulo, acao) {
  const b = el("button", "icone", texto);
  b.type = "button";
  b.title = titulo;
  b.setAttribute("aria-label", titulo);
  b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); acao(); });
  return b;
}

function grupoPasta(nome, itens) {
  const grupo = el("details", "pasta-grupo");
  grupo.open = !pastasFechadas.has(nome);
  grupo.addEventListener("toggle", () => { grupo.open ? pastasFechadas.delete(nome) : pastasFechadas.add(nome); });
  const renomear = botaoPequeno("✎", "Renomear pasta", async () => {
    const novo = prompt("Novo nome da pasta:", nome)?.trim();
    if (!novo || novo === nome) return;
    await api(`/api/pastas/${encodeURIComponent(nome)}`, { method: "PATCH", body: { nome: novo } });
    await atualizar();
  });
  const desfazer = botaoPequeno("✕", "Desfazer pasta (as conversas não são apagadas)", async () => {
    if (!confirm(`Desfazer a pasta "${nome}"? As conversas continuam no histórico, só ficam sem pasta.`)) return;
    await api(`/api/pastas/${encodeURIComponent(nome)}`, { method: "DELETE" });
    await atualizar();
  });
  grupo.append(
    el("summary", "pasta-cab", el("span", "pasta-nome", "📁 " + nome), el("span", "pasta-contagem", itens.length), renomear, desfazer),
    ...itens.map(itemConversa));
  return grupo;
}

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
  const filtradas = conversas.filter((c) => !termo || c.titulo.toLowerCase().includes(termo)
    || (c.pasta || "").toLowerCase().includes(termo));
  if (!filtradas.length) {
    $("#lista-conversas").replaceChildren(el("p", "vazio-texto",
      conversas.length ? "Nenhuma conversa encontrada." : "Nenhuma conversa ainda. Faça um pedido na aba Conversa."));
    return;
  }
  const grupos = nomesPastas()
    .map((p) => [p, filtradas.filter((c) => c.pasta === p)])
    .filter(([, itens]) => itens.length)
    .map(([p, itens]) => grupoPasta(p, itens));
  const soltas = filtradas.filter((c) => !c.pasta);
  $("#lista-conversas").replaceChildren(
    ...grupos,
    ...(grupos.length && soltas.length ? [el("div", "pasta-rotulo", "Sem pasta")] : []),
    ...soltas.map(itemConversa));
}

function seletorPasta(c) {
  const NOVA = "\u0000nova";
  const select = el("select", "",
    el("option", "", "— Sem pasta —"),
    ...nomesPastas().map((p) => el("option", "", p)),
    el("option", "", "+ Nova pasta…"));
  [...select.options].forEach((o, i) => { o.value = i === 0 ? "" : i === select.options.length - 1 ? NOVA : o.textContent; });
  select.value = c.pasta || "";
  select.addEventListener("change", async () => {
    let pasta = select.value;
    if (pasta === NOVA) {
      pasta = prompt("Nome da nova pasta:")?.trim();
      if (!pasta) { select.value = c.pasta || ""; return; }
    }
    await editarConversa(c.id, { pasta });
  });
  return el("label", "seletor", "Pasta", select);
}

function tituloEditavel(c) {
  const titulo = el("h2", "", c.titulo);
  const renomear = botaoPequeno("✎", "Renomear conversa", () => {
    const campo = el("input", "campo-titulo");
    campo.value = c.titulo;
    let feito = false;
    const concluir = async (salvar) => {
      if (feito) return;
      feito = true;
      const novo = campo.value.trim();
      if (salvar && novo && novo !== c.titulo) await editarConversa(c.id, { titulo: novo });
      else linha.replaceChildren(titulo, renomear);
    };
    campo.addEventListener("keydown", (e) => {
      if (e.key === "Enter") concluir(true);
      else if (e.key === "Escape") concluir(false);
    });
    campo.addEventListener("blur", () => concluir(true));
    linha.replaceChildren(campo);
    campo.focus();
    campo.select();
  });
  const linha = el("div", "titulo-linha", titulo, renomear);
  return linha;
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
      el("div", "", tituloEditavel(c),
        el("span", "item-meta", `Criada ${formatarData(c.criada_em)} · ${c.turnos.length} turno(s)`)),
      el("div", "acoes", seletorPasta(c), continuar, excluir)),
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
