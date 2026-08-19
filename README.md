# ERP AI Monitoring System

An end-to-end monitoring platform for ERP integration failures. It detects
anomalous transactions, diagnoses the likely root cause using retrieval-augmented
generation over a knowledge base of past incidents, and routes each case to an
operational action.

Built as an MSc research artefact (University of Hertfordshire, 7COM1086). The
accompanying dissertation reports the evaluation behind it.

## Live demo

- Frontend: https://erp-ai-monitor.vercel.app
- Backend: https://erp-ai-monitor.onrender.com

The backend runs on a free tier and sleeps when idle. First request wakes it and
initialisation takes roughly 50 seconds, most of it loading the embedding model.
Use **Start Backend**, wait for the health indicator, then **Simulate Traffic**.

## What it does

Each transaction passes through three layers in sequence.

**Detection** gates which events reach the agent at all. A YAML rule engine flags
an event when the delay is at least 30 minutes or the retry count is at least 3.
An Isolation Forest trained on synthetic normal traffic gives a second opinion,
with normality shaped as an L-region: an event is normal when either signal is
low, and anomalous only when both rise together.

**Diagnosis** explains what was flagged. A query built from the event is embedded
with `all-MiniLM-L6-v2` and the three closest historical incidents are retrieved
from a FAISS index. A hosted LLM reads that context and returns structured JSON
containing root cause, business impact, recommended fix and a confidence score.

**Routing** converts the confidence into an action: at or above 0.85
auto-remediate, at or above 0.60 investigate, below that escalate to a human.

## Architecture

```
React dashboard (Vercel)
        |
FastAPI backend (Render)
        |
        +-- PostgreSQL: events, diagnoses, routing decisions
        |
        +-- LangGraph agent, four nodes:
              retrieve_context -> diagnose -> route_decision -> log_to_db
                    |                |
              FAISS + MiniLM    Groq-hosted LLM
```

Detection sits in front of the graph as a gate. The agent runs asynchronously on
background threads, serialised by a semaphore because memory rather than CPU is
the binding constraint on a 512 MB instance.

## Implementation notes

- The anomaly detector is trained in-process at startup rather than loaded from a
  pickle, so the served model provably matches the documented parameters:
  600 samples, 200 estimators, contamination 0.05, seed 42.
- The knowledge base is split on incident boundaries before indexing. Without
  this the whole base is a single document and retrieval returns everything.
- Transactions are claimed atomically before processing, so the ingestion path
  and the retry poller cannot both run the same case.
- CPU-only PyTorch, since the deployment target has no GPU and cannot hold the
  CUDA build in memory.

## Repository layout

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI routes, WebSocket manager, background workers |
| `services/agent/` | LangGraph agent: retrieve, diagnose, route, log |
| `services/ai/` | Embedding, FAISS retrieval, structured diagnosis |
| `services/rule_engine/` | YAML-driven threshold detection |
| `models/` | Isolation Forest training over the L-shaped normal region |
| `evaluation/` | Experiment harness for the three research questions |
| `ai_knowledge/` | Incident knowledge base used for retrieval |
| `frontend/` | React monitoring dashboard |

## Example output

```json
{
  "root_cause": "Concurrent NetSuite API requests exceeded the REST API concurrency limit, causing throttling and repeated retries",
  "impact": "Integration queue backs up, transaction processing is delayed, downstream reporting is affected",
  "recommendation": "Add exponential backoff and request queuing, limit concurrent calls, schedule batch jobs off-peak",
  "confidence_score": 0.73
}
```

## Evaluation

The `evaluation/` directory contains the harness behind the reported results:
a three-configuration detection comparison, a knowledge-base size sweep, a
confidence calibration study across three model scales, a self-consistency
extension and a RAGAS re-evaluation. Scripts are seeded and cache model
responses, so runs are reproducible and dated snapshots are kept under
`evaluation/runs/`.

Note that the evaluation harness is self-contained and trains its own detector;
it does not depend on the deployed service.

## Note on models

The project originally used Groq-hosted Llama models. Both were withdrawn from
service in August 2026, and the deployed system now uses `openai/gpt-oss-120b`.
Cached model outputs from the earlier runs are retained in `evaluation/` as the
record of those results.

## Running locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="your_key"
export DATABASE_URL="your_postgres_url"
uvicorn backend.main:app --reload-dir backend --reload-dir services --reload-dir configs
```

Scope `--reload-dir` as shown. Watching the whole tree includes the virtual
environment and model caches, which triggers a reload loop.

## Licence

Submitted as academic coursework. Not licensed for reuse.
