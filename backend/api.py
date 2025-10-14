"""Simple FastAPI app to serve parsed notice data for downstream ChatBot.

Endpoints:
- GET /posts -> list known posts (from index.json)
- GET /posts/{post_id} -> return parsed JSON for a post
- GET /search?q=... -> simple substring search over titles and content

Run: `uvicorn api:app --reload --host 127.0.0.1 --port 8000` from `backend/`.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import os
import json
from pydantic import BaseModel
from bs4 import BeautifulSoup
import re
import os
import requests as http_requests
# embeddings/LLM integration removed in rollback to earlier stable behavior

app = FastAPI(title="KKU CS Notices API")

# CORS: allow local frontend origins during development. Adjust in production.
# During development allow all origins to avoid CORS issues. In production
# restrict this to known origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = os.path.dirname(__file__)
INDEX_PATH = os.path.join(BASE, "data", "index.json")
PARSED_DIR = os.path.join(BASE, "data", "parsed")


def load_index():
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@app.get("/posts")
def list_posts(limit: int = 50):
    idx = load_index()
    # idx is a mapping post_id -> meta; convert to a list sorted by fetched_at desc
    items = list(idx.items())
    items.sort(key=lambda kv: kv[1].get("fetched_at", 0), reverse=True)
    results = [{"id": k, **v} for k, v in items[:limit]]
    return {"count": len(results), "results": results}


@app.get("/posts/{post_id}")
def get_post(post_id: str):
    path = os.path.join(PARSED_DIR, f"{post_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="post not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@app.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = 20):
    idx = load_index()
    results = []
    ql = q.lower()
    # Basic query normalization and synonym expansion for Korean common paraphrases
    # Small local map: map token -> list of variants to consider in scoring
    SYNONYMS = {
        '불이익': ['불이익', '제한', '불이익이', '불이익을', '불이익은'],
        '빌리': ['빌리', '빌려', '대여', '대여하다', '대여가능'],
        '빌릴': ['빌릴', '대여'],
        '누구': ['누구', '누구야', '누구인지', '누가'],
    }
    for post_id, meta in idx.items():
        try:
            path = os.path.join(PARSED_DIR, f"{post_id}.json")
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            title = (parsed.get("title") or "")
            content = (strip_html(parsed.get("content") or "") or "").lower()
            ocr = (parsed.get("ocr_text") or "").lower()
            if ocr:
                content = content + "\n" + ocr
            if ql in title.lower() or ql in content:
                results.append({"id": post_id, "title": title, "url": meta.get("url")})
        except Exception:
            continue
        if len(results) >= limit:
            break
    return {"count": len(results), "results": results}


class ChatRequest(BaseModel):
    question: str
    top_k: int = 5


def strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def extract_relevant_sentences(text: str, q: str, max_sentences: int = 3):
    # naive: split into sentences and pick those containing any keyword token
    q_tokens = [t.lower() for t in re.findall(r"\w+", q) if len(t) > 2]
    if not q_tokens:
        return []
    sents = re.split(r'(?<=[.!?])\s+', text)
    scored = []
    for s in sents:
        low = s.lower()
        score = sum(1 for t in q_tokens if t in low)
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_sentences]]


@app.post("/chat")
def chat(req: ChatRequest):
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")

    # reuse search to find candidate posts
    idx = load_index()
    candidates = []
    ql = q.lower()
    for post_id, meta in idx.items():
        try:
            path = os.path.join(PARSED_DIR, f"{post_id}.json")
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            title = (parsed.get("title") or "")
            content_html = parsed.get("content") or ""
            content = strip_html(content_html)
            # include OCR text if available
            ocr = parsed.get("ocr_text") or ""
            if ocr:
                # append OCR text to searchable content
                content = content + "\n" + ocr
            # simple score: occurrence count in title + content
            score = title.lower().count(ql) * 3 + content.lower().count(ql)
            # synonym expansion scoring
            for key, variants in SYNONYMS.items():
                if key in ql:
                    for v in variants:
                        score += title.lower().count(v) * 2
                        score += content.lower().count(v)
            # add heuristic: token matches
            for tok in re.findall(r"\w+", ql):
                if len(tok) > 1:
                    if tok in title.lower():
                        score += 2
                    score += content.lower().count(tok)
            if score > 0:
                candidates.append((score, post_id, title, content[:400], content))
        except Exception:
            continue

    # if no exact matches, fallback to substring search over title/content
    if not candidates:
        for post_id, meta in idx.items():
            try:
                path = os.path.join(PARSED_DIR, f"{post_id}.json")
                with open(path, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                title = (parsed.get("title") or "")
                content_html = parsed.get("content") or ""
                content = strip_html(content_html)
                if any(tok in content.lower() or tok in title.lower() for tok in re.findall(r"\w+", ql) if len(tok) > 2):
                    candidates.append((1, post_id, title, content[:400], content))
            except Exception:
                continue

    # Special-case: if the question asks '누구' (who), try to match names directly
    if any(x in ql for x in ['누구', '누가', '누구야']):
        for post_id, meta in idx.items():
            try:
                path = os.path.join(PARSED_DIR, f"{post_id}.json")
                with open(path, 'r', encoding='utf-8') as f:
                    parsed = json.load(f)
                title = (parsed.get('title') or '').lower()
                writer = (parsed.get('writer') or parsed.get('WRITER_NM') or '')
                content = strip_html(parsed.get('content') or '').lower()
                # find possible name tokens in question
                for tok in re.findall(r"\w+", ql):
                    if len(tok) > 1 and tok in title:
                        candidates.append((2, post_id, title, content[:400], content))
                    if len(tok) > 1 and tok in content:
                        candidates.append((1, post_id, title, content[:400], content))
                    if writer and tok in writer.lower():
                        candidates.append((3, post_id, title, content[:400], content))
            except Exception:
                continue

    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = candidates[: req.top_k ]
    # If not enough candidates from keyword/OCR matching, fall back to local BM25
    if len(chosen) < req.top_k:
        try:
            from search import search as bm25_search
            need = req.top_k - len(chosen)
            bm = bm25_search(q, top_k=need)
            for item in bm:
                # item may be (pid, score) or (score, pid)
                if isinstance(item[0], str):
                    pid = item[0]
                    score = float(item[1]) if len(item) > 1 else 0.0
                else:
                    pid = item[1]
                    score = float(item[0])
                if any(pid == c[1] for c in chosen):
                    continue
                try:
                    path = os.path.join(PARSED_DIR, f"{pid}.json")
                    with open(path, 'r', encoding='utf-8') as f:
                        parsed = json.load(f)
                    title = parsed.get('title') or ''
                    full = strip_html(parsed.get('content') or '') + '\n' + (parsed.get('ocr_text') or '')
                    snippet = full[:400]
                    chosen.append((score, pid, title, snippet, full))
                except Exception:
                    continue
        except Exception:
            pass
    # If still no chosen candidates, try a more aggressive BM25 fetch
    if not chosen:
        try:
            from search import search as bm25_search
            bm = bm25_search(q, top_k=req.top_k)
            for score, pid in bm:
                try:
                    path = os.path.join(PARSED_DIR, f"{pid}.json")
                    with open(path, 'r', encoding='utf-8') as f:
                        parsed = json.load(f)
                    title = parsed.get('title') or ''
                    full = strip_html(parsed.get('content') or '') + '\n' + (parsed.get('ocr_text') or '')
                    snippet = full[:400]
                    chosen.append((float(score), pid, title, snippet, full))
                except Exception:
                    continue
        except Exception:
            pass

    # (rollback) No semantic/embedding fallback in this stable version.
    # If no candidates were found via keyword/ocr matching above, we return
    # that no related post was found.

    answer_parts = []
    sources = []
    for score, post_id, title, snippet, full in chosen:
        sent = extract_relevant_sentences(full, q, max_sentences=3)
        if sent:
            excerpt = " ".join(sent)
        else:
            excerpt = snippet
        src = idx.get(post_id, {}).get("url")
        # include score and excerpt to emphasize relevance
        sources.append({"id": post_id, "title": title, "url": src, "score": int(score), "excerpt": excerpt})
        answer_parts.append(f"[{title}] {excerpt}")
    # dedupe sources by URL and remove falsy urls
    seen = set()
    deduped = []
    for s in sources:
        u = s.get('url')
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)
        deduped.append(s)
    sources = deduped

    # Only show up to two most relevant sources to the user; keep full list
    # internally for LLM/context if needed.
    display_sources = sources[:2]

    if not answer_parts:
        # As a last resort, try a direct BM25 fetch and return its snippet
        try:
            from search import search as bm25_search
            bm = bm25_search(q, top_k=1)
            if bm:
                score, pid = bm[0]
                path = os.path.join(PARSED_DIR, f"{pid}.json")
                with open(path, 'r', encoding='utf-8') as f:
                    parsed = json.load(f)
                title = parsed.get('title') or ''
                full = strip_html(parsed.get('content') or '') + '\n' + (parsed.get('ocr_text') or '')
                snippet = full[:800]
                return {"answer": snippet, "sources": [{"id": pid, "title": title, "url": parsed.get('_source_url')}], "llm": False}
        except Exception:
            pass
        return {"answer": "관련 공지를 찾지 못했습니다.", "sources": [], "llm": False}

    # Simple aggregation: join parts
    answer_text = "\n\n".join(answer_parts)

    # If an OpenAI API key is provided via environment, call the Chat Completions
    # endpoint to produce a natural, concise answer in Korean using the
    # extracted excerpts as context. Otherwise return the rule-based answer.
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        clean = re.sub(r"https?:\\/\\/\\S+", "", answer_text)
        return {"answer": clean, "sources": display_sources, "llm": False}

    # Build the prompt with context from sources
    system_msg = (
        "당신은 대학 학과 공지사항에 대해 학생이 질문하면 정확하고 간결하게 요약해주는 도우미입니다."
        "출처를 항상 명시하고, 필요한 경우 '참고' 형식으로 링크를 제공하세요. 응답은 한국어로 작성하세요."
    )
    # Compose a user message containing the question and the gathered excerpts
    ctx_parts = []
    for s in sources:
        pid = s.get("id")
        title = s.get("title")
        url = s.get("url")
        excerpt = s.get("excerpt") or ""
        # include the parsed text for each source if available (prefer full parsed content)
        try:
            path = os.path.join(PARSED_DIR, f"{pid}.json")
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            text = strip_html(parsed.get("content") or "")
            ocr = parsed.get("ocr_text") or ""
            full_text = (text + "\n" + ocr).strip()
            if full_text:
                excerpt_full = full_text[:1200]
            else:
                excerpt_full = excerpt
        except Exception:
            excerpt_full = excerpt
        ctx_parts.append(f"[{pid}] {title}\nURL: {url}\n{excerpt_full}\n")

    user_msg = f"질문: {q}\n\n다음은 관련 공지들의 발췌입니다:\n\n" + "\n---\n".join(ctx_parts) + "\n\n위 출처만을 사용하여 간결하게(한두 문단) 답변하고, 반드시 출처를 1~2개 명시하세요. 출처가 불충분하면 '관련 공지를 찾지 못했습니다.'라고 응답하세요."

    # Use retrieval-augmented generation: retrieve top documents via BM25
    try:
        from search import search as bm25_search
        # always try to retrieve top_k docs
        top_docs = bm25_search(q, top_k=req.top_k)
    except Exception:
        top_docs = []

    if not top_docs:
        # nothing retrieved: fallback to rule-based snippet or not found
        clean = re.sub(r"https?:\\/\\/\\S+", "", answer_text)
        if clean.strip():
            return {"answer": clean, "sources": display_sources, "llm": False}
        return {"answer": "관련 공지를 찾지 못했습니다.", "sources": [], "llm": False}

    # Build source contexts for LLM
    ctx_parts = []
    src_list = []
    for rank, item in enumerate(top_docs, start=1):
        try:
            # bm25.search may return (pid, score) or (score, pid); detect
            if isinstance(item[0], str):
                pid = item[0]
                score = float(item[1]) if len(item) > 1 else 0.0
            else:
                pid = item[1]
                score = float(item[0])
            path = os.path.join(PARSED_DIR, f"{pid}.json")
            with open(path, 'r', encoding='utf-8') as f:
                parsed = json.load(f)
            title = parsed.get('title') or ''
            url = parsed.get('_source_url') or parsed.get('url') or idx.get(pid, {}).get('url')
            full = strip_html(parsed.get('content') or '') + '\n' + (parsed.get('ocr_text') or '')
            excerpt = (full or '')[:1200]
            ctx_parts.append(f"[{rank}] {title}\nURL: {url}\n{excerpt}\n")
            src_list.append({"id": pid, "title": title, "url": url})
        except Exception:
            continue

    # Compose strict prompt: force usage of provided sources only
    system_msg = (
        "당신은 건국대학교 공지사항을 기반으로 학생 질문에 정확하고 간결하게 답변하는 도우미입니다. "
        "반드시 아래에 제공된 출처의 발췌만 사용하고, 출처 외의 정보를 만들어내지 마세요. "
        "응답은 한국어로 작성하세요. 다음과 같이 정확한 JSON 객체만 반환하세요:\n"
        "{\"answer\": \"(간결한 한국어 답변)\", \"sources\": [\"출처 URL 1\", \"출처 URL 2\"]}\n"
        "출처에 근거가 없으면 {\"answer\": \"관련 공지를 찾지 못했습니다.\", \"sources\": []} 를 반환하세요."
    )
    user_msg = f"질문: {q}\n\n다음은 검색된 출처들입니다:\n\n" + "\n---\n".join(ctx_parts) + "\n\n위 출처만 사용하여 요청한 형식의 JSON으로 간결히 응답하세요."

    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        # no key: return aggregated snippets and sources
        agg = '\n\n'.join([c.split('\n',2)[-1][:400] for c in ctx_parts[:2]])
        return {"answer": agg, "sources": src_list[:2], "llm": False}

    payload = {
        'model': 'gpt-3.5-turbo',
        'messages': [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': user_msg},
        ],
        'max_tokens': 300,
        'temperature': 0.0,
    }
    headers = {'Authorization': f'Bearer {openai_key}', 'Content-Type': 'application/json'}
    try:
        resp = http_requests.post('https://api.openai.com/v1/chat/completions', json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        llm_text = data.get('choices', [])[0].get('message', {}).get('content', '').strip()
        # Try to parse JSON from model output
        try:
            import json as _json
            parsed = _json.loads(llm_text)
            answer = parsed.get('answer') if isinstance(parsed, dict) else llm_text
            sources_out = parsed.get('sources') if isinstance(parsed, dict) else [s.get('url') for s in src_list[:2]]
            return {"answer": answer, "sources": sources_out, "llm": True}
        except Exception:
            # not valid JSON — fall back to raw text but still return sources
            cleaned = re.sub(r"https?:\\/\\/\\S+", "", llm_text)
            return {"answer": cleaned, "sources": src_list[:2], "llm": True}
    except Exception as e:
        agg = '\n\n'.join([c.split('\n',2)[-1][:400] for c in ctx_parts[:2]])
        return {"answer": agg, "sources": src_list[:2], "llm": False, 'error': str(e)}
