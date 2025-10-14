"""Simple BM25 search over parsed documents.

This provides a lightweight local semantic search without external deps.
It builds an index from `backend/data/parsed/*.json` using simple tokenization
and computes BM25 scores for queries.
"""
import os
import json
import math
import re
from collections import defaultdict

BASE = os.path.dirname(__file__)
PARSED_DIR = os.path.join(BASE, "data", "parsed")
INDEX_FILE = os.path.join(BASE, "data", "bm25_index.json")

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str):
    if not text:
        return []
    toks = [t.lower() for t in TOKEN_RE.findall(text)]
    # simple Korean particle stripping for common josa (이/가/은/는/을/를/야/아)
    particles = set(['이','가','은','는','을','를','야','아'])
    norm = []
    for t in toks:
        norm.append(t)
        # if token ends with a common particle and length>2, also add stripped form
        if len(t) > 2 and t[-1] in particles:
            norm.append(t[:-1])
    return norm


class BM25Index:
    def __init__(self):
        self.N = 0
        self.avgdl = 0.0
        self.doc_len = {}  # docid -> length
        self.tf = {}  # docid -> {term: freq}
        self.df = defaultdict(int)  # term -> doc freq
        self.docs = {}  # docid -> title

    def build(self):
        files = [f for f in os.listdir(PARSED_DIR) if f.endswith('.json')]
        N = 0
        total_len = 0
        for fname in files:
            pid = fname[:-5]
            path = os.path.join(PARSED_DIR, fname)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    parsed = json.load(f)
            except Exception:
                continue
            title = parsed.get('title') or ''
            content = parsed.get('content') or ''
            ocr = parsed.get('ocr_text') or ''
            text = title + ' ' + re.sub('<[^>]+>', ' ', content) + ' ' + ocr
            toks = tokenize(text)
            N += 1
            total_len += len(toks)
            self.docs[pid] = title
            self.doc_len[pid] = len(toks)
            freqs = defaultdict(int)
            for t in toks:
                freqs[t] += 1
            self.tf[pid] = freqs
            for t in freqs.keys():
                self.df[t] += 1
        self.N = N
        self.avgdl = (total_len / N) if N else 0.0

    def save(self):
        data = {
            'N': self.N,
            'avgdl': self.avgdl,
            'doc_len': self.doc_len,
            'tf': self.tf,
            'df': dict(self.df),
            'docs': self.docs,
        }
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def load(self):
        if not os.path.exists(INDEX_FILE):
            return False
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.N = data.get('N', 0)
        self.avgdl = data.get('avgdl', 0.0)
        self.doc_len = data.get('doc_len', {})
        self.tf = {k: {tk: int(tv) for tk, tv in v.items()} for k, v in data.get('tf', {}).items()}
        self.df = defaultdict(int, {k: int(v) for k, v in data.get('df', {}).items()})
        self.docs = data.get('docs', {})
        return True

    def score(self, query: str, k1=1.5, b=0.75, top_k=5):
        q_toks = [t for t in tokenize(query) if len(t) > 0]
        if not q_toks or self.N == 0:
            return []
        # compute idf
        idf = {}
        for t in set(q_toks):
            df = self.df.get(t, 0)
            idf[t] = math.log(1 + (self.N - df + 0.5) / (df + 0.5))

        scores = {}
        for pid, freqs in self.tf.items():
            dl = self.doc_len.get(pid, 0)
            score = 0.0
            for t in q_toks:
                if t not in idf:
                    continue
                f = freqs.get(t, 0)
                denom = f + k1 * (1 - b + b * (dl / self.avgdl if self.avgdl else 0))
                score += idf[t] * (f * (k1 + 1)) / (denom if denom != 0 else 1)
            if score > 0:
                scores[pid] = score
        items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return items


_global_index = None

def get_index():
    global _global_index
    if _global_index is None:
        idx = BM25Index()
        loaded = idx.load()
        if not loaded:
            idx.build()
            try:
                idx.save()
            except Exception:
                pass
        _global_index = idx
    return _global_index


def search(query: str, top_k: int = 5):
    idx = get_index()
    return idx.score(query, top_k=top_k)
