// Ponto de entrada da tela: abas (pelo #hash da URL) e inicialização dos módulos.
import { $, api, emitir } from "./util.js";
import { iniciarChat } from "./chat.js";
import { iniciarHistorico } from "./historico.js";
import { iniciarRag } from "./rag.js";
import { iniciarMcp } from "./mcp.js";
import { iniciarFluxo } from "./fluxo.js";

const ABAS = ["conversa", "historico", "rag", "mcp", "fluxo"];

function abrirAba() {
  // Formato do hash: #aba ou #aba/parametro (ex.: #historico/<id da conversa>).
  const [nome, parametro] = location.hash.slice(1).split("/");
  const aba = ABAS.includes(nome) ? nome : "conversa";
  for (const nome of ABAS) {
    $(`#aba-${nome}`).hidden = nome !== aba;
    const link = $(`.abas a[data-aba="${nome}"]`);
    link.classList.toggle("ativa", nome === aba);
    link.setAttribute("aria-selected", nome === aba);
  }
  emitir("aba-aberta", { aba, parametro });
}

async function iniciar() {
  window.addEventListener("hashchange", abrirAba);
  let dados;
  try {
    dados = await api("/api/agentes");
  } catch (e) {
    $("#modelo").textContent = "servidor indisponível: " + e.message;
    return;
  }
  $("#modelo").textContent = `${dados.modelo} · ${dados.agentes.length} agentes`;
  await Promise.all([
    iniciarChat(dados.agentes),
    iniciarMcp(dados.agentes),
    iniciarFluxo(dados.modelo),
  ]);
  iniciarHistorico();
  iniciarRag();
  abrirAba();  // depois dos módulos, para que recebam o "aba-aberta" inicial
}

iniciar();
