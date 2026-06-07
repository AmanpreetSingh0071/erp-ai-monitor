# Research Findings Log

**Project:** Autonomous ERP Integration Failure Detection and Diagnosis — A Hybrid Agentic Approach Combining Isolation Forest, Rule-Based Detection and Retrieval-Augmented Generation
**Module:** 7COM1086 — MSc AI and Robotics Project
**Author:** Amanpreet Ahluwalia (23089700)
**Supervisor:** Vitoria Wilkinson

---

## How to use this log

Append a new entry every time an experiment is run, a bug is fixed, or a design
decision is made. Each entry records *what changed*, *the numbers*, and most
importantly *what it taught* — the last part is what matters at IPR and viva.
Keep raw outputs in `evaluation/runs/<date>-<tag>/` so earlier results are never
overwritten. Commit after each entry so the git log timestamps the progression.

Entry tags: `[INFRA]` engineering/deployment, `[RQ1]` routing & calibration,
`[RQ2]` RAG knowledge-base size, `[RQ3]` detection, `[ADMIN]` supervision/process.

---

## Milestone summary (quick reference)

| Date | Area | Outcome |
|------|------|---------|
| 2026-06-03 | [ADMIN] | DPP topic confirmed suitable by supervisor; dataset clarification added |
| 2026-06-04 | [INFRA] | LangGraph 4-node agent built and running locally |
| 2026-06-04 | [INFRA] | Fixed RETRIEVER import bug (None copied at import time) |
| 2026-06-05 | [INFRA] | Fixed missing load_dotenv (DATABASE_URL not read) |
| 2026-06-05 | [INFRA] | Fixed WatchFiles infinite reload loop |
| 2026-06-05 | [INFRA] | Fixed Render memory crash with concurrency semaphore |
| 2026-06-07 | [RQ3] | Three-config detection results — clear precision/recall tradeoff |
| 2026-06-07 | [RQ1] | Routing + calibration analysis — LLM confidence is uninformative |

---

## Entries

### 2026-06-03 — [ADMIN] DPP finalised and dataset point clarified
**Context.** Supervisor confirmed the topic direction is suitable. Her one query
was whether the 50-scenario dataset was large enough for *training*.
**Action.** Clarified in the methodology that the 50 cases are an *evaluation*
set only; the Isolation Forest is trained separately on a larger synthetic
distribution of normal operational data. Also removed AI-style phrasing from the
DPP (third-person self-reference, "represents the original contribution",
padding such as "in operational domains").
**Learned.** The evaluation-vs-training distinction is central and must stay
explicit in every later writeup, or the dataset size invites criticism.
**Next.** Email DPP to supervisor before Canvas submission (deadline 8 June).

---

### 2026-06-04 — [INFRA] LangGraph agent built
**Action.** Implemented a 4-node graph: retrieve_context → diagnose →
route_decision → log_to_db. Routing thresholds: ≥0.85 AUTO_REMEDIATE,
≥0.60 INVESTIGATE, <0.60 ESCALATE.
**Learned.** The agent layer is the part that operationalises RQ1; the routing
thresholds are a design parameter to be justified, not a given.

---

### 2026-06-04 — [INFRA] Bug: RETRIEVER imported as None
**Symptom.** `'NoneType' object has no attribute 'invoke'` on every agent run.
**Cause.** `from rag_root_cause import RETRIEVER` copied the value at import
time, before `init_rag()` had assigned it, so the agent held a stale `None`.
**Fix.** Import the module (`import ... as _rag`) and reference `_rag.RETRIEVER`
at call time so the initialised value is used.
**Learned.** Module-level singletons initialised after import must be referenced
through the module, not copied by name. Worth a sentence in the implementation
chapter on initialisation ordering in the agent pipeline.

---

### 2026-06-05 — [INFRA] Bug: DATABASE_URL not set
**Symptom.** DB migration and worker failed with "DATABASE_URL not set" despite
a populated `.env`.
**Cause.** `load_dotenv()` was missing from the backend entry point, so the
`.env` was never read.
**Fix.** Added `load_dotenv()` at the top of `backend/main.py`.
**Learned.** Environment loading must happen before any module reads env vars.

---

### 2026-06-05 — [INFRA] Bug: WatchFiles infinite reload loop
**Symptom.** Server restarted continuously; RAG re-initialised every few seconds.
**Cause.** `--reload` watched the whole tree including `.venv`; dependency files
(and HuggingFace model downloads) triggered endless reloads.
**Fix.** For testing, run without `--reload`; when reloading is needed, scope it
with `--reload-dir backend --reload-dir services --reload-dir configs`.
**Learned.** Auto-reload must exclude the virtual environment and model caches.

---

### 2026-06-05 — [INFRA] Bug: Render instance crash under load
**Symptom.** Live backend (Render free tier, 512 MB) died after ~3 concurrent
transactions; RAG retrieval time spiked from <2 s to ~38 s before the instance
was killed and restarted.
**Cause.** Three agents running simultaneously exhausted RAM (torch +
transformers + FAISS + model all resident), causing disk swap then OOM.
**Fix.** Added `threading.Semaphore(1)` so agents run one at a time.
**Learned.** Memory, not CPU, is the binding constraint for this stack on
constrained hosting. Relevant to any deployment/limitations section. A managed
tier with ≥2 GB would remove the constraint for a live demo.

---

### 2026-06-07 — [RQ3] Three-configuration detection results
**Setup.** 50-case labelled ground truth (44 anomalies across 6 failure
categories + 6 normals, of which 3 are "noisy" false-positive traps that trip a
rule threshold but are benign). Isolation Forest trained on a synthetic normal
distribution shaped as an L-region (low retry OR low delay = normal).

**Results.**

| Config | Precision | Recall | F1 | FPR |
|--------|-----------|--------|------|------|
| A — rules only | 93.6% | 100.0% | 96.7% | 50.0% |
| B — IF + rules | 100.0% | 72.7% | 84.2% | 0.0% |
| C — full agent | 95.7% | 100.0% | **97.8%** | 33.3% |

**Learned.**
- Rules alone maximise recall but over-flag: hard thresholds cannot tell a benign
  maintenance-window delay from a real SLA breach (50% FPR).
- Adding the Isolation Forest eliminates false positives (0% FPR) but over-corrects,
  dropping recall to 72.7% by also vetoing genuine boundary anomalies.
- The full agent keeps full recall *and* cuts FPR to 33% by reading the error
  signature semantically. Case EVAL-048 ("planned nightly batch window") is the
  proof: the semantic layer correctly returned NORMAL where neither rules nor the
  IF could. This single case justifies the architecture.
- **RQ3 answer (provisional):** the hybrid does not dominate on all metrics; it
  resolves the precision/recall tradeoff that the two numeric methods cannot, and
  the semantic layer is what produces the net F1 gain.
**Artefacts.** `results_detection.csv`, `llm_cache.json`.

---

### 2026-06-07 — [RQ1] Routing and confidence-calibration analysis
**Setup.** Config C routing compared against expected routing; added a 3×3
confusion matrix and a confidence-calibration check. Two prompt versions tested:
v1 (abstract rules) and v2 (few-shot worked examples).

**Results.**

| Prompt | Routing accuracy | Behaviour |
|--------|------------------|-----------|
| v1 (abstract) | 30.4% | Everything collapsed into INVESTIGATE |
| v2 (few-shot) | 45.7% | Everything collapsed into AUTO_REMEDIATE |

v2 confusion matrix (rows = expected, cols = predicted):

```
                 AUTO_R   INVEST   ESCALA
AUTO_REMEDIATE       16        0        0
INVESTIGATE          10        5        0
ESCALATE              9        4        0
```

Confidence calibration (v2): mean confidence when CORRECT = 0.87, when WRONG =
0.88, separation = −0.01. Confidence values barely vary (0.80–0.95).

**Learned.**
- The accuracy rise from 30%→46% is misleading. The model did not improve; it
  swapped which bucket it over-uses, anchoring on whichever class the prompt
  foregrounds. The ESCALATE column is all zeros in *both* versions — the agent
  never escalates.
- Confidence carries no signal: it reports ~0.87–0.88 whether right or wrong, so
  thresholding on confidence cannot separate good decisions from bad ones.
- Most serious: 9 cases that should ESCALATE were routed to AUTO_REMEDIATE —
  i.e. the system would autonomously act on revoked credentials and a 3-hour
  peak outage. This is the worst real-world failure mode and belongs in the
  discussion of autonomous-routing risk.
- **RQ1 answer (provisional):** raw llama-3.1-8b-instant confidence is not a
  reliable basis for autonomous routing. Its confidence is uncalibrated and its
  routing collapses toward the prompt-salient class. This is a substantive
  finding, not a failure to hide.
**Artefacts.** `results_routing.csv`, confusion matrix above.
**Next.** Test threshold-based routing directly (apply 0.85/0.60 thresholds to
the confidence score) to confirm — as predicted — that it also fails, completing
the RQ1 argument. Consider a larger model or an explicit calibration step as a
comparison point.

---

## Open threads / TODO

- [ ] [RQ1] Confidence-threshold routing experiment (expected to also fail — document it)
- [ ] [RQ2] RAG knowledge-base size experiment at 10 / 30 / 50 incidents
- [ ] [RQ1] Optional: compare a larger LLM to test whether calibration improves with scale
- [ ] [INFRA] Decide on Render tier for a stable live demo at viva
- [ ] [ADMIN] Confirm Tuesday supervision slot; bring dashboard + this log
