// Aba "Recursos MCP": catálogo vivo de cada servidor (tools, resources,
// templates e prompts), com leitura de resources e geração de prompts.
import { $, el, api, emitir } from "./util.js";

const PRIMITIVAS = [
  { nome: "Tools", quem: "o MODELO decide", texto: "Funções com argumentos (JSON Schema). O LLM pede a chamada no meio do raciocínio; o orquestrador executa via tools/call e devolve o resultado.", exemplo: "buscar_arquivos(termo)" },
  { nome: "Resources", quem: "a APLICAÇÃO decide", texto: "Dados identificados por URI. O orquestrador lê (resources/read) os resources de cada agente ANTES de chamar o LLM e os coloca no system prompt.", exemplo: "rag://status" },
  { nome: "Prompts", quem: "o USUÁRIO decide", texto: "Modelos de pedido com argumentos, oferecidos pelo servidor (prompts/get). Aqui você preenche e envia para a conversa.", exemplo: "relatorio(assunto)" },
];

function parametros(schema) {
  const props = schema?.properties || {};
  const obrig = new Set(schema?.required || []);
  const nomes = Object.keys(props);
  if (!nomes.length) return el("span", "param-vazio", "sem parâmetros");
  return el("span", "params", ...nomes.map((n) =>
    el("code", obrig.has(n) ? "param obrigatorio" : "param", `${n}${obrig.has(n) ? "*" : ""}: ${props[n].type || "any"}`)));
}

function saida() {
  const pre = el("pre", "saida-mcp");
  pre.hidden = true;
  return pre;
}

function mostrar(pre, texto) {
  pre.hidden = false;
  pre.textContent = texto;
}

function quemUsa(lista) {
  return lista.length ? el("span", "usado-por", "usado por ", ...lista.map((a) => el("span", `chip agente-${a}`, a))) : null;
}

function blocoTools(srv, agentes) {
  return srv.tools.map((t) => {
    const usam = agentes.filter((a) => a.tools.includes(t.nome)).map((a) => a.nome);
    return el("div", "item-mcp",
      el("div", "item-mcp-cab", el("code", "nome-mcp", t.nome), quemUsa(usam)),
      el("p", "", t.descricao || ""), parametros(t.parametros));
  });
}

function blocoResources(srv, agentes) {
  return srv.resources.map((r) => {
    const pre = saida();
    const ler = el("button", "pequeno", "Ler agora");
    ler.type = "button";
    ler.addEventListener("click", async () => {
      mostrar(pre, "lendo…");
      try { mostrar(pre, (await api("/api/mcp/resource", { method: "POST", body: { uri: r.uri, servidor: srv.nome } })).conteudo); }
      catch (e) { mostrar(pre, "Erro: " + e.message); }
    });
    const usam = agentes.filter((a) => a.resources.includes(r.uri)).map((a) => a.nome);
    return el("div", "item-mcp",
      el("div", "item-mcp-cab", el("code", "nome-mcp", r.uri), el("span", "mime", r.mime || ""), quemUsa(usam)),
      el("p", "", (r.nome ? r.nome + " — " : "") + (r.descricao || "")), ler, pre);
  });
}

function formulario(campos, rotuloBotao, aoEnviar) {
  const inputs = campos.map((c) => {
    const i = el("input");
    i.placeholder = c.nome + (c.obrigatorio === false ? " (opcional)" : "");
    i.dataset.nome = c.nome;
    return i;
  });
  const botao = el("button", "pequeno", rotuloBotao);
  botao.type = "submit";
  const form = el("form", "form-mcp", ...inputs, botao);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const valores = Object.fromEntries(inputs.filter((i) => i.value.trim()).map((i) => [i.dataset.nome, i.value.trim()]));
    aoEnviar(valores);
  });
  return form;
}

function blocoTemplates(srv) {
  return srv.templates.map((t) => {
    const pre = saida();
    const campos = [...t.uri.matchAll(/\{(\w+)\}/g)].map((m) => ({ nome: m[1] }));
    const form = formulario(campos, "Ler resource", async (valores) => {
      const uri = t.uri.replace(/\{(\w+)\}/g, (_, n) => encodeURIComponent(valores[n] || ""));
      mostrar(pre, `lendo ${uri}…`);
      try { mostrar(pre, (await api("/api/mcp/resource", { method: "POST", body: { uri, servidor: srv.nome } })).conteudo); }
      catch (e) { mostrar(pre, "Erro: " + e.message); }
    });
    return el("div", "item-mcp",
      el("div", "item-mcp-cab", el("code", "nome-mcp", t.uri), el("span", "chip", "template")),
      el("p", "", (t.nome ? t.nome + " — " : "") + (t.descricao || "")), form, pre);
  });
}

function blocoPrompts(srv) {
  return srv.prompts.map((p) => {
    const pre = saida();
    const usar = el("button", "pequeno primario", "Usar na conversa");
    usar.type = "button";
    usar.hidden = true;
    usar.addEventListener("click", () => emitir("usar-texto", pre.textContent));
    const form = formulario(p.argumentos, "Gerar prompt", async (valores) => {
      try {
        mostrar(pre, (await api("/api/mcp/prompt", { method: "POST", body: { servidor: srv.nome, nome: p.nome, argumentos: valores } })).texto);
        usar.hidden = false;
      } catch (e) { mostrar(pre, "Erro: " + e.message); usar.hidden = true; }
    });
    return el("div", "item-mcp",
      el("div", "item-mcp-cab", el("code", "nome-mcp", p.nome)),
      el("p", "", p.descricao || ""), form, pre, usar);
  });
}

function secao(titulo, itens) {
  if (!itens.length) return null;
  return el("div", "secao-mcp", el("h4", "", `${titulo} (${itens.length})`), ...itens);
}

export async function iniciarMcp(agentes) {
  const raiz = $("#aba-mcp");
  let catalogo;
  try { catalogo = await api("/api/mcp"); }
  catch (e) { raiz.replaceChildren(el("div", "caixa-erro", "Falha ao carregar o catálogo MCP: " + e.message)); return; }

  const cardsPrimitivas = PRIMITIVAS.map((p) => el("div", "primitiva",
    el("h3", "", p.nome), el("span", "quem", p.quem), el("p", "", p.texto), el("code", "", p.exemplo)));

  const servidores = catalogo.servidores.map((srv) => {
    const usam = agentes.filter((a) => a.servidores.includes(srv.nome)).map((a) => a.nome);
    return el("article", "servidor",
      el("header", "servidor-cab",
        el("div", "", el("h3", "", "MCP · " + srv.nome), el("code", "modulo", `python -m ${srv.modulo}`)),
        el("div", "contagens",
          el("span", "chip", `${srv.tools.length} tools`),
          el("span", "chip", `${srv.resources.length + srv.templates.length} resources`),
          el("span", "chip", `${srv.prompts.length} prompts`))),
      quemUsa(usam),
      secao("Tools", blocoTools(srv, agentes)),
      secao("Resources", blocoResources(srv, agentes)),
      secao("Resource templates", blocoTemplates(srv)),
      secao("Prompts", blocoPrompts(srv)));
  });

  raiz.replaceChildren(
    el("div", "pagina-cabecalho",
      el("h2", "", "Recursos MCP"),
      el("p", "", "Tudo abaixo é lido ao vivo dos servidores (tools/list, resources/list, resources/templates/list, prompts/list). Cada servidor é um processo Python separado, conectado por stdio com JSON-RPC 2.0.")),
    el("div", "primitivas", ...cardsPrimitivas),
    el("div", "servidores", ...servidores));
}
