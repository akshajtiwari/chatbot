import os
import json
import logging
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np
import sqlite3

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel

# Optional imports
try:
    from sentence_transformers import SentenceTransformer
    HAVE_SENTENCE = True
except Exception:
    HAVE_SENTENCE = False

try:
    import redis as _redis
    HAVE_REDIS = True
except Exception:
    _redis = None
    HAVE_REDIS = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    HAVE_SKLEARN = True
except Exception:
    HAVE_SKLEARN = False

# -----------------------
# CONFIG / SETTINGS
# -----------------------
DATABASE_PATH = os.getenv("CHATBOT_DB", "chatbot.db")
VECTOR_DIM = int(os.getenv("VECTOR_DIM", "384"))  # used for SentenceTransformer; TF-IDF determines dim when used
REDIS_URL = os.getenv("REDIS_URL", None)  # e.g. "redis://localhost:6379/0"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))
VECTORS_PATH = os.getenv("VECTORS_PATH", "vectors.npy")
IDS_PATH = os.getenv("IDS_PATH", "vectors.ids.json")
API_KEY = os.getenv("CHATBOT_API_KEY", "testkey")  # replace in prod
MAX_SNIPPET = int(os.getenv("MAX_SNIPPET", "500"))
RUN_SELF_TESTS = os.getenv("RUN_SELF_TESTS", "0") == "1"

# -----------------------
# LOGGING
# -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("chatbot_backend")

# -----------------------
# REDIS (optional)
# -----------------------
r = None
if HAVE_REDIS and REDIS_URL:
    try:
        r = _redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis cache enabled.")
    except Exception as e:
        logger.warning(f"Redis configured but connection failed: {e}. Continuing without Redis.")
else:
    if REDIS_URL:
        logger.warning("Redis library not installed or failed import; caching disabled.")
    else:
        logger.info("Redis not configured; caching disabled.")

def get_cache(key: str):
    if not r:
        return None
    try:
        v = r.get(key)
        return json.loads(v) if v else None
    except Exception:
        return None

def set_cache(key: str, value: dict, ttl: Optional[int] = None):
    if not r:
        return
    try:
        r.set(key, json.dumps(value), ex=ttl or CACHE_TTL_SECONDS)
    except Exception:
        pass

# -----------------------
# DATABASE (SQLite)
# -----------------------
conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS documents(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    title TEXT,
    content TEXT,
    metadata TEXT,
    created_at TEXT,
    valid_until TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS admin_tickets(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT,
    created_at TEXT,
    resolved INTEGER DEFAULT 0,
    metadata TEXT
)
""")
conn.commit()

# -----------------------
# ENCODER: SentenceTransformer preferred; TF-IDF fallback
# -----------------------
encoder_type = "none"
encoder_model = None
tfidf_vectorizer = None
tfidf_dim = None

if HAVE_SENTENCE:
    try:
        encoder_model = SentenceTransformer("all-MiniLM-L6-v2")
        encoder_type = "sentence_transformer"
        logger.info("Using SentenceTransformer encoder (all-MiniLM-L6-v2).")
    except Exception as e:
        logger.warning(f"Failed to load SentenceTransformer: {e}")
        encoder_model = None
        HAVE_SENTENCE = False

if encoder_model is None:
    # fallback to TF-IDF if sklearn available
    if HAVE_SKLEARN:
        encoder_type = "tfidf"
        tfidf_vectorizer = TfidfVectorizer(max_features=1024, stop_words="english")
        # We'll fit TF-IDF lazily when we have docs (see _ensure_tfidf_fitted)
        tfidf_dim = None
        logger.info("Falling back to TF-IDF encoder (sklearn).")
    else:
        logger.info("No SentenceTransformer or sklearn available. Will use deterministic random embeddings as last resort.")
        encoder_type = "random"

def encode_texts(texts):
    """
    Accepts str or list[str].
    Returns numpy array (n, d) dtype float32.
    """
    single = False
    if isinstance(texts, str):
        texts = [texts]
        single = True
    if encoder_type == "sentence_transformer":
        emb = encoder_model.encode(texts, show_progress_bar=False, convert_to_numpy=True).astype("float32")
        # ensure 2D
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        return emb[0] if single else emb
    elif encoder_type == "tfidf":
        _ensure_tfidf_fitted(texts)
        emb = tfidf_vectorizer.transform(texts).toarray().astype("float32")
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        return emb[0] if single else emb
    else:
        # deterministic pseudo-embedding (only if nothing else available)
        arr = []
        for t in texts:
            # simple deterministic pseudo-random vector from hash (not semantic but deterministic)
            seed = abs(hash(t)) % (2**32)
            rng = np.random.RandomState(seed)
            v = rng.rand(VECTOR_DIM).astype("float32")
            arr.append(v)
        emb = np.vstack(arr)
        return emb[0] if single else emb

def _ensure_tfidf_fitted(new_texts=None):
    """
    Fit TF-IDF on existing documents + incoming texts if not fitted yet.
    Called before encoding with TF-IDF.
    """
    global tfidf_vectorizer, tfidf_dim
    if tfidf_vectorizer is None:
        raise RuntimeError("tfidf_vectorizer missing even though encoder_type == 'tfidf'")
    # If not yet fitted, fit on all documents + any provided texts
    # Gather existing contents
    try:
        c.execute("SELECT content FROM documents")
        rows = [r[0] for r in c.fetchall() if r[0]]
    except Exception:
        rows = []
    if new_texts:
        if isinstance(new_texts, str):
            rows.append(new_texts)
        else:
            rows.extend([t for t in new_texts if t])
    if not rows:
        # fallback: fit on provided texts only with small safe default
        rows = new_texts if new_texts else ["dummy"]
    tfidf_vectorizer.fit(rows)
    tfidf_dim = len(tfidf_vectorizer.get_feature_names_out())
    logger.info(f"TF-IDF fitted with dim={tfidf_dim}")

# -----------------------
# NUMPY VECTOR STORE (persistent)
# -----------------------
# Globals:
#   _VECS: np.ndarray (N, D) of L2-normalized vectors
#   _IDS: list[int] length N
_VECS = None
_IDS = []

def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    if mat.ndim == 1:
        mat = mat.reshape(1, -1)
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
    return mat / norms

def _load_store():
    global _VECS, _IDS
    try:
        if os.path.exists(VECTORS_PATH):
            _VECS = np.load(VECTORS_PATH)
            _VECS = _VECS.astype("float32")
        else:
            # default empty
            if encoder_type == "sentence_transformer":
                dims = encoder_model.get_sentence_embedding_dimension() if HAVE_SENTENCE else VECTOR_DIM
            elif encoder_type == "tfidf" and tfidf_vectorizer is not None and tfidf_vectorizer.vocabulary_:
                # we will update dims later
                dims = None
            else:
                dims = VECTOR_DIM
            _VECS = np.empty((0, dims if dims else VECTOR_DIM), dtype="float32")
        if os.path.exists(IDS_PATH):
            with open(IDS_PATH, "r") as f:
                _IDS = json.load(f)
        else:
            _IDS = []
        # normalize if non-empty
        if _VECS is not None and _VECS.size:
            _VECS[:] = _l2_normalize(_VECS)
        logger.info(f"Vector store loaded: {_VECS.shape[0]} vectors.")
    except Exception as e:
        logger.exception(f"Failed to load vector store: {e}")
        _VECS = np.empty((0, VECTOR_DIM), dtype="float32")
        _IDS = []

def _save_store():
    global _VECS, _IDS
    try:
        if _VECS is None:
            return
        np.save(VECTORS_PATH, _VECS.astype("float32"))
        with open(IDS_PATH, "w") as f:
            json.dump(_IDS, f)
    except Exception:
        logger.exception("Failed to persist vector store to disk.")

def add_vector(vec: np.ndarray, doc_id: int):
    global _VECS, _IDS
    if vec.ndim == 1:
        vec = vec.reshape(1, -1)
    vec = _l2_normalize(vec.astype("float32"))
    if _VECS is None or _VECS.size == 0:
        _VECS = vec
    else:
        # If dimensions mismatch (e.g., TF-IDF newly fitted), try to align shapes
        if _VECS.shape[1] != vec.shape[1]:
            # If _VECS is empty in dimension, replace. Otherwise, pad or truncate
            old_dim = _VECS.shape[1]
            new_dim = vec.shape[1]
            if _VECS.shape[0] == 0:
                _VECS = vec
            else:
                # pad smaller to larger with zeros
                if new_dim > old_dim:
                    pad = np.zeros((_VECS.shape[0], new_dim - old_dim), dtype="float32")
                    _VECS = np.hstack([_VECS, pad])
                elif new_dim < old_dim:
                    # truncate existing to new_dim
                    _VECS = _VECS[:, :new_dim]
                # now _VECS and vec are compatible
                _VECS = np.vstack([_VECS, vec])
        else:
            _VECS = np.vstack([_VECS, vec])
    _IDS.append(int(doc_id))
    _save_store()

def query_vector(vec: np.ndarray, top_k: int = 5):
    """
    Return list of {"id": doc_id, "score": float} sorted by score desc.
    """
    if _VECS is None or _VECS.size == 0:
        return []
    if vec.ndim == 1:
        vec = vec.reshape(1, -1)
    q = _l2_normalize(vec.astype("float32"))
    # dot product because both normalized -> cosine similarity
    sims = (_VECS @ q.T).ravel()
    if sims.size == 0:
        return []
    k = min(top_k, sims.shape[0])
    # get top-k indices
    idx = np.argpartition(-sims, k - 1)[:k]
    # sort them
    idx = idx[np.argsort(-sims[idx])]
    out = []
    for i in idx:
        out.append({"id": _IDS[i], "score": float(sims[i])})
    return out

# Load store at import
_load_store()

# -----------------------
# SCHEMAS
# -----------------------
class IngestRequest(BaseModel):
    source: str
    title: Optional[str]
    content: str
    metadata: Optional[Dict[str, Any]] = {}
    valid_until: Optional[str]

class QueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5

class SearchItem(BaseModel):
    id: int
    title: Optional[str]
    text: str
    score: Optional[float]

class QueryResponse(BaseModel):
    query: str
    results: List[SearchItem]
    confidence: float
    fallback: Optional[bool] = False
    fallback_ticket_id: Optional[int] = None

# -----------------------
# APP
# -----------------------
app = FastAPI(title="College Chatbot Backend (Robust)")

# -----------------------
# AUTH
# -----------------------
def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# -----------------------
# INGEST ENDPOINT
# -----------------------
@app.post("/ingest")
def ingest(req: IngestRequest, x_api_key: str = Depends(verify_api_key)):
    if not req.content or not isinstance(req.content, str):
        raise HTTPException(status_code=422, detail="content must be a non-empty string")
    try:
        # persist metadata safe string
        metadata_str = json.dumps(req.metadata or {})
        created_at = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO documents (source,title,content,metadata,created_at,valid_until)
            VALUES (?,?,?,?,?,?)
        """, (req.source, req.title, req.content, metadata_str, created_at, req.valid_until))
        conn.commit()
        doc_id = c.lastrowid

        # encoding
        # If using TF-IDF, ensure it's fitted with existing + this content
        if encoder_type == "tfidf":
            _ensure_tfidf_fitted([req.content])
        vec = encode_texts(req.content)
        add_vector(vec, doc_id)
        logger.info(f"Ingested doc_id={doc_id} (source={req.source})")
        # optionally clear TF-IDF cache? we keep it fitted
        return {"id": doc_id, "message": "Document ingested"}
    except Exception as e:
        logger.exception("Ingest error")
        raise HTTPException(status_code=500, detail=f"Failed to ingest document: {e}")

# -----------------------
# QUERY ENDPOINT
# -----------------------
@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, x_api_key: str = Depends(verify_api_key)):
    if not req.query or not isinstance(req.query, str):
        raise HTTPException(status_code=422, detail="query must be a non-empty string")
    cache_key = hashlib.sha256(req.query.encode()).hexdigest()
    cached = get_cache(cache_key)
    if cached:
        return cached

    try:
        # If TF-IDF and not fitted, fit on existing docs first
        if encoder_type == "tfidf":
            _ensure_tfidf_fitted([req.query])

        vec = encode_texts(req.query)
        vector_results = query_vector(vec, top_k=req.top_k or 5)

        results = []
        for r in vector_results:
            c.execute("SELECT id, title, content FROM documents WHERE id=?", (r["id"],))
            row = c.fetchone()
            if row:
                results.append(SearchItem(id=row[0], title=row[1], text=(row[2] or "")[:MAX_SNIPPET], score=r["score"]))

        confidence = results[0].score if results else 0.0
        fallback = False
        ticket_id = None

        # hybrid: keyword fallback if low confidence
        if confidence < CONFIDENCE_THRESHOLD:
            c.execute("SELECT id, title, content FROM documents WHERE content LIKE ? OR title LIKE ? LIMIT 5",
                      (f"%{req.query}%", f"%{req.query}%"))
            for row in c.fetchall():
                if any(r.id == row[0] for r in results):
                    continue
                results.append(SearchItem(id=row[0], title=row[1], text=(row[2] or "")[:MAX_SNIPPET], score=0.3))

        # If still no confident result, create admin ticket
        if not results or confidence < CONFIDENCE_THRESHOLD:
            fallback = True
            c.execute("INSERT INTO admin_tickets (question, created_at) VALUES (?,?)",
                      (req.query, datetime.utcnow().isoformat()))
            conn.commit()
            ticket_id = c.lastrowid

        response = QueryResponse(query=req.query, results=results, confidence=confidence,
                                 fallback=fallback, fallback_ticket_id=ticket_id)
        set_cache(cache_key, response.dict())
        return response
    except Exception as e:
        logger.exception("Query error")
        raise HTTPException(status_code=500, detail=f"Failed to process query: {e}")

# -----------------------
# SELF-TESTS
# -----------------------
def _run_self_tests():
    logger.info("Running self-tests...")
    # create temp DB + vector files in /tmp (avoid clobbering user data)
    import tempfile, shutil
    tmpdir = tempfile.mkdtemp(prefix="cbot_test_")
    try:
        global DATABASE_PATH, conn, c, VECTORS_PATH, IDS_PATH, _VECS, _IDS
        # switch to temp paths
        old_db = DATABASE_PATH
        old_vectors = VECTORS_PATH
        old_ids = IDS_PATH
        DATABASE_PATH = os.path.join(tmpdir, "test.db")
        VECTORS_PATH = os.path.join(tmpdir, "vectors.npy")
        IDS_PATH = os.path.join(tmpdir, "vectors.ids.json")

        # reset DB
        conn.close()
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS documents(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            content TEXT,
            metadata TEXT,
            created_at TEXT,
            valid_until TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS admin_tickets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            created_at TEXT,
            resolved INTEGER DEFAULT 0,
            metadata TEXT
        )
        """)
        conn.commit()

        # reset vector store in memory
        _VECS = np.empty((0, VECTOR_DIM), dtype="float32")
        _IDS = []

        # ingest a few docs via function calls
        ingest(IngestRequest(source="test", title="Alpha", content="FastAPI tutorial about routing", metadata={}))
        ingest(IngestRequest(source="test", title="Beta", content="How to use transformers for embeddings", metadata={}))
        ingest(IngestRequest(source="test", title="Gamma", content="Database usage in SQLite and backups", metadata={}))

        # query
        resp = query(QueryRequest(query="transformers"), x_api_key=API_KEY)
        assert resp.results, "Self-test failed: no results for 'transformers'"

        resp2 = query(QueryRequest(query="nonexistent topic"), x_api_key=API_KEY)
        assert resp2.fallback, "Self-test failed: fallback ticket not created for unknown query"

        logger.info("Self-tests passed ✅")
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

if __name__ == "__main__":
    if RUN_SELF_TESTS:
        _run_self_tests()
    else:
        import uvicorn
        uvicorn.run("chatbot_backend:app", host="0.0.0.0", port=8000, reload=True)
