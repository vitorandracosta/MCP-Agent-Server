// Aba "Como funciona": fluxograma da arquitetura (destacando a última
// execução real), linha do tempo dos eventos, etapas, tecnologias e código.
import { $, el, api, formatarDuracao, ouvir } from "./util.js";

const FONTES = {
  arquivos: "pastas monitoradas",
  rag: "ChromaDB + embeddings",
  escrita: "pasta saidas/",
  sistema: "nvidia-smi · platform",
};

const ETAPAS = [
  { id: "usuario", titulo: "Usuário", arquivo: "web/static · client.py",
    texto: "Você digita o pedido na tela (ou no terminal).",
    seta: "HTTP POST /api/perguntar · resposta em stream NDJSON" },
  { id: "api", titulo: "API FastAPI", arquivo: "web/app.py",
    texto: "Recebe o pedido, carrega o histórico da conversa do SQLite e repassa ao orquestrador.",
    seta: "executar(mensagem, histórico, agente_forçado)" },
  { id: "roteador", titulo: "Roteador", arquivo: "agents/router.py", llm: "chat.completions · modo JSON",
    texto: "Envia ao LLM a descrição de cada agente e a mensagem; recebe {\"agente\", \"motivo\"}. A resposta é normalizada (acentos, pontuação) e, se inválida, cai no agente padrão.",
    seta: "agente escolhido + motivo" },
  { id: "agente", titulo: "Agente", arquivo: "agents/registry.py",
    texto: "Define o papel: system prompt, servidores/tools permitidos e os resources que viram contexto.",
    seta: "resources/read → contexto no system prompt" },
  { id: "loop", titulo: "Loop de tool-calling", arquivo: "orquestrador.py", llm: "chat.completions · tools",
    texto: "O LLM recebe só as tools do agente. Se pedir uma tool, o orquestrador executa e devolve o resultado; repete até vir texto (máx. 6 rodadas). Se o agente exige uma ação e o modelo só \"conversa\", recebe um lembrete.",
    seta: "tools/call · stdio · JSON-RPC 2.0" },
  { id: "hub", titulo: "HubMCP", arquivo: "orquestrador.py",
    texto: "Mantém uma sessão MCP aberta com cada servidor (subprocessos) e sabe qual servidor atende cada tool e cada resource.",
    servidores: true },
  { id: "resposta", titulo: "Resposta", arquivo: "web/historico.py",
    texto: "Cada evento vai para a tela no momento em que acontece; ao final, o turno inteiro é salvo no histórico." },
];

const TECNOLOGIAS = [
  ["Python 3.10+", "Linguagem de todo o backend."],
  ["MCP Python SDK (FastMCP)", "Servidores MCP (tools, resources, prompts) e o cliente que conecta neles."],
  ["Ollama", "Executa o LLM localmente e expõe uma API compatível com a da OpenAI."],
  ["__MODELO__", "LLM usado pelo roteador e por todos os agentes (troca pelo .env)."],
  ["OpenAI Python SDK", "Cliente da API de chat; funciona com Ollama ou com o Qwen na nuvem (DashScope)."],
  ["ChromaDB", "Banco vetorial persistente do RAG (similaridade de cosseno)."],
  ["sentence-transformers", "Gera os embeddings dos trechos e das perguntas (__EMBEDDING__)."],
  ["pypdf · python-docx", "Extraem texto de PDF/DOCX; python-docx também gera .docx."],
  ["FastAPI · Uvicorn", "API web e streaming de eventos em NDJSON."],
  ["SQLite", "Histórico de conversas com todos os eventos de cada turno."],
  ["HTML · CSS · JavaScript", "A tela, sem frameworks (ES modules)."],
  ["pytest", "Testes automatizados (segurança, roteador, RAG, orquestrador, histórico)."],
];

const CODIGO = [
  ["config.py", "configuração central (lê o .env)"],
  ["orquestrador.py", "HubMCP + Orquestrador (roteamento, resources, loop de tools)"],
  ["agents/registry.py", "definição dos agentes"],
  ["agents/router.py", "escolha do agente com motivo"],
  ["servers/*_server.py", "os 4 servidores MCP"],
  ["servers/seguranca.py", "allowlist de caminhos"],
  ["rag/indexer.py", "chunking, embeddings, Chroma, reindexação incremental"],
  ["rag/extracao.py", "texto de txt/md/py/pdf/docx"],
  ["web/app.py", "API REST + stream"],
  ["web/historico.py", "persistência SQLite (conversas, títulos, pastas)"],
  ["web/rag.py", "API da aba RAG (fontes, envios, exclusões, opções)"],
  ["web/guia.py", "guia lateral (estado e agentes)"],
  ["web/static/", "a tela (este código)"],
  ["client.py", "interface de terminal"],
  ["tests/", "testes automatizados"],
];

let catalogo = null;
let ultima = null;

function resumoExecucao(eventos) {
  const rot = eventos.find((e) => e.tipo === "roteamento");
  const servidores = new Set(eventos.filter((e) => e.servidor).map((e) => e.servidor));
  return {
    rot,
    servidores,
    tools: eventos.filter((e) => e.tipo === "tool_chamada").map((e) => e.tool),
    resources: eventos.filter((e) => e.tipo === "resource_lido").map((e) => e.uri),
    resposta: eventos.some((e) => e.tipo === "resposta"),
    erro: eventos.find((e) => e.tipo === "erro"),
  };
}

function detalheVivo(id, r) {
  if (!r?.rot) return null;
  const linha = (t) => el("div", "no-vivo", t);
  switch (id) {
    case "roteador": return linha(`→ ${r.rot.agente} (${r.rot.metodo}): ${r.rot.motivo}`);
    case "agente": return linha(`${r.rot.agente} · ${r.resources.length} resource(s) lido(s)`);
    case "loop": return linha(r.tools.length ? `${r.tools.length} chamada(s): ${r.tools.join(", ")}` : "nenhuma tool chamada");
    case "resposta": return linha(r.erro ? "erro: " + r.erro.mensagem : r.resposta ? "resposta entregue e salva" : "");
    default: return linha("✓");
  }
}

function noServidores(r) {
  const servidores = (catalogo?.servidores || []).map((s) => {
    const usado = r?.servidores.has(s.nome);
    return el("div", "srv" + (usado ? " usado" : ""),
      el("b", "", s.nome),
      el("span", "srv-contagem", `${s.tools.length}T · ${s.resources.length + s.templates.length}R · ${s.prompts.length}P`),
      el("span", "srv-fonte", "↓ " + (FONTES[s.nome] || "")));
  });
  return el("div", "srvs", ...servidores);
}

function diagrama() {
  const r = ultima ? resumoExecucao(ultima) : null;
  const nos = [];
  ETAPAS.forEach((etapa, i) => {
    const ativo = r?.rot && (etapa.id !== "loop" || r.tools.length || r.resposta);
    nos.push(el("div", "no" + (ativo ? " ativo" : ""),
      el("span", "no-num", i + 1),
      el("div", "no-corpo",
        el("div", "no-titulo", etapa.titulo, el("code", "no-arquivo", etapa.arquivo)),
        el("div", "no-texto", etapa.texto),
        detalheVivo(etapa.id, r),
        etapa.servidores ? noServidores(r) : null),
      etapa.llm ? el("div", "no-llm", el("span", "", "⇄ LLM"), el("small", "", etapa.llm)) : null));
    if (etapa.seta) nos.push(el("div", "seta", el("span", "", etapa.seta)));
    if (etapa.servidores) nos.push(el("div", "seta seta-volta", el("span", "", "resultado das tools volta ao LLM (etapa 5) até a resposta final")));
  });
  return el("div", "diagrama", ...nos);
}

function linhaDoTempo() {
  if (!ultima) {
    return el("p", "vazio-texto", "Faça um pedido na aba Conversa (ou clique em \"Ver no fluxograma\" num turno) para ver aqui o caminho real que ele percorreu.");
  }
  const total = Math.max(1, ...ultima.map((e) => e.t_ms || 0));
  const rotulo = (e) => ({
    roteamento: `roteador → ${e.agente}`,
    resource_lido: `resource ${e.uri}`,
    tool_chamada: `tool ${e.tool}`,
    tool_resultado: `resultado ${e.tool}${e.erro ? " (erro)" : ""}`,
    aviso: "aviso: " + e.mensagem,
    resposta: "resposta final",
    erro: "erro: " + e.mensagem,
  }[e.tipo] || e.tipo);
  return el("div", "timeline", ...ultima.filter((e) => e.t_ms !== undefined).map((e) =>
    el("div", `tl-linha tl-${e.tipo}`,
      el("span", "tl-rotulo", rotulo(e)),
      el("span", "tl-trilha", Object.assign(el("span", "tl-marca"), { style: `left:${(e.t_ms / total) * 100}%` })),
      el("span", "tl-tempo", formatarDuracao(e.t_ms)))));
}

function render(modelo, embedding) {
  const tecnologias = TECNOLOGIAS.map(([nome, papel]) => el("div", "tec",
    el("b", "", nome.replace("__MODELO__", modelo)), el("span", "", papel.replace("__EMBEDDING__", embedding))));
  $("#aba-fluxo").replaceChildren(
    el("div", "pagina-cabecalho",
      el("h2", "", "Como funciona"),
      el("p", "", "O caminho de um pedido, do clique à resposta. Depois de uma execução, as etapas percorridas ficam destacadas e os servidores MCP usados aparecem acesos.")),
    el("section", "bloco", el("h3", "", "Fluxograma"), diagrama()),
    el("section", "bloco", el("h3", "", "Linha do tempo da última execução"), linhaDoTempo()),
    el("section", "bloco", el("h3", "", "Tecnologias"), el("div", "tecs", ...tecnologias)),
    el("section", "bloco", el("h3", "", "Onde está cada parte no código"),
      el("table", "tabela", el("tbody", "", ...CODIGO.map(([a, d]) => el("tr", "", el("td", "", el("code", "", a)), el("td", "", d)))))),
  );
}

export async function iniciarFluxo(modelo) {
  let embedding = "all-MiniLM-L6-v2";
  try {
    catalogo = await api("/api/mcp");
    embedding = (await api("/api/status")).indice.modelo_embedding || embedding;
  } catch { /* o diagrama funciona sem os detalhes */ }
  const atualizar = () => render(modelo, embedding);
  ouvir("execucao-concluida", (eventos) => { ultima = eventos; atualizar(); });
  ouvir("mostrar-execucao", (eventos) => { ultima = eventos; atualizar(); location.hash = "#fluxo"; });
  // #fluxo/<id da conversa>: destaca o último turno daquela conversa.
  ouvir("aba-aberta", async ({ aba, parametro }) => {
    if (aba !== "fluxo" || !parametro) return;
    try {
      const conversa = await api(`/api/conversas/${parametro}`);
      ultima = conversa.turnos.at(-1)?.eventos || null;
      atualizar();
    } catch { /* conversa inexistente: mantém o diagrama sem destaque */ }
  });
  atualizar();
}
