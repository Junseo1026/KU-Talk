빌드·실행 가이드 (개발자용)
=============================

이 문서는 `chat_bot` 레포지토리(프론트엔드 + 백엔드)의 로컬 빌드와 실행, 크롤러 및 OCR 관련 준비 방법을 안내합니다.

구성요약
- `backend/` : Python 크롤러, OCR, FastAPI 서버, 스케줄러
- `frontend/`: React + Vite 프론트엔드 (개발서버 및 빌드)

사전 요구사항
- Python 3.10+ (권장)
- Node.js 18+ 및 `npm` 또는 `pnpm`
- 시스템 패키지 (OCR/PDF 처리 시):
  - `tesseract-ocr` 및 한국어 데이터: 예) `sudo apt install tesseract-ocr tesseract-ocr-kor`
  - (PDF 첨부 처리) `poppler-utils`: `sudo apt install poppler-utils`

1) 저장소 준비

```
git clone <repo-url>
cd chat_bot
```

2) 백엔드 설정

- (권장) Python 가상환경 생성 및 활성화
```
python -m venv .venv
source .venv/bin/activate
```

- Python 의존성 설치
```
pip install -r backend/requirements.txt
```

- 환경 변수(.env)
  - `backend/.env` 파일을 편집하여 아래 값을 설정하세요:
    - `OPENAI_API_KEY=sk-...` (LLM/임베딩 사용 시)
    - 프록시 필요 시 `HTTP_PROXY` / `HTTPS_PROXY` 추가

- (옵션) Tesseract / 한국어 학습데이터 설치
```
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-kor poppler-utils
```

3) 백엔드 실행 (API 서버)

```
cd backend
# 환경변수 로드
set -o allexport; source .env; set +o allexport
# 외부에서 접근해야 할 경우 0.0.0.0 바인딩
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

테스트:
- `curl -s http://127.0.0.1:8000/posts | jq .`
- `curl -s -X POST http://127.0.0.1:8000/chat -H 'Content-Type: application/json' -d '{"question":"시험 질의","top_k":3}' | jq .`

4) 프론트엔드 설정 & 실행

- 의존성 설치
```
cd frontend
npm install
# 또는 pnpm install
```

- 개발 서버 실행
```
npm run dev
```

- 접속: 보통 `http://localhost:5173/` 또는 콘솔에 표시된 포트(예: 8081)

주의: 프론트엔드를 외부 IP로 접속하는 경우 백엔드가 `0.0.0.0:8000`으로 바인딩되어 있어야 합니다.

5) 크롤러 사용

- 최신 N 페이지만 크롤링 (예: 3페이지만):
```
cd backend
set -o allexport; source .env; set +o allexport
python run_crawler.py --max-pages 3
```

- 모든 페이지(끝까지) 크롤링:
```
python run_crawler.py --max-pages 0
```

- 결과 위치:
  - 원본 HTML: `backend/data/raw/*.html`
  - 이미지: `backend/data/raw/images/<POST_ID>/*`
  - 파싱 JSON: `backend/data/parsed/<POST_ID>.json`
  - 인덱스: `backend/data/index.json`

6) OCR/첨부 처리

- 크롤러는 이미지 태그를 찾아 자동으로 다운로드하고 OCR을 수행합니다. OCR 결과(`ocr_text`)는 각 parsed JSON에 저장됩니다.
- 수동 재처리(이미 다운받은 게시글 일괄 OCR 업데이트):
```
cd backend
python attach_ocr.py
# 또는 빈 OCR 재시도
python repair_ocr.py
```

7) 임베딩(의미 검색) 생성 (선택)

- OpenAI Embeddings를 사용하려면 `OPENAI_API_KEY`가 필요합니다.
- 임베딩 빌드 스크립트:
```
cd backend
set -o allexport; source .env; set +o allexport
python build_embeddings.py 10   # batch_size=10
```

- 생성 결과는 `backend/data/embeddings.json` 에 저장됩니다.

8) 스케줄링

- Python 스케줄러 사용 (일일 실행 등):
```
cd backend
set -o allexport; source .env; set +o allexport
python scheduler.py
```

- Cron 예시 (매일 08:00 KST 최신 3페이지 크롤):
```
0 8 * * * cd /full/path/to/chat_bot/backend && /bin/bash -lc "set -o allexport; source .env; set +o allexport; python run_crawler.py --max-pages 3 >> cron_crawl.log 2>&1"
```

9) 프록시 네트워크

- 네트워크가 프록시를 요구하면 `backend/.env`에 다음을 추가하세요:
```
HTTP_PROXY=http://proxy.host:3128
HTTPS_PROXY=http://proxy.host:3128
```
- 크롤러는 환경변수를 읽어 requests 세션에 proxy를 적용합니다.

10) 문제 해결(FAQ)

- `Failed to fetch` 에러:
  - 프론트엔드에서 백엔드에 접근할 수 없는 경우 발생합니다.
  - 백엔드를 외부에서 접근 가능하게 하려면 `--host 0.0.0.0` 로 바인딩하거나 `VITE_BACKEND_URL` env를 사용하세요.

- DNS/네트워크 오류(예: NameResolutionError):
  - 서버에서 `curl -I https://cs.kku.ac.kr` 또는 `python3 -c "import socket; print(socket.gethostbyname('cs.kku.ac.kr'))"` 를 사용해 확인하세요.
  - 필요시 `HTTP(S)_PROXY` 설정 또는 네트워크 관리자에게 문의하세요.

11) 주요 파일 위치

- `backend/crawler.py` — 크롤링/파싱/OCR
- `backend/api.py` — FastAPI 서비스
- `backend/attach_ocr.py` / `backend/repair_ocr.py` — OCR 보정
- `backend/embeddings.py` / `backend/build_embeddings.py` — embedding 처리
- `frontend/src/components/ChatInterface.tsx` — 채팅 UI
- `frontend/src/components/ChatMessage.tsx` — 말풍선/출처 UI

라이센스 및 보안
- `OPENAI_API_KEY` 등 민감 정보는 절대 커밋하지 마세요. `.env`를 사용하고 `.gitignore`에 추가하세요.

문의
- 실행 중 에러가 발생하면 관련 콘솔 로그와 `backend/uvicorn.log`, 그리고 `backend/data/`의 일부 파일을 보내주시면 도와드리겠습니다.

