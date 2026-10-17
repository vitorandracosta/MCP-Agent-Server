// Aba "RAG": fontes do índice (pastas, arquivos e envios), o que foi
// indexado e em quantos trechos, os trechos de cada arquivo, busca de teste
// e as opções do RAG (chunking, top-k, extensões, modelo de embedding).
import { $, el, api, emitir, ouvir } from "./util.js";

const ORIGENS = {
  env: ["do .env", "Definida em MCP_PASTAS no .env. Remover aqui não altera o .env e pode ser desfeito."],
  padrao: ["exemplo", "Documentos de exemplo do repositório, usados quando o .env não define MCP_PASTAS."],
  tela: ["adicionada aqui", ""],
  enviados: ["enviados", "Arquivos enviados por esta tela (ficam em dados/enviados)."],
};

let dados = null;       // GET /api/rag
let inventario = null;  // GET /api/rag/arquivos
let ocupado = false;
let filtro = "";

function botao(texto, classe, acao) {
  const b = el("button", classe, texto);
  b.type = "button";
  b.addEventListener("click", acao);
  return b;
}

function formatarTamanho(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

const separador = (c) => (c.includes("\\") ? "\\" : "/");

/** A fonte que contém o caminho e o caminho relativo a ela. */
function localizar(caminho) {
  const fonte = (dados?.fontes || [])
    .filter((f) => caminho === f.caminho || caminho.startsWith(f.caminho + separador(f.caminho)))
    .sort((a, b) => b.caminho.length - a.caminho.length)[0];
  if (!fonte) return { fonte: null, relativo: caminho };
  const relativo = caminho === fonte.caminho ? caminho.split(/[\\/]/).pop() : caminho.slice(fonte.caminho.length + 1);
  return { fonte, relativo };
}

const nomeCurto = (caminho) => caminho.split(/[\\/]/).filter(Boolean).pop() || caminho;

// ---------- Ações que mexem no índice ----------

async function executar(rotulo, acao) {
  if (ocupado) return;
  ocupado = true;
  mostrarProgresso(rotulo);
  try {
    await acao();
  } catch (e) {
    alert(e.message);
  } finally {
    ocupado = false;
    await recarregar();
  }
}

async function reindexar(forcar = false) {
  const r = await api(`/api/reindexar${forcar ? "?forcar=true" : ""}`, { method: "POST" });
  emitir("rag-alterado");
  return r;
}

function mostrarProgresso(texto) {
  const barra = $("#rag-progresso");
  if (!barra) return;
  barra.hidden = false;
  barra.replaceChildren(el("span", "carregando", texto));
  document.querySelectorAll("#aba-rag button").forEach((b) => { b.disabled = true; });
}

// ---------- Blocos ----------

function blocoResumo() {
  const s = dados.status;
  const semTexto = inventario.arquivos.filter((a) => a.trechos === 0).length;
  const pendentes = inventario.novos.length + inventario.modificados.length + inventario.apagados.length;
  const cartao = (rotulo, valor, classe = "") => el("div", "metrica " + classe, el("span", "metrica-valor", valor), el("span", "metrica-rotulo", rotulo));

  const aviso = pendentes
    ? el("div", "rag-aviso",
        el("span", "", `O índice está desatualizado: ${[
          inventario.novos.length && `${inventario.novos.length} arquivo(s) novo(s)`,
          inventario.modificados.length && `${inventario.modificados.length} modificado(s)`,
          inventario.apagados.length && `${inventario.apagados.length} apagado(s) ou fora das fontes`,
        ].filter(Boolean).join(", ")}. Até atualizar, o modelo não enxerga essas mudanças.`),
        botao("Atualizar índice", "pequeno primario", () => executar("Indexando… (pode levar minutos)", () => reindexar())))
    : null;

  return el("section", "",
    el("div", "metricas",
      cartao("fontes", dados.fontes.length),
      cartao("arquivos no índice", inventario.arquivos.length - semTexto),
      cartao("trechos (chunks)", inventario.total_chunks),
      cartao("sem texto extraível", semTexto, semTexto ? "metrica-alerta" : ""),
      cartao("pendentes", pendentes, pendentes ? "metrica-alerta" : "")),
    el("p", "rag-modelo", "Modelo de embedding: ", el("code", "", s.modelo_embedding),
      ` · trechos de ${dados.opcoes.chunk_size} caracteres com ${dados.opcoes.chunk_overlap} de sobreposição · ${dados.opcoes.top_k} trechos por busca`),
    aviso);
}

function blocoFontes() {
  const linhas = dados.fontes.map((f) => {
    const [rotulo, dica] = ORIGENS[f.origem] || [f.origem, ""];
    const chip = el("span", "chip", rotulo);
    if (dica) chip.title = dica;
    const remover = f.origem === "enviados" ? null : botao("Remover", "pequeno perigo", () => {
      const doEnv = f.origem === "tela" ? "" : "\n\nEla vem do .env, que não é alterado: dá para restaurá-la depois na lista de excluídos.";
      if (!confirm(`Remover a fonte ${f.caminho}?\n\nOs arquivos dela saem do índice e os agentes deixam de poder lê-los. Nada é apagado do seu computador.${doEnv}`)) return;
      executar("Removendo do índice…", async () => {
        await api(`/api/rag/fontes?caminho=${encodeURIComponent(f.caminho)}`, { method: "DELETE" });
        await reindexar();
      });
    });
    const excluirParte = f.tipo === "pasta" && f.existe && f.origem !== "enviados"
      ? botao("Excluir subpasta…", "pequeno", () => abrirNavegador(excluirDoIndice,
          { inicio: f.caminho, limite: f.caminho, rotulo: "Excluir esta pasta do índice", titulo: "Escolha a subpasta ou o arquivo que não deve ser indexado" }))
      : null;
    return el("div", "fonte" + (f.existe ? "" : " fonte-faltando"),
      el("span", "fonte-icone", f.tipo === "arquivo" ? "📄" : "📁"),
      el("div", "fonte-texto", el("code", "", f.caminho),
        f.existe ? null : el("span", "aviso-texto", " não encontrada")),
      chip, excluirParte, remover);
  });

  const campo = el("input", "rag-campo");
  campo.placeholder = "Caminho completo de uma pasta ou arquivo (ex.: C:\\Users\\voce\\Documentos\\Disciplinas)";
  const adicionar = (caminho) => executar("Adicionando e indexando… (pode levar minutos)", async () => {
    await api("/api/rag/fontes", { method: "POST", body: { caminho } });
    campo.value = "";
    await reindexar();
  });
  const form = el("form", "rag-linha", campo,
    botao("Procurar…", "", () => abrirNavegador((caminho) => { campo.value = caminho; })),
    el("button", "primario", "Adicionar"));
  form.lastChild.type = "submit";
  form.addEventListener("submit", (e) => { e.preventDefault(); if (campo.value.trim()) adicionar(campo.value.trim()); });

  const arquivo = el("input");
  arquivo.type = "file";
  arquivo.multiple = true;
  arquivo.accept = dados.extensoes_conhecidas.join(",");
  arquivo.hidden = true;
  arquivo.addEventListener("change", () => enviarArquivos([...arquivo.files]));
  const zona = el("div", "rag-envio",
    el("span", "", "Arraste arquivos para cá ou "),
    botao("escolha no computador", "link", () => arquivo.click()),
    el("span", "guia-nota", ` (${dados.extensoes_conhecidas.join(", ")}; cópias ficam em dados/enviados)`),
    arquivo);
  zona.addEventListener("dragover", (e) => { e.preventDefault(); zona.classList.add("arrastando"); });
  zona.addEventListener("dragleave", () => zona.classList.remove("arrastando"));
  zona.addEventListener("drop", (e) => {
    e.preventDefault();
    zona.classList.remove("arrastando");
    enviarArquivos([...e.dataTransfer.files]);
  });

  return el("section", "bloco",
    el("h3", "", "Fontes"),
    el("p", "guia-nota", "Pastas e arquivos que viram contexto. Tudo que está aqui entra no índice e também pode ser lido pelos agentes explorador, resumidor e escritor."),
    el("div", "fontes", ...linhas),
    blocoExcluidos(),
    form, zona);
}

function excluirDoIndice(caminho) {
  executar("Excluindo do índice…", async () => {
    await api("/api/rag/exclusoes", { method: "POST", body: { caminho } });
    await reindexar();
  });
}

function blocoExcluidos() {
  const removidas = dados.fontes_removidas.map((c) => el("div", "fonte fonte-excluida",
    el("span", "fonte-icone", "📁"),
    el("div", "fonte-texto", el("code", "", c), el("span", "guia-nota", " fonte do .env removida")),
    botao("Restaurar", "pequeno", () => executar("Restaurando e indexando… (pode levar minutos)", async () => {
      await api("/api/rag/fontes", { method: "POST", body: { caminho: c } });
      await reindexar();
    }))));
  const exclusoes = dados.exclusoes.map((c) => {
    const { relativo, fonte } = localizar(c);
    return el("div", "fonte fonte-excluida",
      el("span", "fonte-icone", "🚫"),
      el("div", "fonte-texto", el("code", "", relativo), el("span", "guia-nota", fonte ? ` em ${nomeCurto(fonte.caminho)}` : "")),
      botao("Incluir de novo", "pequeno", () => executar("Incluindo e indexando… (pode levar minutos)", async () => {
        await api(`/api/rag/exclusoes?caminho=${encodeURIComponent(c)}`, { method: "DELETE" });
        await reindexar();
      })));
  });
  if (!removidas.length && !exclusoes.length) return null;
  return el("div", "excluidos",
    el("h4", "", "Fora do índice"),
    el("p", "guia-nota", "Fontes removidas saem também do alcance dos agentes. Subpastas e arquivos excluídos só deixam de ser indexados: o explorador ainda consegue abri-los pelo nome."),
    el("div", "fontes", ...removidas, ...exclusoes));
}

function enviarArquivos(arquivos) {
  if (!arquivos.length) return;
  executar(`Enviando ${arquivos.length} arquivo(s) e indexando…`, async () => {
    for (const f of arquivos) {
      const r = await fetch(`/api/rag/enviar?nome=${encodeURIComponent(f.name)}`, {
        method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: f,
      });
      if (!r.ok) throw new Error(`${f.name}: ${(await r.json().catch(() => ({}))).detail || r.statusText}`);
    }
    await reindexar();
  });
}

function blocoArquivos() {
  const pendentes = new Set([...inventario.novos, ...inventario.modificados]);
  const busca = el("input", "rag-campo");
  busca.type = "search";
  busca.placeholder = "Filtrar arquivos…";
  busca.value = filtro;
  const lista = el("div", "rag-arquivos");

  const linhaArquivo = (caminho, info) => {
    const { fonte, relativo } = localizar(caminho);
    const estado = !info ? el("span", "chip chip-alerta", "não indexado")
      : pendentes.has(caminho) ? el("span", "chip chip-alerta", "modificado")
      : info.trechos === 0 ? el("span", "chip chip-alerta", "sem texto")
      : el("span", "chip", `${info.trechos} trecho(s)`);
    const det = el("details", "rag-arquivo");
    const corpo = el("div", "rag-trechos");
    det.addEventListener("toggle", async () => {
      if (!det.open || corpo.dataset.carregado) return;
      corpo.dataset.carregado = "1";
      if (!info) { corpo.replaceChildren(el("p", "vazio-texto", "Ainda não indexado. Clique em \"Atualizar índice\".")); return; }
      if (info.trechos === 0) {
        corpo.replaceChildren(el("p", "vazio-texto", "Nenhum texto foi extraído: o arquivo está vazio, é um PDF escaneado (imagem) ou não pôde ser lido. Sem OCR, o modelo não enxerga este conteúdo."));
        return;
      }
      corpo.replaceChildren(el("span", "carregando", "Carregando trechos"));
      try {
        const trechos = await api(`/api/rag/trechos?caminho=${encodeURIComponent(caminho)}`);
        corpo.replaceChildren(
          el("p", "guia-nota", "Cada trecho é um vetor no índice. A busca devolve os trechos mais parecidos com a pergunta, e é só isso que o modelo lê."),
          ...trechos.map((t) => el("div", "trecho", el("span", "trecho-num", `#${t.chunk}`), el("pre", "", t.texto))));
      } catch (e) { corpo.replaceChildren(el("div", "caixa-erro", e.message)); }
    });
    const apagar = fonte?.origem === "enviados" && info
      ? botao("Apagar", "pequeno perigo", (e) => {
          e.preventDefault();
          if (!confirm(`Apagar ${relativo} dos arquivos enviados e do índice?`)) return;
          executar("Apagando…", async () => {
            await api(`/api/rag/enviados?caminho=${encodeURIComponent(caminho)}`, { method: "DELETE" });
            await reindexar();
          });
        })
      : null;
    const excluir = fonte && fonte.origem !== "enviados" && fonte.caminho !== caminho
      ? botao("Excluir", "pequeno", (e) => {
          e.preventDefault();
          if (confirm(`Excluir ${relativo} do índice?\n\nO arquivo não é apagado; dá para incluí-lo de novo depois.`)) excluirDoIndice(caminho);
        })
      : null;
    if (excluir) excluir.title = "Deixar de indexar este arquivo";
    det.append(
      el("summary", "",
        el("span", "rag-arquivo-nome", relativo),
        el("span", "rag-arquivo-fonte", fonte ? nomeCurto(fonte.caminho) : ""),
        el("span", "rag-arquivo-tam", formatarTamanho(info?.tamanho)), estado, excluir, apagar),
      corpo);
    return det;
  };

  const desenhar = () => {
    const termo = filtro.trim().toLowerCase();
    const porCaminho = new Map(inventario.arquivos.map((a) => [a.caminho, a]));
    const caminhos = [...new Set([...porCaminho.keys(), ...inventario.novos])]
      .filter((c) => !inventario.apagados.includes(c))
      .filter((c) => !termo || c.toLowerCase().includes(termo))
      .sort((a, b) => a.localeCompare(b, "pt-BR"));
    const visiveis = caminhos.slice(0, 300);
    lista.replaceChildren(
      ...(visiveis.length ? visiveis.map((c) => linhaArquivo(c, porCaminho.get(c)))
        : [el("p", "vazio-texto", inventario.arquivos.length ? "Nenhum arquivo encontrado." : "O índice está vazio. Adicione uma fonte ou clique em \"Atualizar índice\".")]),
      caminhos.length > visiveis.length ? el("p", "guia-nota", `Mostrando 300 de ${caminhos.length}. Use o filtro para achar os demais.`) : null);
  };
  busca.addEventListener("input", () => { filtro = busca.value; desenhar(); });
  desenhar();

  return el("section", "bloco",
    el("div", "rag-titulo",
      el("h3", "", "O que está no índice"),
      el("div", "acoes",
        botao("Atualizar índice", "pequeno", () => executar("Indexando… (pode levar minutos)", () => reindexar())),
        botao("Refazer do zero", "pequeno", () => {
          if (!confirm("Apagar o índice e gerar todos os embeddings de novo? Pode levar vários minutos.")) return;
          executar("Refazendo o índice… (pode levar minutos)", () => reindexar(true));
        }))),
    el("p", "guia-nota", "Abra um arquivo para ver os trechos exatamente como foram guardados. Arquivos \"sem texto\" não ajudam o modelo em nada."),
    busca, lista);
}

function blocoBusca() {
  const pergunta = el("input", "rag-campo");
  pergunta.placeholder = "Faça uma pergunta para ver quais trechos a busca devolve";
  const k = el("input", "rag-k");
  k.type = "number"; k.min = 1; k.max = 30; k.value = dados.opcoes.top_k;
  k.title = "Quantos trechos trazer (top-k)";
  const resultado = el("div", "rag-resultados");
  const form = el("form", "rag-linha", pergunta, el("label", "seletor", "k", k), el("button", "primario", "Buscar"));
  form.lastChild.type = "submit";
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!pergunta.value.trim()) return;
    resultado.replaceChildren(el("span", "carregando", "Buscando"));
    try {
      const hits = await api("/api/rag/busca", { method: "POST", body: { pergunta: pergunta.value, k: Number(k.value) } });
      resultado.replaceChildren(...(hits.length ? hits.map((h, i) => {
        const preenchido = el("span");
        preenchido.style.width = `${Math.max(0, Math.min(100, h.score * 100))}%`;
        return el("div", "hit",
          el("div", "hit-cab",
            el("b", "", `${i + 1}.`), el("code", "", localizar(h.fonte).relativo), el("span", "trecho-num", `#${h.chunk ?? "?"}`),
            el("span", "hit-score", el("span", "hit-barra", preenchido), h.score.toFixed(2))),
          el("pre", "", h.texto));
      }) : [el("p", "vazio-texto", "O índice está vazio.")]));
    } catch (err) { resultado.replaceChildren(el("div", "caixa-erro", err.message)); }
  });
  return el("section", "bloco",
    el("h3", "", "Testar a busca"),
    el("p", "guia-nota", "É a mesma busca que o agente pesquisador faz com buscar_contexto_local. A similaridade é o cosseno entre a pergunta e o trecho (1 = idêntico). Abaixo de ~0,3 o trecho costuma ser pouco relevante."),
    form, resultado);
}

function blocoOpcoes() {
  const o = dados.opcoes;
  const numero = (valor, min, max, passo = 1) => {
    const i = el("input", "rag-num");
    Object.assign(i, { type: "number", min, max, step: passo, value: valor });
    return i;
  };
  const tamanho = numero(o.chunk_size, 100, 4000, 50);
  const sobreposicao = numero(o.chunk_overlap, 0, 2000, 10);
  const topk = numero(o.top_k, 1, 20);
  const extensoes = dados.extensoes_conhecidas.map((ext) => {
    const c = el("input");
    c.type = "checkbox"; c.value = ext; c.checked = o.extensoes.includes(ext);
    return el("label", "rag-check", c, ext);
  });
  const modelo = el("input", "rag-campo");
  modelo.value = o.embedding_model;
  modelo.setAttribute("list", "rag-modelos");
  const sugestoes = el("datalist", "", ...dados.modelos_sugeridos.map((m) => { const op = el("option", "", m.nota); op.value = m.nome; return op; }));
  sugestoes.id = "rag-modelos";

  const campo = (rotulo, entrada, ajuda) => el("label", "rag-opcao", el("span", "rag-opcao-rotulo", rotulo), entrada, el("span", "guia-nota", ajuda));

  const salvar = botao("Salvar", "primario", async () => {
    const novo = {
      chunk_size: Number(tamanho.value), chunk_overlap: Number(sobreposicao.value), top_k: Number(topk.value),
      extensoes: extensoes.map((l) => l.firstChild).filter((c) => c.checked).map((c) => c.value),
      embedding_model: modelo.value.trim(),
    };
    const refaz = novo.chunk_size !== o.chunk_size || novo.chunk_overlap !== o.chunk_overlap || novo.embedding_model !== o.embedding_model;
    if (refaz && !confirm("Mudar o tamanho dos trechos ou o modelo de embedding refaz o índice inteiro (pode levar minutos" +
        (novo.embedding_model !== o.embedding_model ? "; um modelo novo é baixado da internet na primeira vez" : "") + "). Continuar?")) return;
    executar(refaz ? "Salvando e refazendo o índice… (pode levar minutos)" : "Salvando…", async () => {
      const r = await api("/api/rag/opcoes", { method: "PUT", body: novo });
      if (r.refazer_indice || r.mudou_extensoes) await reindexar();
      else emitir("rag-alterado");
    });
  });
  const restaurar = botao("Restaurar padrões", "", () => {
    const p = dados.padroes;
    tamanho.value = p.chunk_size; sobreposicao.value = p.chunk_overlap; topk.value = p.top_k; modelo.value = p.embedding_model;
    extensoes.forEach((l) => { l.firstChild.checked = p.extensoes.includes(l.firstChild.value); });
  });

  return el("section", "bloco",
    el("h3", "", "Opções"),
    el("p", "guia-nota", "Antes só dava para mudar isso no código ou no .env. O que for salvo aqui fica em dados/rag_config.json e vale para todos os servidores MCP na hora."),
    el("div", "rag-opcoes",
      campo("Tamanho do trecho", tamanho, "caracteres por chunk. Menor = busca mais precisa, porém com menos contexto em cada trecho."),
      campo("Sobreposição", sobreposicao, "caracteres repetidos entre trechos vizinhos, para não cortar uma ideia ao meio."),
      campo("Trechos por busca (top-k)", topk, "quantos trechos o agente recebe. Mais trechos ocupam mais do contexto (pequeno) do modelo."),
      el("div", "rag-opcao", el("span", "rag-opcao-rotulo", "Extensões indexadas"), el("div", "rag-checks", ...extensoes)),
      campo("Modelo de embedding", el("div", "", modelo, sugestoes),
        dados.modelos_sugeridos.map((m) => `${m.nome}: ${m.nota}`).join(" · "))),
    el("div", "acoes", salvar, restaurar));
}

// ---------- Navegador de pastas ----------

/**
 * inicio: pasta onde abre; limite: não deixa subir acima dela;
 * rotulo: texto do botão que escolhe a pasta aberta; titulo: cabeçalho.
 */
function abrirNavegador(aoEscolher, { inicio = "", limite = null, rotulo = "Escolher esta pasta", titulo = "Escolher pasta ou arquivo" } = {}) {
  const dialogo = el("dialog", "navegador");
  const corpo = el("div", "navegador-corpo");
  const fechar = () => { dialogo.close(); dialogo.remove(); };
  const ir = async (caminho) => {
    corpo.replaceChildren(el("span", "carregando", "Abrindo"));
    let r;
    try { r = await api(`/api/rag/navegar?caminho=${encodeURIComponent(caminho)}`); }
    catch (e) { corpo.replaceChildren(el("div", "caixa-erro", e.message), botao("Voltar ao início", "pequeno", () => ir(""))); return; }
    const itens = r.itens.map((i) => {
      const b = botao((i.tipo === "pasta" ? "📁 " : "📄 ") + i.nome, "navegador-item", () => {
        if (i.tipo === "pasta") ir(i.caminho);
        else { aoEscolher(i.caminho); fechar(); }
      });
      return b;
    });
    const noLimite = limite !== null && r.caminho === limite;
    corpo.replaceChildren(
      el("div", "navegador-topo",
        r.pai !== null && !noLimite ? botao("↑ Subir", "pequeno", () => ir(r.pai)) : null,
        el("code", "", r.caminho || "Locais"),
        r.caminho && !noLimite ? botao(rotulo, "pequeno primario", () => { aoEscolher(r.caminho); fechar(); }) : null),
      el("div", "navegador-lista", ...(itens.length ? itens : [el("p", "vazio-texto", "Pasta vazia (só aparecem subpastas e arquivos suportados).")])));
  };
  dialogo.append(el("div", "navegador-cab", el("b", "", titulo), botao("✕", "icone", fechar)), corpo);
  dialogo.addEventListener("close", () => dialogo.remove());
  document.body.append(dialogo);
  dialogo.showModal();
  ir(inicio);
}

// ---------- Montagem ----------

async function recarregar() {
  const raiz = $("#aba-rag");
  if (!dados) raiz.replaceChildren(el("div", "carregando", "Lendo o índice"));
  try {
    [dados, inventario] = await Promise.all([api("/api/rag"), api("/api/rag/arquivos")]);
  } catch (e) {
    raiz.replaceChildren(el("div", "caixa-erro", "Falha ao carregar o RAG: " + e.message));
    return;
  }
  const progresso = el("div", "rag-progresso");
  progresso.id = "rag-progresso";
  progresso.hidden = true;

  raiz.replaceChildren(
    el("div", "pagina-cabecalho",
      el("h2", "", "RAG: o que o modelo pode usar como contexto"),
      el("p", "", "Os arquivos das fontes viram texto, o texto é cortado em trechos, cada trecho vira um vetor (embedding) e vai para o banco vetorial local (ChromaDB). Numa pergunta, a busca devolve os trechos mais parecidos, e só eles chegam ao modelo.")),
    blocoResumo(), progresso, blocoFontes(), blocoArquivos(), blocoBusca(), blocoOpcoes());
}

export function iniciarRag() {
  ouvir("aba-aberta", ({ aba }) => { if (aba === "rag" && !ocupado) recarregar(); });
}
