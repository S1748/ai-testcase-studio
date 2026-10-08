"""知识库服务：分块、向量化入库、检索、删除。

向量存 ChromaDB（嵌入模式，本地文件），文本与元数据存 SQLite，两边用 chroma_id 对齐。
collection 按「项目 + embedding 模型」隔离，避免更换模型后新旧向量维度混杂。
"""

import hashlib
import os
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.llm import embed_texts
from app.services.settings_service import RuntimeModelConfig, get_project_runtime_config

# 支持环境变量覆盖，便于自动化测试隔离向量数据
CHROMA_DIR = Path(os.environ.get("AITC_CHROMA_DIR", "") or BASE_DIR / "data" / "chroma")

# 分块参数：每块目标 200~500 字，过长段落按句子切
MAX_CHUNK_CHARS = 500
MIN_CHUNK_CHARS = 20

# 检索参数
DEFAULT_TOP_K = 5
SIMILARITY_THRESHOLD = 0.35  # 余弦相似度低于该值的分块视为不相关，不注入

_client = None


def _get_client():
    global _client
    if _client is None:
        import chromadb

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _embedding_configured(config: RuntimeModelConfig) -> bool:
    return bool(config.embedding_base_url and config.embedding_api_key and config.embedding_model)


def _use_pseudo_embedding(config: RuntimeModelConfig) -> bool:
    """Mock 模式且未配置 embedding 时，用本地伪向量让链路可跑通（仅用于开发调试）。"""
    return config.use_mock_llm and not _embedding_configured(config)


def _pseudo_embed(texts: list[str]) -> list[list[float]]:
    """基于字符 trigram 哈希的确定性伪向量（64 维），仅供 mock 模式调试。"""
    dim = 64
    result = []
    for text in texts:
        vec = [0.0] * dim
        for i in range(len(text) - 2):
            bucket = int(hashlib.md5(text[i:i + 3].encode()).hexdigest(), 16) % dim
            vec[bucket] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        result.append([v / norm for v in vec])
    return result


async def _embed(texts: list[str], config: RuntimeModelConfig) -> list[list[float]]:
    if _use_pseudo_embedding(config):
        return _pseudo_embed(texts)
    # 分批调用，避免单次请求过大（多数供应商限制 batch <= 64）
    vectors: list[list[float]] = []
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        vectors.extend(await embed_texts(texts[i:i + batch_size], config))
    return vectors


def _model_key(config: RuntimeModelConfig) -> str:
    model = config.embedding_model if not _use_pseudo_embedding(config) else "mock"
    return re.sub(r"[^a-zA-Z0-9]", "_", model)[:40] or "default"


def _collection(project_id: int, config: RuntimeModelConfig):
    name = f"p{project_id}_{_model_key(config)}"
    return _get_client().get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


# ---------- 分块 ----------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?;\n])")


def _split_long_text(text: str) -> list[str]:
    """把超长文本按句子边界切成不超过 MAX_CHUNK_CHARS 的片段。"""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    pieces, current = [], ""
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        if current and len(current) + len(sentence) > MAX_CHUNK_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current += sentence
    if current.strip():
        pieces.append(current)
    return pieces


def chunk_markdown(text: str) -> list[dict]:
    """按 Markdown 标题层级分块，每块带标题路径。

    返回 [{"content": str, "heading": "一级 > 二级"}]。
    非 Markdown 的纯文本会整体按段落 + 句子切块（heading 为空）。
    """
    heading_stack: list[tuple[int, str]] = []  # [(level, title)]
    blocks: list[dict] = []
    buffer: list[str] = []

    def heading_path() -> str:
        return " > ".join(t for _, t in heading_stack)

    def flush():
        content = "\n".join(buffer).strip()
        buffer.clear()
        if len(content) < MIN_CHUNK_CHARS:
            return
        path = heading_path()
        for piece in _split_long_text(content):
            piece = piece.strip()
            if len(piece) >= MIN_CHUNK_CHARS:
                blocks.append({"content": piece, "heading": path})

    for line in text.split("\n"):
        match = _HEADING_RE.match(line.strip())
        if match:
            flush()
            level = len(match.group(1))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, match.group(2).strip()))
        else:
            buffer.append(line)
    flush()
    return blocks


# ---------- 入库 / 删除 ----------

async def ingest_document(db: Session, doc: KnowledgeDocument) -> None:
    """分块 → 向量化 → 写入 ChromaDB 与 SQLite。失败时置为 failed 并记录原因。"""
    try:
        model_config = get_project_runtime_config(db, doc.project_id)
        chunks = chunk_markdown(doc.raw_content)
        if not chunks:
            raise ValueError("文档内容过短或无法分块")

        # 向量化时把标题路径拼进文本，提升检索区分度
        texts = [
            f"{c['heading']}\n{c['content']}" if c["heading"] else c["content"]
            for c in chunks
        ]
        vectors = await _embed(texts, model_config)

        collection = _collection(doc.project_id, model_config)
        ids = [f"doc{doc.id}_c{i}" for i in range(len(chunks))]
        collection.add(
            ids=ids,
            embeddings=vectors,
            documents=[c["content"] for c in chunks],
            metadatas=[
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "source_type": doc.source_type,
                    "heading": c["heading"],
                }
                for c in chunks
            ],
        )

        for i, c in enumerate(chunks):
            db.add(KnowledgeChunk(
                document_id=doc.id,
                content=c["content"],
                heading=c["heading"],
                chroma_id=ids[i],
            ))
        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.error_message = ""
        db.commit()
    except Exception as exc:
        db.rollback()
        doc.status = "failed"
        doc.error_message = str(exc)[:500]
        db.commit()
        raise


def delete_document_vectors(doc: KnowledgeDocument) -> None:
    try:
        prefix = f"p{doc.project_id}_"
        for item in _get_client().list_collections():
            name = item if isinstance(item, str) else item.name
            if name.startswith(prefix):
                _get_client().get_collection(name=name).delete(where={"document_id": doc.id})
    except Exception:
        pass  # 向量清理失败不阻塞文档删除（collection 可能因换模型而不存在）


# ---------- 检索 ----------

async def retrieve(
    db: Session,
    project_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = SIMILARITY_THRESHOLD,
    model_config: RuntimeModelConfig | None = None,
) -> list[dict]:
    """按 query 检索项目知识库，返回 [{content, title, heading, source_type, score}]。

    知识库为空或未命中时返回空列表，调用方按"无知识"继续，不应视为错误。
    """
    ready_count = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.project_id == project_id, KnowledgeDocument.status == "ready")
        .count()
    )
    if not ready_count:
        return []

    model_config = model_config or get_project_runtime_config(db, project_id)
    query_vector = (await _embed([query], model_config))[0]
    collection = _collection(project_id, model_config)
    if collection.count() == 0:
        return []

    result = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for content, meta, distance in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        score = 1.0 - distance  # cosine distance → similarity
        if score < threshold:
            continue
        hits.append({
            "content": content,
            "title": (meta or {}).get("title", ""),
            "heading": (meta or {}).get("heading", ""),
            "source_type": (meta or {}).get("source_type", "doc"),
            "score": round(score, 3),
        })
    return hits


def has_ready_knowledge(db: Session, project_id: int) -> bool:
    return (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.project_id == project_id, KnowledgeDocument.status == "ready")
        .count()
        > 0
    )
