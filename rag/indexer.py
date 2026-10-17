"""
Indexador RAG.

Varre WATCHED_PATHS, extrai texto de cada arquivo suportado, quebra em
chunks, gera embeddings e persiste num banco vetorial (Chroma) local em
disco. A reindexação é incremental: um manifest.json guarda o mtime de
cada arquivo já indexado, então só reprocessa o que mudou, e remove do
índice os arquivos que foram apagados.
"""
import hashlib
import json
import os
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

import config
from .extracao import extrair_texto, log

# A distância usada é cosseno, então score = 1 - distância fica em [-1, 1]
# e significa similaridade de cosseno de verdade (1 = idêntico).
ESPACO_DISTANCIA = "cosine"
TAMANHO_LOTE = 1000  # o Chroma limita quantos itens cabem num único add()

MODELO_PADRAO_ANTIGO = "all-MiniLM-L6-v2"  # coleções criadas antes de guardarmos o modelo

_model = None
_nome_model = None
_client = None
_collection = None


def _manifest_path() -> Path:
    return Path(config.PERSIST_DIR) / "manifest.json"


def _get_model():
    global _model, _nome_model
    config.sincronizar()
    if _model is None or _nome_model != config.EMBEDDING_MODEL:
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
        _nome_model = config.EMBEDDING_MODEL
    return _model


def _espaco_da_colecao(collection) -> str:
    cfg = getattr(collection, "configuration", None) or {}
    espaco = (cfg.get("hnsw") or {}).get("space") if isinstance(cfg, dict) else None
    return espaco or (collection.metadata or {}).get("hnsw:space", "l2")


def _get_collection():
    global _client, _collection
    config.sincronizar()
    if (_collection is not None and (_collection.metadata or {}).get("embedding_model", MODELO_PADRAO_ANTIGO)
            != config.EMBEDDING_MODEL):
        _collection = None  # o modelo foi trocado pela tela: a checagem abaixo recria a coleção
    if _collection is None:
        Path(config.PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(config.PERSIST_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        metadata = {"hnsw:space": ESPACO_DISTANCIA, "embedding_model": config.EMBEDDING_MODEL}
        collection = _client.get_or_create_collection(config.COLLECTION_NAME, metadata=metadata)
        # A métrica e o modelo de embedding não podem mudar numa coleção
        # existente (vetores de modelos diferentes não são comparáveis):
        # nesses casos recria do zero e força a reindexação.
        modelo_atual = (collection.metadata or {}).get("embedding_model", MODELO_PADRAO_ANTIGO)
        if _espaco_da_colecao(collection) != ESPACO_DISTANCIA or modelo_atual != config.EMBEDDING_MODEL:
            log("[rag] Coleção usa outra métrica ou outro modelo de embedding; recriando.")
            _client.delete_collection(config.COLLECTION_NAME)
            _manifest_path().unlink(missing_ok=True)
            collection = _client.create_collection(config.COLLECTION_NAME, metadata=metadata)
        _collection = collection
    return _collection


def _chunk(text: str):
    size, overlap = config.CHUNK_SIZE, config.CHUNK_OVERLAP
    step = max(size - overlap, 1)
    chunks = []
    for start in range(0, len(text), step):
        piece = text[start:start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(text):
            break
    return chunks


def _file_id(path: Path, mtime: float) -> str:
    return hashlib.sha256(f"{path}:{mtime}".encode()).hexdigest()


def _arquivos_da_pasta(base: Path):
    for root, pastas, files in os.walk(base):
        # Nem entra nas subpastas excluídas pela tela (podem ser grandes).
        pastas[:] = [d for d in pastas if not config.excluido(Path(root) / d)]
        for name in files:
            yield Path(root) / name


def _iter_files():
    config.sincronizar()
    vistos = set()  # fontes podem se sobrepor (uma pasta e um arquivo dentro dela)
    for base_path in config.WATCHED_PATHS:
        if not base_path.exists():
            log(f"[rag] Caminho não encontrado, pulando: {base_path}")
            continue
        if base_path.is_file():  # fonte que é um arquivo solto
            candidatos = [base_path]
        else:
            candidatos = _arquivos_da_pasta(base_path)
        for p in candidatos:
            if (p.suffix.lower() in config.SUPPORTED_EXTENSIONS and p not in vistos
                    and not config.excluido(p)):
                vistos.add(p)
                yield p


def build_index(force: bool = False) -> dict:
    """Reindexa arquivos novos ou modificados e remove os que foram apagados."""
    collection = _get_collection()
    model = _get_model()

    # Trechos gerados com outro tamanho/sobreposição não convivem bem com os
    # novos: se o chunking mudou desde a última indexação, refaz tudo.
    parametros = {"chunk_size": config.CHUNK_SIZE, "chunk_overlap": config.CHUNK_OVERLAP}
    caminho_parametros = Path(config.PERSIST_DIR) / "parametros.json"
    if caminho_parametros.exists() and json.loads(caminho_parametros.read_text(encoding="utf-8")) != parametros:
        log("[rag] Parâmetros de chunking mudaram; reindexando tudo.")
        force = True

    manifest = {}
    if _manifest_path().exists():
        manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    if force:  # apaga tudo o que estava no índice, inclusive de fontes que saíram
        for key in manifest:
            collection.delete(where={"source": key})
        manifest = {}

    new_manifest = {}
    indexed, skipped, vazios = 0, 0, 0

    for path in _iter_files():
        mtime = path.stat().st_mtime
        key = str(path)
        new_manifest[key] = mtime

        if not force and manifest.get(key) == mtime:
            skipped += 1
            continue

        # Remove chunks antigos desse arquivo antes de reinserir a versão nova.
        collection.delete(where={"source": key})

        chunks = _chunk(extrair_texto(path))
        if not chunks:
            vazios += 1
            continue

        embeddings = model.encode(chunks, normalize_embeddings=True).tolist()
        ids = [f"{_file_id(path, mtime)}-{i}" for i in range(len(chunks))]
        metadatas = [{"source": key, "chunk": i} for i in range(len(chunks))]

        for i in range(0, len(chunks), TAMANHO_LOTE):
            fatia = slice(i, i + TAMANHO_LOTE)
            collection.add(
                ids=ids[fatia], embeddings=embeddings[fatia],
                documents=chunks[fatia], metadatas=metadatas[fatia],
            )
        indexed += 1

    # Arquivos que estavam no manifest antigo mas não existem mais.
    removidos = [key for key in manifest if key not in new_manifest]
    for key in removidos:
        collection.delete(where={"source": key})

    _manifest_path().write_text(json.dumps(new_manifest), encoding="utf-8")
    caminho_parametros.write_text(json.dumps(parametros), encoding="utf-8")
    resumo = {
        "atualizados": indexed,
        "sem_alteracao": skipped,
        "sem_texto": vazios,
        "removidos": len(removidos),
        "total_chunks": collection.count(),
    }
    log(f"[rag] Indexação concluída: {resumo}")
    return resumo


def arquivos_indexados() -> list:
    """Caminhos dos arquivos registrados no manifest da última indexação."""
    if not _manifest_path().exists():
        return []
    return list(json.loads(_manifest_path().read_text(encoding="utf-8")))


def status() -> dict:
    collection = _get_collection()
    return {
        "indice_construido": _manifest_path().exists(),
        "arquivos_no_manifest": len(arquivos_indexados()),
        "total_chunks": collection.count(),
        "modelo_embedding": config.EMBEDDING_MODEL,
        "pastas_monitoradas": [str(p) for p in config.WATCHED_PATHS],
    }


def inventario() -> dict:
    """
    O que está no índice, arquivo por arquivo (quantos trechos cada um gerou),
    e o que mudou nas fontes desde a última indexação (pendentes).
    """
    collection = _get_collection()
    manifest = {}
    if _manifest_path().exists():
        manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    trechos = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
        trechos[meta["source"]] = trechos.get(meta["source"], 0) + 1

    arquivos = []
    for caminho, mtime in manifest.items():
        p = Path(caminho)
        arquivos.append({"caminho": caminho, "trechos": trechos.get(caminho, 0), "indexado_mtime": mtime,
                         "tamanho": p.stat().st_size if p.exists() else None})
    atuais = {str(p): p.stat().st_mtime for p in _iter_files()}
    return {
        "arquivos": arquivos,
        "novos": sorted(c for c in atuais if c not in manifest),
        "modificados": sorted(c for c, m in atuais.items() if c in manifest and manifest[c] != m),
        "apagados": sorted(c for c in manifest if c not in atuais),
        "total_chunks": collection.count(),
    }


def trechos_do_arquivo(caminho: str) -> list:
    """Os trechos (chunks) que foram gerados para um arquivo, na ordem."""
    dados = _get_collection().get(where={"source": caminho}, include=["documents", "metadatas"])
    pares = sorted(zip(dados["metadatas"], dados["documents"]), key=lambda par: par[0].get("chunk", 0))
    return [{"chunk": meta.get("chunk"), "texto": doc} for meta, doc in pares]


def query(text: str, k: int = None):
    """Retorna os k trechos mais relevantes para a pergunta (k padrão: config.TOP_K_DEFAULT)."""
    collection = _get_collection()
    k = k or config.TOP_K_DEFAULT
    total = collection.count()
    if total == 0:
        return []
    embedding = _get_model().encode([text], normalize_embeddings=True).tolist()
    results = collection.query(query_embeddings=embedding, n_results=min(k, total))

    hits = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({"texto": doc, "fonte": meta.get("source"), "chunk": meta.get("chunk"), "score": 1 - dist})
    return hits
