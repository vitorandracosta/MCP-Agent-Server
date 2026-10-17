// Aba "Conversa": envio do pedido, leitura do stream NDJSON e guia lateral.
import { $, el, api, emitir, ouvir } from "./util.js";
import { Turno } from "./turno.js";
import { carregarGuia } from "./guia.js";

let conversaId = null;
let ocupado = false;
let guia = null;

function rolarParaFim() {
  const m = $("#mensagens");
  m.scrollTop = m.scrollHeight;
}

function telaVazia() {
  const sugestoes = (guia?.agentes || [])
    .filter((a) => a.exemplos.length)
    .map((a) => {
      const b = el("button", "exemplo", el("span", `chip agente-${a.nome}`, a.nome), " ", a.exemplos[0]);
      b.type = "button";
      b.addEventListener("click", () => enviar(a.exemplos[0]));
      return b;
    });
  return el("div", "chat-vazio",
    el("h2", "", "Faça um pedido"),
    el("p", "", "O roteador escolhe o agente mais adequado e explica por quê. O agente lê seus resources, chama tools nos servidores MCP e responde. Cada passo aparece aqui."),
    el("div", "sugestoes", ...sugestoes),
    el("p", "dica-texto", "Veja no guia ao lado o que cada agente faz."));
}

function reiniciar() {
  conversaId = null;
  $("#titulo-conversa").textContent = "Nova conversa";
  $("#mensagens").replaceChildren(telaVazia());
}

async function lerStream(resposta, turno) {
  const leitor = resposta.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const linhas = buffer.split("\n");
    buffer = linhas.pop();
    for (const linha of linhas) {
      if (!linha.trim()) continue;
      const ev = JSON.parse(linha);
      if (ev.tipo === "inicio") conversaId = ev.conversa_id;
      else if (ev.tipo !== "fim") turno.aplicar(ev);
      rolarParaFim();
    }
  }
}

export async function enviar(texto) {
  if (ocupado || !texto.trim()) return;
  ocupado = true;
  $("#enviar").disabled = true;
  $(".chat-vazio")?.remove();
  document.body.classList.remove("guia-aberto");
  if (!conversaId) $("#titulo-conversa").textContent = texto.slice(0, 80);

  const turno = new Turno($("#mensagens"), texto);
  rolarParaFim();
  try {
    const r = await fetch("/api/perguntar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensagem: texto, conversa_id: conversaId, agente: $("#seletor").value }),
    });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    await lerStream(r, turno);
  } catch (e) {
    turno.aplicar({ tipo: "erro", mensagem: e.message });
  } finally {
    turno.finalizar();
    ocupado = false;
    $("#enviar").disabled = false;
    $("#entrada").focus();
    emitir("execucao-concluida", turno.eventos);
    emitir("historico-alterado");
  }
}

async function carregarConversa(id) {
  const conversa = await api(`/api/conversas/${id}`);
  conversaId = conversa.id;
  $("#titulo-conversa").textContent = conversa.titulo;
  const mensagens = $("#mensagens");
  mensagens.replaceChildren();
  for (const t of conversa.turnos) {
    const turno = new Turno(mensagens, t.pergunta, { aoVivo: false });
    t.eventos.forEach((ev) => turno.aplicar(ev));
    turno.finalizar(t.duracao_ms);
  }
  rolarParaFim();
}

export async function iniciarChat(agentes) {
  for (const a of agentes) {
    const opt = el("option", "", a.nome);
    opt.value = a.nome;
    $("#seletor").append(opt);
  }

  $("#form").addEventListener("submit", (e) => {
    e.preventDefault();
    const texto = $("#entrada").value;
    $("#entrada").value = "";
    $("#entrada").style.height = "auto";
    enviar(texto);
  });
  $("#entrada").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#form").requestSubmit(); }
  });
  $("#entrada").addEventListener("input", (e) => {
    e.target.style.height = "auto";
    e.target.style.height = e.target.scrollHeight + "px";
  });
  $("#nova").addEventListener("click", reiniciar);
  $("#abrir-guia").addEventListener("click", () => document.body.classList.toggle("guia-aberto"));

  ouvir("continuar-conversa", async (id) => {
    location.hash = "#conversa";
    await carregarConversa(id);
  });
  ouvir("aba-aberta", ({ aba, parametro }) => {
    if (aba === "conversa" && parametro && parametro !== conversaId) carregarConversa(parametro).catch(() => reiniciar());
  });
  ouvir("rag-alterado", async () => { guia = await carregarGuia($("#guia")); });
  ouvir("conversa-renomeada", ({ id, titulo }) => {
    if (id === conversaId) $("#titulo-conversa").textContent = titulo;
  });
  ouvir("usar-texto", (texto) => {
    location.hash = "#conversa";
    $("#entrada").value = texto;
    $("#entrada").dispatchEvent(new Event("input"));
    $("#entrada").focus();
  });
  ouvir("agente-escolhido", (nome) => {
    document.querySelectorAll(".guia-agente").forEach((c) => c.classList.toggle("ativo", c.classList.contains(`agente-borda-${nome}`)));
  });

  reiniciar();
  // As sugestões da tela vazia passam pelo roteador (não forçam o agente), para mostrar se ele acerta.
  guia = await carregarGuia($("#guia"));
  if (!conversaId && !$("#mensagens .turno")) reiniciar();
}
