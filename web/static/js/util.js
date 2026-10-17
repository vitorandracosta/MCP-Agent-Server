// Utilitários compartilhados pelas abas.

export const $ = (seletor, raiz = document) => raiz.querySelector(seletor);

/** Cria um elemento. Texto sempre via textContent (nunca innerHTML) para evitar XSS. */
export function el(tag, classe, ...filhos) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  for (const f of filhos) {
    if (f === null || f === undefined || f === false) continue;
    e.append(f instanceof Node ? f : String(f));
  }
  return e;
}

export function escapar(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Markdown mínimo e seguro: tudo é escapado antes de virar HTML. */
export function markdown(texto) {
  const blocos = [];
  let s = escapar(texto).replace(/```[\w-]*\n?([\s\S]*?)```/g, (_, c) => {
    blocos.push(`<pre><code>${c}</code></pre>`);
    return `\u0000${blocos.length - 1}\u0000`;
  });
  s = s.replace(/^### (.*)$/gm, "<h3>$1</h3>")
       .replace(/^## (.*)$/gm, "<h2>$1</h2>")
       .replace(/^# (.*)$/gm, "<h1>$1</h1>")
       .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
       .replace(/`([^`\n]+)`/g, "<code>$1</code>")
       .replace(/^[ \t]*[-*] (.*)$/gm, "<li>$1</li>")
       .replace(/^[ \t]*\d+\. (.*)$/gm, "<li>$1</li>")
       .replace(/(?:<li>.*<\/li>(?:\n|$))+/g, (lista) => `<ul>${lista.trim()}</ul>\n`);
  s = s.split(/\n{2,}/).map((p) => /^\s*<(h\d|ul|pre)|\u0000/.test(p) ? p : `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => blocos[i]);
}

export async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, {
    ...opcoes,
    headers: opcoes.body ? { "Content-Type": "application/json" } : undefined,
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined,
  });
  const dados = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(dados.detail || r.statusText);
  return dados;
}

export function formatarData(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function formatarDuracao(ms) {
  if (ms === null || ms === undefined) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** Barramento simples de eventos entre as abas. */
export const barramento = new EventTarget();
export const emitir = (nome, detalhe) => barramento.dispatchEvent(new CustomEvent(nome, { detail: detalhe }));
export const ouvir = (nome, fn) => barramento.addEventListener(nome, (e) => fn(e.detail));
