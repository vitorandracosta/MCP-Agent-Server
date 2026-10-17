// Renderiza um turno (pergunta + execução + resposta) a partir dos eventos
// do orquestrador. O mesmo componente serve para a conversa ao vivo e para
// reabrir turnos salvos no histórico.
import { el, markdown, formatarDuracao, emitir } from "./util.js";

const METODOS = {
  llm: "escolhido pelo roteador (LLM)",
  manual: "escolhido manualmente",
  padrao: "agente padrão (fallback)",
};

function tempo(ev) {
  return ev.t_ms !== undefined ? el("span", "passo-tempo", formatarDuracao(ev.t_ms)) : null;
}

export class Turno {
  constructor(container, pergunta, { aoVivo = true } = {}) {
    this.eventos = [];
    this.pendentes = [];
    container.append(el("div", "bolha-usuario", pergunta));

    this.card = el("article", "turno");
    this.roteamento = el("div", "turno-roteamento");
    this.roteamento.hidden = true;
    this.passos = el("div", "turno-passos");
    this.status = aoVivo ? el("div", "carregando", "Escolhendo agente") : null;
    this.resposta = el("div", "turno-resposta");
    this.arquivos = el("div", "turno-arquivos");
    this.rodape = el("div", "turno-rodape");
    this.card.append(...[this.roteamento, this.passos, this.status, this.resposta, this.arquivos, this.rodape].filter(Boolean));
    container.append(this.card);
  }

  aplicar(ev) {
    this.eventos.push(ev);
    switch (ev.tipo) {
      case "roteamento": return this._roteamento(ev);
      case "resource_lido": return this._resource(ev);
      case "tool_chamada": return this._toolChamada(ev);
      case "tool_resultado": return this._toolResultado(ev);
      case "aviso":
        this.passos.append(el("div", "passo passo-aviso", "⚠️ ", ev.mensagem, tempo(ev)));
        return;
      case "resposta":
        this.resposta.innerHTML = markdown(ev.conteudo || "(o agente não produziu texto)");
        return this._encerrarStatus();
      case "erro":
        this.resposta.append(el("div", "caixa-erro", "Erro: " + ev.mensagem));
        return this._encerrarStatus();
    }
  }

  finalizar(duracaoMs) {
    this._encerrarStatus();
    this.rodape.replaceChildren();
    const total = duracaoMs ?? this.eventos.at(-1)?.t_ms;
    if (total !== undefined) this.rodape.append(el("span", "", "⏱ " + formatarDuracao(total)));
    const n = this.eventos.filter((e) => e.tipo === "tool_chamada").length;
    this.rodape.append(el("span", "", `🔧 ${n} chamada(s) de tool`));
    const botao = el("button", "link", "Ver no fluxograma →");
    botao.type = "button";
    botao.addEventListener("click", () => emitir("mostrar-execucao", this.eventos));
    this.rodape.append(botao);
  }

  _encerrarStatus() {
    this.status?.remove();
    this.status = null;
  }

  _setStatus(texto) {
    if (this.status) this.status.textContent = texto;
  }

  _roteamento(ev) {
    this.roteamento.hidden = false;
    const servidores = ev.servidores.length ? ev.servidores.map((s) => el("span", "chip", "MCP " + s)) : [el("span", "chip", "sem tools")];
    this.roteamento.append(
      el("div", "rot-linha",
        el("span", "rot-rotulo", "Agente"),
        el("span", `rot-agente agente-${ev.agente}`, ev.agente),
        el("span", "rot-metodo", METODOS[ev.metodo] || ev.metodo),
        tempo(ev)),
      el("div", "rot-motivo", el("span", "rot-rotulo", "Por quê"), ev.motivo),
      el("div", "rot-servidores", ...servidores),
    );
    emitir("agente-escolhido", ev.agente);
    this._setStatus(`${ev.agente} trabalhando`);
  }

  _resource(ev) {
    const passo = el("details", "passo passo-resource" + (ev.erro ? " erro" : ""));
    passo.append(
      el("summary", "", "📚 ", el("span", "passo-tipo", "resource"), " ",
        el("code", "", ev.uri), el("span", "passo-servidor", ev.servidor || "?"), tempo(ev)),
      el("pre", "", ev.conteudo || "(vazio)"),
    );
    this.passos.append(passo);
    this._setStatus("Lendo contexto");
  }

  _toolChamada(ev) {
    const args = typeof ev.args === "string" ? ev.args : JSON.stringify(ev.args);
    const passo = el("details", "passo passo-tool");
    passo.append(el("summary", "", "🔧 ", el("span", "passo-tipo", "tool"), " ",
      el("code", "", ev.tool), el("span", "passo-servidor", ev.servidor || "?"),
      el("span", "passo-args", args), tempo(ev)));
    this.passos.append(passo);
    this.pendentes.push(passo);
    this._setStatus(`Executando ${ev.tool}`);
  }

  _toolResultado(ev) {
    const passo = this.pendentes.shift();
    if (passo) {
      if (ev.erro) passo.classList.add("erro");
      passo.append(el("pre", "", ev.resultado || "(vazio)"));
    }
    const criado = /Arquivo criado: (.+?) \(\d+ bytes\)/.exec(ev.resultado || "");
    if (ev.tool === "criar_arquivo" && criado) {
      const partes = criado[1].split(/[\\/]saidas[\\/]/);
      const nome = partes[partes.length - 1].replace(/\\/g, "/");
      const link = el("a", "arquivo-criado", "📄 Abrir " + nome);
      link.href = "/saidas/" + nome.split("/").map(encodeURIComponent).join("/");
      link.target = "_blank";
      this.arquivos.append(link);
    }
    this._setStatus("Pensando");
  }
}
