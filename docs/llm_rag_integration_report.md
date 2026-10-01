# LLM/RAG 통합 보고서

작성 기준 브랜치: `merge/llm-rag-integration`
기준 커밋: `origin/develop` (`c92e609`)
AI 소스 브랜치: 요청서의 `feature/llm+rag`는 원격에 없어서 실제 존재하는
`origin/feature/rag+llm` (`6491d3b`)을 사용했다. 원격 push는 수행하지 않았다.

## 1. Branch 비교

### develop의 기존 RAG/LLM 구조

- `backend/services/docent_service.py`가 `ai.rag.docent.Docent`를 직접 import한다.
- 최초 설명은 `ai.rag.gold_store.get_cached_description()`을 먼저 시도하고,
  cache miss이면 `Docent.describe(artifact_id, visitor_type=...)`를 호출한다.
- 후속 질문은 Backend SQLite에서 최근 3턴을 읽어
  `Docent.chat(artifact_id, question, visitor_type=..., history=...)`에 전달한다.
- 기존 AI는 `ai/rag/data.py`, `retrieval.py`, `index.py`의 자체 Gold/card,
  BM25/vector 혼합 검색과 `ai/rag/ollama.py`의 직접 HTTP client를 사용했다.
- 기존 평가는 `ai/rag/evaluate.py`와 `data/eval/emuseum_questions.jsonl`을 사용했다.

### feature/rag+llm 구조

- `ai/rag/gold_loader.py`: 완성된 chunk JSONL을 검증하고 `relic_label`로 직접 조회한다.
- `ai/rag/document_builder.py`: Gold 한 행을 LangChain `Document` 하나로 만든다.
- `ai/rag/embeddings.py`: YAML의 한 embedding model을 문서와 query에 공통 사용한다.
- `ai/rag/vector_store.py`: Gold `chunk_id`를 Chroma ID로 유지한다.
- `ai/rag/retriever.py`: Chroma 검색 결과를 `chunk_id`, `relic_label`, `content`,
  `metadata`, `score`, `distance`로 정규화한다.
- `ai/rag/chat.py`: 최초 설명은 exact Gold lookup, 모든 후속 질문은 실제 Retriever를 사용한다.
- `ai/llm/client.py`: YAML에 따라 Ollama 또는 Transformers backend를 호출한다.
- `ai/llm/evaluation/retrieval_eval.py`: 서비스와 같은 `ai.rag.retriever.retrieve()`로
  Recall@1/3/5와 MRR을 계산한다.

### 주요 차이

develop은 `artifact_id`와 자체 card/parent abstraction을 사용하지만 feature는
`relic_label`, artifact-unit Gold chunk, LangChain Document, Chroma를 사용한다.
따라서 Backend를 변경하지 않고 `artifact_id → accession_no/relic_label` 변환 및
기존 반환 객체를 복원하는 AI facade가 필요했다.

feature의 현재 커밋은 전체 history를 메모리에 저장하되 최근 N턴만 prompt에 넣었고,
요청서에 명시된 누적 summary는 구현되어 있지 않았다. 이번 통합에서 feature 세션
구조를 확장해 오래된 메시지를 summary에 한 번만 반영하도록 보완했다.

feature 설정이 요구하는 `data/gold/gold0929.jsonl`과 Chroma 파일도 원격 브랜치에는
커밋되어 있지 않았다. develop 서비스의 7개 유물이 즉시 동작하도록 `data/metadata.csv`를
feature schema의 artifact-unit chunk 7개로 변환한 통합 Gold를 포함했다. feature에서
사용했다는 전체 4,269개 Gold는 별도로 확보해야 30개 원본 평가셋 전체를 재현할 수 있다.

## 2. 제거한 기존 RAG 파일

| 파일 | 기존 역할 | 제거 이유 |
|---|---|---|
| `ai/rag/ask.py` | 기존 질의 CLI | feature chat CLI로 교체 |
| `ai/rag/build_gold.py` | develop Gold 생성 | feature Gold schema/loader로 교체 |
| `ai/rag/data.py` | 기존 card/Gold 객체 | feature `gold_loader.py`로 교체 |
| `ai/rag/evaluate.py` | 기존 평가 | feature Recall 평가로 교체 |
| `ai/rag/generate.py` | 기존 답변 생성 | `ai/llm/client.py`와 `ai/rag/chat.py`로 교체 |
| `ai/rag/generate_descriptions.py` | 사전 설명 생성 | 최초 요청 시 exact Gold + LLM 흐름으로 교체 |
| `ai/rag/index.py` | 기존 index 구축 | Chroma 구축 script로 교체 |
| `ai/rag/retrieval.py` | 기존 BM25/vector 검색 | feature Chroma Retriever로 교체 |
| `ai/rag/text.py` | 기존 검색 전처리 | 새 pipeline에서 미사용 |
| `ai/rag/prompts.py` | 기존 prompt | `ai/llm/prompts.py`로 교체 |
| `ai/llm/build_human_eval.py` | 기존 model 비교 자료 생성 | 현재 서비스/evaluation과 무관 |
| `ai/llm/compare_models.py` | 기존 model 비교 | feature model/config 흐름으로 교체 |
| `ai/llm/judge_models.py` | 기존 judge 실행 | feature model/config 흐름으로 교체 |
| `ai/llm/ollama_client.py` | 이전 단일 prompt client | `ai/llm/client.py`로 교체 |
| `scripts/check_docent_prompt.py` | 삭제된 Gold/prompt용 검사 | 새 schema와 불일치 |
| `scripts/check_docent_routes.py` | 기존 rule router 검사 | 모든 후속 질문이 새 Retriever를 쓰도록 교체 |
| `scripts/demo_vision_rag.py` | 기존 parent/card demo | 삭제된 develop RAG 객체에 의존 |

기존 model 비교 결과 JSON/Markdown도 실행 코드와 함께 제거했다. 반면 Backend가 실제로
import하는 `ai/rag/docent.py`, `gold_store.py`, `ollama.py`의 파일 경로는 유지하되 내부는
새 구현으로 연결하는 compatibility code로 완전히 교체했다.

## 3. feature에서 반영한 파일

| 파일 | 역할 |
|---|---|
| `ai/llm/configs/base.yaml` | Gold, embedding, Chroma, top-k, history/summary, LLM 생성 옵션 |
| `ai/llm/client.py` | Ollama/Transformers 공통 생성 진입점 |
| `ai/llm/prompts.py` | 설명, 후속 질문, query rewrite, summary prompt |
| `ai/llm/transformers_backend.py` | 선택적 로컬/Hugging Face 모델 실행 |
| `ai/llm/chat.py` | CLI와 `DocentChatService` 생성 |
| `ai/llm/rag_chain.py` | feature 서비스 공개 import |
| `ai/rag/config.py` | YAML merge/path/값 검증 |
| `ai/rag/gold_loader.py` | Gold schema 검증, cache, label exact lookup |
| `ai/rag/document_builder.py` | artifact-unit Document와 metadata 생성 |
| `ai/rag/embeddings.py` | 공통 Hugging Face embedding |
| `ai/rag/vector_store.py` | persistent Chroma build/open/검증 |
| `ai/rag/retriever.py` | 서비스와 평가가 공유하는 유일한 Retriever 함수 |
| `ai/rag/session.py` | thread-safe session, recent history, 누적 summary 상태 |
| `ai/rag/chat.py` | 최초 설명, query rewrite, 후속 RAG, multi-turn orchestration |
| `ai/rag/scripts/build_vector_db.py` | Gold로 Chroma 구축 |
| `ai/rag/scripts/smoke_retrieval.py` | 실제 Chroma 검색 smoke test |
| `ai/rag/scripts/smoke_multiturn.py` | multi-turn smoke test |
| `ai/llm/evaluation/retrieval_eval.py` | Recall@K/MRR 계산 |
| `ai/llm/evaluation/evaluate_retriever.py` | 평가 CLI |
| `ai/llm/evaluation/evalset/example_retrieval_eval.json` | feature 원본 30개 평가 표본 |
| `ai/rag/tests/*` | 외부 모델 없는 pipeline/Transformers 계약 테스트 |

통합을 위해 추가한 AI 자산은 다음과 같다.

- `ai/rag/scripts/build_integration_gold.py`: develop 7개 유물을 feature schema로 변환
- `data/gold/gold0929.jsonl`: artifact-unit 통합 Gold 7 chunks
- `ai/llm/evaluation/evalset/integration_retrieval_eval.json`: 현재 포함 Gold용 5 queries

## 4. 새로 작성한 Compatibility Layer

### `ai/rag/docent.py`

Backend가 기대하는 인터페이스:

```python
Docent.describe(artifact_id, visitor_type=...) -> Answer
Docent.chat(artifact_id, question, visitor_type=..., history=...) -> (Answer, route)
```

adapter 동작:

1. `data/metadata.csv`의 `artifact_id → accession_no`를 읽는다.
2. accession number를 새 pipeline의 `relic_label`로 전달한다.
3. `describe()`는 `DocentChatService.describe_relic()`로 연결한다.
4. `chat()`은 Backend가 준 최근 history를 feature in-memory session의 tail과 대조해
   같은 대화를 찾고 `DocentChatService.answer_follow_up()`로 연결한다.
5. 새 결과 dict를 기존 `Answer.answer`, `Answer.sources`, route 객체로 변환한다.
6. Chroma는 `_LazyChromaStore`로 후속 질문 때만 열어 최초 설명이 DB 없이도 가능하다.

Backend 계약에는 AI session_id parameter가 없으므로 adapter가 history tail을 이용한다.
프로세스 재시작 후에는 Backend가 전달하는 최근 history로 새 AI session을 시작하며,
재시작 전의 in-memory summary 자체는 복구할 수 없다.

### `ai/rag/gold_store.py`

기존 사전 생성 설명 cache는 더 이상 source of truth가 아니다. 항상 명시적 cache miss인
`GoldDataMissing`을 반환해 Backend의 기존 fallback 경로가 새 `Docent.describe()`를 호출하게 한다.

### `ai/rag/ollama.py`

Backend가 catch하는 `OllamaError` 타입을 유지한다. adapter가 LLM/Chroma runtime 오류를
이 타입으로 변환하므로 기존 Backend는 503 응답 계약을 유지한다.

## 5. 수정하지 않은 Frontend / Backend

`git diff origin/develop -- frontend backend` 결과는 비어 있다. endpoint, router,
controller/service, schema, SQLite 코드와 Frontend API client는 변경하지 않았다.

Frontend 계약은 다음과 같다.

- `POST /api/v1/docent/description`: `{artifact_id, visitor_type}`
- `POST /api/v1/docent/chat`: `{artifact_id, visitor_type, session_id?, question}`
- `GET /api/v1/docent/chat/{session_id}`
- 응답은 기존 `DescriptionResponse`, `ChatResponse`, `ChatHistoryResponse` 그대로다.

## 6. 최종 RAG Pipeline

```text
data/gold/gold0929.jsonl
→ ai.rag.gold_loader.load_gold()
→ ai.rag.document_builder.build_documents()
→ ai.rag.embeddings.get_embedding()
→ ai.rag.vector_store.build_chroma()/open_chroma()
→ ai.rag.retriever.retrieve()
→ ai.rag.chat.DocentChatService
→ ai.llm.client.generate_chat()
→ ChatOllama 또는 ai.llm.transformers_backend.generate_answer()
```

Gold 한 행이 한 artifact chunk이고 `Document.id == metadata["chunk_id"] == Chroma ID`다.

## 7. 최초 유물 설명 흐름

```text
frontend/src/api/docent.ts::fetchDescription()
→ backend/routers/docent.py::describe_artifact()
→ backend/services/docent_service.py::fetch_description()
→ ai.rag.docent.Docent.describe(artifact_id)
→ metadata.csv에서 relic_label 변환
→ ai.rag.chat.DocentChatService.describe_relic()
→ ai.rag.gold_loader.get_relic_records_by_label()
→ ai.llm.client.generate_chat()
→ 기존 DescriptionResponse
```

`describe_relic()`은 Retriever를 호출하지 않고 같은 `relic_label`의 Gold record를 직접 사용한다.

## 8. 후속 질문 흐름

```text
frontend/src/api/docent.ts::sendChat()
→ backend/routers/docent.py::chat()
→ backend/services/docent_service.py::send_chat_message()
→ ai.rag.docent.Docent.chat()
→ DocentChatService.answer_follow_up()
→ DocentChatService.rewrite_query()
→ ai.rag.retriever.retrieve()
→ Chroma.similarity_search_with_score()
→ _format_retrieval()로 LLM context 구성
→ ai.llm.client.generate_chat()
→ 기존 ChatResponse
```

후속 질문은 종류와 관계없이 Retriever를 호출한다. 결과에는 `chunk_id`, `relic_label`,
`content`, 전체 `metadata`, cosine `distance`, `score=1-distance`가 보존된다.

## 9. Multi-turn 구조

- 전체 recent message 저장: `ai/rag/session.py::ChatSession.history`
- summary 저장: `ChatSession.summary`
- 이미 요약한 경계: `ChatSession.summarized_message_count`
- 밀려난 메시지 처리: `InMemorySessionStore.context_window()`
- summary 생성: `DocentChatService._conversation_context()`과
  `ai.llm.prompts.SUMMARY_SYSTEM_PROMPT`
- context 구성: `ai.rag.chat._format_conversation()`
- 설정: `chat.history_turns`, `chat.summary_enabled`, `chat.summary_max_chars`

새 요청 직전에 최근 N턴 밖의 아직 요약되지 않은 메시지만 기존 summary와 함께 요약한다.
최종 prompt는 `summary + recent N turns + current question`을 포함한다.

## 10. Retriever Evaluation

- 실행 파일: `ai/llm/evaluation/evaluate_retriever.py`
- feature 원본 query/정답: `ai/llm/evaluation/evalset/example_retrieval_eval.json`
- 현재 7-chunk 실행 query/정답:
  `ai/llm/evaluation/evalset/integration_retrieval_eval.json`
- ground truth 위치: 각 item의 `relevant_chunk_ids`
- loader: `ai.llm.evaluation.retrieval_eval.load_evaluation()`
- Retriever 호출: `evaluate()` 내부의 `ai.rag.retriever.retrieve()`
- top-k 반환: `retrieve()`의 정규화된 dict list
- chunk ID 추출: `retrieved_ids = [result["chunk_id"] for result in results]`
- Recall@1/3/5: `KS = (1, 3, 5)`와 `evaluate()`의 intersection 계산
- 결과 저장: CLI `--output`으로 지정한 JSON. 권장 위치는
  `ai/llm/evaluation/results/retrieval_eval.json`

실행 명령:

```bash
uv run python ai/llm/evaluation/evaluate_retriever.py \
  --config ai/llm/configs/base.yaml \
  --dataset ai/llm/evaluation/evalset/integration_retrieval_eval.json \
  --output ai/llm/evaluation/results/retrieval_eval.json
```

Chatbot과 평가는 모두 `ai.rag.retriever.retrieve()`를 import한다. 별도 평가 Retriever는 없다.

## 11. Dependency 변경

`pyproject.toml`에 다음 AI runtime package를 추가하고 `uv.lock`을 갱신했다.

- `chromadb`
- `langchain-chroma`
- `langchain-core`
- `langchain-huggingface`
- `langchain-ollama`
- `pyyaml`
- `sentence-transformers`

선택적 `hf` extra에는 `transformers`, `accelerate`, `bitsandbytes`, `torchao`를 추가했다.
develop의 Torch, Vision, FastAPI, HTTP, multipart 등 기존 package는 제거하지 않았다.
기존 RAG만 사용하던 `kiwipiepy`, `rank-bm25`, `hanja`는 `requirements-rag.txt`에서 제거했다.

## 12. End-to-End Flow

```text
Frontend fetchDescription()/sendChat()
→ develop FastAPI /api/v1/docent/*
→ develop docent_service
→ ai.rag.docent compatibility facade
→ DocentChatService
→ exact Gold lookup(최초) 또는 shared retrieve()(후속)
→ persistent Chroma
→ generate_chat()
→ develop DescriptionResponse/ChatResponse
→ Frontend
```

## 13. 실행 검증 결과

### Dependency / import

- `UV_CACHE_DIR=/tmp/merge_uv_cache uv lock`: 성공, 177 packages resolve
- `UV_CACHE_DIR=/tmp/merge_uv_cache uv sync`: 성공, 145 packages 설치
- `uv run python -m compileall -q ai backend scripts`: 성공
- `git diff --check`: 최종 재검사 대상으로 수행

### Case 1: 최초 유물 설명

- 외부 모델 없는 `Docent` facade test: 성공
- Backend `fetch_description()` + 실제 SQLite schema + 새 facade: 성공
- `artifact_id=bon002789`이 `본관 2789`로 변환되고 기존 `DescriptionResponse` 반환 확인

### Case 2: 후속 질문

- Backend `send_chat_message()` 2회: 성공
- fake store가 매 요청마다 호출되어 Retriever call 2회 확인
- 반환 source에 검색 `chunk_id` 포함 확인

### Case 3: Multi-turn

- 동일 Backend session으로 2회 왕복, SQLite history 4 messages 확인
- `history_turns=1` 테스트에서 오래된 message의 summary 반영 및
  `summarized_message_count` 증가 확인

### Case 4: Retriever evaluation

- 소형 deterministic embedding + 실제 Chroma build/open + shared Retriever로 실행
- 7 documents / 5 queries
- Recall@1 = 0.8, Recall@3 = 1.0, Recall@5 = 1.0
- 이 수치는 연결 검증용 deterministic embedding 결과이며 BAAI/bge-m3 품질 수치가 아니다.

### Case 5: 잘못된 입력

- 없는 artifact는 adapter `ArtifactNotFound`를 통해 Backend 404 계약으로 변환됨
- 빈 질문은 crash 없이 기존 Backend가 처리 가능한 오류로 변환됨
- 검색 결과가 빈 list여도 `_format_retrieval()`이 `(관련 검색 자료 없음)` context를 사용함

### Test suite / Frontend

- `uv run python -m unittest discover -s ai/rag/tests -v`: 27/27 성공
- `npm ci && npm run build` (`frontend/`): 성공, 28 modules build
- Frontend와 Backend source diff: 없음

### 확인하지 못한 범위

- Ollama binary는 있지만 `127.0.0.1:11434` 서버가 실행 중이지 않아 실제
  `exaone3.5:7.8b` inference는 수행하지 못했다.
- `BAAI/bge-m3` cache와 production Chroma가 없어 대형 모델 다운로드/실제 embedding은
  수행하지 않았다. Chroma 계약은 deterministic embedding으로 실제 저장/검색까지 확인했다.
- FastAPI `TestClient`는 이 환경에서 lifespan의 `run_in_threadpool()` 진입 중 정지했다.
  동일 현상이 trivial `anyio.to_thread.run_sync(lambda: 1)`에도 재현되어 AI 통합과 무관한
  실행 환경 threadpool 문제로 판정했다. 대신 같은 router가 호출하는 Backend service,
  schema, SQLite 경로를 직접 왕복 검증했다.
- feature 원본 전체 4,269-chunk Gold가 Git에 없으므로 원본 30-query 평가 전체는 실행하지 못했다.

## 14. 최종 실행 방법

1. 환경 생성 및 dependency 설치

   ```bash
   uv sync
   # Transformers 직접 실행이 필요할 때만
   uv sync --extra hf
   ```

2. AI 설정

   `ai/llm/configs/base.yaml`에서 embedding, Chroma, top-k, history/summary, LLM을 확인한다.
   다른 YAML은 `DOCENT_CONFIG` 환경변수로 지정할 수 있다.

3. Gold 준비

   저장소의 7개 서비스 유물은 이미 준비되어 있다. 재생성하려면:

   ```bash
   uv run python ai/rag/scripts/build_integration_gold.py
   ```

   전체 feature 데이터가 필요하면 공유 저장소의 4,269-chunk 파일을
   `data/gold/gold0929.jsonl`에 놓는다.

4. Embedding / Chroma 준비

   ```bash
   uv run python ai/rag/scripts/build_vector_db.py \
     --config ai/llm/configs/base.yaml --rebuild
   ```

5. Ollama/LLM 준비

   ```bash
   ollama serve
   ollama pull exaone3.5:7.8b
   ```

   embedding은 기본값 `BAAI/bge-m3`를 Hugging Face에서 처음 한 번 다운로드한다.

6. Backend 실행

   ```bash
   uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

7. Frontend 실행

   ```bash
   cd frontend
   npm ci
   VITE_USE_MOCK=false npm run dev
   ```

8. Chatbot CLI

   ```bash
   uv run python ai/llm/chat.py --relic-label "본관 2789" --interactive
   ```

9. Retriever evaluation

   ```bash
   uv run python ai/llm/evaluation/evaluate_retriever.py \
     --dataset ai/llm/evaluation/evalset/integration_retrieval_eval.json \
     --output ai/llm/evaluation/results/retrieval_eval.json
   ```

## 최종 상태

- develop Frontend/Backend source는 그대로 유지했다.
- develop의 중복 RAG/LLM 실행 구현은 제거했다.
- feature의 Gold/Embedding/Chroma/Retriever/LLM/evaluation을 source of truth로 사용한다.
- Backend의 기존 import와 함수 signature는 AI compatibility facade가 유지한다.
- 최초 설명은 label exact lookup, 후속 질문은 shared Chroma Retriever를 사용한다.
- multi-turn은 summary + recent N messages + current query 구조다.
- 원격 push는 수행하지 않았다.
