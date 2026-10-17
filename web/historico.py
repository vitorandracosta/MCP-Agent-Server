"""
Histórico persistente das conversas (SQLite, biblioteca padrão).

Cada conversa tem vários turnos. Um turno guarda a pergunta, a escolha do
roteador (agente, motivo, método), a resposta final e TODOS os eventos da
execução (resources lidos, tools chamadas, resultados), para que a tela
possa reconstruir exatamente o que aconteceu.
"""
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (
    id            TEXT PRIMARY KEY,
    titulo        TEXT NOT NULL,
    criada_em     TEXT NOT NULL,
    atualizada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turnos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id TEXT NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    pergunta    TEXT NOT NULL,
    agente      TEXT,
    motivo      TEXT,
    metodo      TEXT,
    resposta    TEXT,
    erro        TEXT,
    eventos     TEXT NOT NULL,
    duracao_ms  INTEGER,
    criado_em   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turnos_conversa ON turnos(conversa_id);
"""


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Historico:
    def __init__(self, caminho: Path):
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(caminho), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(ESQUEMA)
        self._lock = threading.Lock()

    def registrar_turno(self, conversa_id: str, pergunta: str, eventos: list, duracao_ms: int):
        """Salva um turno (criando a conversa se for o primeiro) a partir dos eventos da execução."""
        roteamento = next((e for e in eventos if e["tipo"] == "roteamento"), {})
        resposta = next((e["conteudo"] for e in eventos if e["tipo"] == "resposta"), None)
        erro = next((e["mensagem"] for e in eventos if e["tipo"] == "erro"), None)
        agora = _agora()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO conversas (id, titulo, criada_em, atualizada_em) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET atualizada_em = excluded.atualizada_em",
                (conversa_id, pergunta.strip()[:80], agora, agora),
            )
            self._conn.execute(
                "INSERT INTO turnos (conversa_id, pergunta, agente, motivo, metodo, resposta, erro, "
                "eventos, duracao_ms, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (conversa_id, pergunta, roteamento.get("agente"), roteamento.get("motivo"),
                 roteamento.get("metodo"), resposta, erro,
                 json.dumps(eventos, ensure_ascii=False), duracao_ms, agora),
            )

    def mensagens_para_llm(self, conversa_id: str) -> list:
        """Pares pergunta/resposta da conversa, no formato de mensagens do LLM."""
        with self._lock:
            linhas = self._conn.execute(
                "SELECT pergunta, resposta FROM turnos WHERE conversa_id = ? AND resposta IS NOT NULL "
                "ORDER BY id", (conversa_id,),
            ).fetchall()
        mensagens = []
        for linha in linhas:
            mensagens += [{"role": "user", "content": linha["pergunta"]},
                          {"role": "assistant", "content": linha["resposta"]}]
        return mensagens

    def listar(self) -> list:
        with self._lock:
            linhas = self._conn.execute(
                "SELECT c.id, c.titulo, c.criada_em, c.atualizada_em, COUNT(t.id) AS n_turnos, "
                "GROUP_CONCAT(DISTINCT t.agente) AS agentes "
                "FROM conversas c LEFT JOIN turnos t ON t.conversa_id = c.id "
                "GROUP BY c.id ORDER BY c.atualizada_em DESC",
            ).fetchall()
        return [{**dict(l), "agentes": (l["agentes"] or "").split(",") if l["agentes"] else []}
                for l in linhas]

    def obter(self, conversa_id: str):
        with self._lock:
            conversa = self._conn.execute("SELECT * FROM conversas WHERE id = ?", (conversa_id,)).fetchone()
            if conversa is None:
                return None
            turnos = self._conn.execute(
                "SELECT * FROM turnos WHERE conversa_id = ? ORDER BY id", (conversa_id,),
            ).fetchall()
        return {**dict(conversa),
                "turnos": [{**dict(t), "eventos": json.loads(t["eventos"])} for t in turnos]}

    def estatisticas(self) -> dict:
        """Métricas agregadas por agente (úteis para avaliar o roteador e os agentes)."""
        with self._lock:
            geral = self._conn.execute(
                "SELECT COUNT(DISTINCT conversa_id) AS conversas, COUNT(*) AS turnos, "
                "ROUND(AVG(duracao_ms)) AS duracao_media_ms, "
                "SUM(erro IS NOT NULL) AS erros FROM turnos",
            ).fetchone()
            por_agente = self._conn.execute(
                "SELECT agente, COUNT(*) AS turnos, ROUND(AVG(duracao_ms)) AS duracao_media_ms, "
                "SUM(metodo = 'llm') AS pelo_roteador, SUM(metodo = 'manual') AS manual, "
                "SUM(metodo = 'padrao') AS fallback, SUM(erro IS NOT NULL) AS erros "
                "FROM turnos GROUP BY agente ORDER BY turnos DESC",
            ).fetchall()
        return {"geral": dict(geral), "por_agente": [dict(l) for l in por_agente]}

    def excluir(self, conversa_id: str) -> bool:
        with self._lock, self._conn:
            return self._conn.execute("DELETE FROM conversas WHERE id = ?", (conversa_id,)).rowcount > 0

    def fechar(self):
        self._conn.close()
