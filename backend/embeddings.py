"""Embeddings utilities using OpenAI embeddings API.

Provides functions to build embeddings for parsed documents and perform
semantic search using cosine similarity without external deps.
"""
import os
import json
import time
from typing import Dict, List, Tuple
import requests

BASE = os.path.dirname(__file__)
PARSED_DIR = os.path.join(BASE, "data", "parsed")
EMB_FILE = os.path.join(BASE, "data", "embeddings.json")


def _get_api_key():
    return os.getenv("OPENAI_API_KEY")


def _call_openai_embeddings(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    key = _get_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": texts}
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]


def build_embeddings(batch_size: int = 10):
    files = [f for f in os.listdir(PARSED_DIR) if f.endswith('.json')]
    files.sort()
    mapping: Dict[str, List[float]] = {}
    # load existing to avoid re-computing
    if os.path.exists(EMB_FILE):
        try:
            with open(EMB_FILE, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
        except Exception:
            mapping = {}

    to_process = []
    id_map = []
    for fname in files:
        pid = fname[:-5]
        if pid in mapping:
            continue
        path = os.path.join(PARSED_DIR, fname)
        with open(path, 'r', encoding='utf-8') as f:
            parsed = json.load(f)
        title = parsed.get('title','') or ''
        content = parsed.get('content','') or ''
        # strip tags naive: keep as-is (server-side embedding can accept HTML)
        ocr = parsed.get('ocr_text','') or ''
        text = title + '\n' + content + '\n' + ocr
        # trim length to avoid huge payloads
        text = text[:30000]
        to_process.append(text)
        id_map.append(pid)
        # batch send
        if len(to_process) >= batch_size:
            embs = _call_openai_embeddings(to_process)
            for pid_, emb in zip(id_map, embs):
                mapping[pid_] = emb
            # persist
            with open(EMB_FILE, 'w', encoding='utf-8') as f:
                json.dump(mapping, f)
            to_process = []
            id_map = []
            time.sleep(1)

    if to_process:
        embs = _call_openai_embeddings(to_process)
        for pid_, emb in zip(id_map, embs):
            mapping[pid_] = emb
        with open(EMB_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping, f)

    return mapping


def load_embeddings() -> Dict[str, List[float]]:
    if not os.path.exists(EMB_FILE):
        return {}
    with open(EMB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _cosine(a: List[float], b: List[float]) -> float:
    # simple dot / (||a|| * ||b||)
    sa = 0.0
    sb = 0.0
    dot = 0.0
    for x, y in zip(a, b):
        dot += x * y
        sa += x * x
        sb += y * y
    if sa == 0 or sb == 0:
        return 0.0
    return dot / ((sa ** 0.5) * (sb ** 0.5))


def semantic_search(query: str, top_k: int = 5) -> List[Tuple[float, str]]:
    """Return list of (score, post_id) sorted desc."""
    embs = load_embeddings()
    if not embs:
        raise RuntimeError('embeddings not built; run build_embeddings() first')
    q_emb = _call_openai_embeddings([query])[0]
    results: List[Tuple[float, str]] = []
    for pid, emb in embs.items():
        score = _cosine(q_emb, emb)
        results.append((score, pid))
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_k]

