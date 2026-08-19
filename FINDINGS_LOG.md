# Research Findings Log

**Project:** Towards Autonomous ERP Integration Monitoring: An Agentic LLM System for Confidence-Calibrated Failure Detection, Diagnosis and Autonomous Routing
**Module:** 7COM1086, MSc AI and Robotics Project
**Author:** Amanpreet Ahluwalia (23089700)
**Supervisor:** Vitoria Wilkinson

---

## How to use this log

Append a new entry every time an experiment is run, a bug is fixed, or a design
decision is made. Each entry records *what changed*, *the numbers* and most
importantly *what it taught*: the last part is what matters at IPR and viva.
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
| 2026-06-07 | [RQ3] | Three-config detection results: clear precision/recall tradeoff |
| 2026-06-07 | [RQ1] | Routing + calibration analysis: LLM confidence is uninformative |
| 2026-06-08 | [ADMIN] | DPP submitted on Canvas with project plan |
| 2026-06-08 | [RQ1] | Confidence-threshold routing also fails (45.5%); ESCALATE unreachable |
| 2026-06-13 | [ADMIN] | Supervisor DPP feedback: Gantt with parallel activities, in-text citations, artefact due at FPR |
| 2026-06-20 | [RQ2] | RAG diagnosis 79% vs 18% rule baseline; diminishing returns past ~30 incidents |
| 2026-06-20 | [RQ1] | Calibration study: ECE 0.42, AUROC 0.46; recalibration cannot restore discrimination |
| 2026-06-25 | [RQ1] | Self-consistency weak (AUROC 0.55); model cannot represent ESCALATE |
| 2026-06-26 | [RQ1] | Scale comparison 8B vs 70B: detection fixed, calibration unchanged (AUROC 0.46→0.52) |
| 2026-08-13 | [RQ1] | Third scale (gpt-oss-120b): ECE 0.331, AUROC 0.565, detection perfect |
| 2026-08-16 | [RQ2] | RAGAS evaluation reproduces the KB-size curve; gain is retrieval precision |
| 2026-08-16 | [RQ1] | Realistic-syntax set: detection holds at 100%, routing fails identically |
| 2026-08-16 | [INFRA] | Groq withdraws llama-3.1-8b-instant; llama-3.3-70b follows by 17 Aug |
| 2026-08-17 | [RQ1] | Bootstrap CIs: all three AUROCs include 0.5, no pairwise difference |
| 2026-08-17 | [INFRA] | Deployed artefact aligned with Appendix B after external review |

---

## Entries

### 2026-06-03: [ADMIN] DPP finalised and dataset point clarified
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

### 2026-06-04: [INFRA] LangGraph agent built
**Action.** Implemented a 4-node graph: retrieve_context → diagnose →
route_decision → log_to_db. Routing thresholds: ≥0.85 AUTO_REMEDIATE,
≥0.60 INVESTIGATE, <0.60 ESCALATE.
**Learned.** The agent layer is the part that operationalises RQ1; the routing
thresholds are a design parameter to be justified, not a given.

---

### 2026-06-04: [INFRA] Bug: RETRIEVER imported as None
**Symptom.** `'NoneType' object has no attribute 'invoke'` on every agent run.
**Cause.** `from rag_root_cause import RETRIEVER` copied the value at import
time, before `init_rag()` had assigned it, so the agent held a stale `None`.
**Fix.** Import the module (`import ... as _rag`) and reference `_rag.RETRIEVER`
at call time so the initialised value is used.
**Learned.** Module-level singletons initialised after import must be referenced
through the module, not copied by name. Worth a sentence in the implementation
chapter on initialisation ordering in the agent pipeline.

---

### 2026-06-05: [INFRA] Bug: DATABASE_URL not set
**Symptom.** DB migration and worker failed with "DATABASE_URL not set" despite
a populated `.env`.
**Cause.** `load_dotenv()` was missing from the backend entry point, so the
`.env` was never read.
**Fix.** Added `load_dotenv()` at the top of `backend/main.py`.
**Learned.** Environment loading must happen before any module reads env vars.

---

### 2026-06-05: [INFRA] Bug: WatchFiles infinite reload loop
**Symptom.** Server restarted continuously; RAG re-initialised every few seconds.
**Cause.** `--reload` watched the whole tree including `.venv`; dependency files
(and HuggingFace model downloads) triggered endless reloads.
**Fix.** For testing, run without `--reload`; when reloading is needed, scope it
with `--reload-dir backend --reload-dir services --reload-dir configs`.
**Learned.** Auto-reload must exclude the virtual environment and model caches.

---

### 2026-06-05: [INFRA] Bug: Render instance crash under load
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

### 2026-06-07: [RQ3] Three-configuration detection results
**Setup.** 50-case labelled ground truth (44 anomalies across 6 failure
categories + 6 normals, of which 3 are "noisy" false-positive traps that trip a
rule threshold but are benign). Isolation Forest trained on a synthetic normal
distribution shaped as an L-region (low retry OR low delay = normal).

**Results.**

| Config | Precision | Recall | F1 | FPR |
|--------|-----------|--------|------|------|
| A: rules only | 93.6% | 100.0% | 96.7% | 50.0% |
| B: IF + rules | 100.0% | 72.7% | 84.2% | 0.0% |
| C: full agent | 95.7% | 100.0% | **97.8%** | 33.3% |

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

### 2026-06-07: [RQ1] Routing and confidence-calibration analysis
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
  foregrounds. The ESCALATE column is all zeros in *both* versions: the agent
  never escalates.
- Confidence carries no signal: it reports ~0.87–0.88 whether right or wrong, so
  thresholding on confidence cannot separate good decisions from bad ones.
- Most serious: 9 cases that should ESCALATE were routed to AUTO_REMEDIATE,
  i.e. the system would autonomously act on revoked credentials and a 3-hour
  peak outage. This is the worst real-world failure mode and belongs in the
  discussion of autonomous-routing risk.
- **RQ1 answer (provisional):** raw llama-3.1-8b-instant confidence is not a
  reliable basis for autonomous routing. Its confidence is uncalibrated and its
  routing collapses toward the prompt-salient class. This is a substantive
  finding, not a failure to hide.
**Artefacts.** `results_routing.csv`, confusion matrix above.
**Next.** Test threshold-based routing directly (apply 0.85/0.60 thresholds to
the confidence score) to confirm, as predicted, that it also fails, completing
the RQ1 argument. Consider a larger model or an explicit calibration step as a
comparison point.

---

### 2026-06-08: [ADMIN] DPP submitted on Canvas
**Context.** Supervisor confirmed the DPP was fine to submit and suggested adding
a basic project plan with timescales, milestones and deliverables.
**Action.** Added a short project plan (intro paragraph plus a phase/date/
deliverable table) covering proposal through viva, kept high-level and
forward-looking. Submitted the DPP on Canvas and sent the updated copy to the
supervisor for reference.
**Learned.** The DPP is feedback-only with no marks, so the project plan is mainly
a foundation to expand for the IPR and FPR, where the project-management
reflection does carry weight.
**Next.** Await individual DPP feedback; continue the evaluation work in parallel.

---

### 2026-06-08: [RQ1] Confidence-threshold routing experiment
**Context.** Routing accuracy was being measured by letting the LLM pick a label
directly. RQ1 actually asks about routing on a confidence *threshold*, which had
not yet been tested as a distinct mechanism.
**Action.** Built analyse_routing_thresholds.py: take the cached confidence
scores, discard the LLM's self-chosen label, and apply thresholds
(≥0.85 AUTO_REMEDIATE, ≥0.60 INVESTIGATE, <0.60 ESCALATE). Computed accuracy and
a confusion matrix, then swept the AUTO threshold from 0.50 to 1.00. Pure
analysis over the cache, no new API calls.
**Result (real run, N=44 anomalies).**
- Fixed thresholds (0.85/0.60): 45.5% accuracy (20/44), indistinguishable from
  the 45.7% the LLM scored choosing its own label.
- ESCALATE produced: 0. No confidence value ever fell below 0.60, so the escalate
  branch is structurally unreachable.
- Sweep 0.50→1.00: accuracy stayed in the 34.1%–45.5% band, best 45.5% at 0.825.
- Confusion matrix (rows expected, cols predicted): AUTO 14/2/0, INVESTIGATE
  9/6/0, ESCALATE 9/4/0: 13 escalate-needed cases sent to auto-remediate or
  investigate, none escalated.
**Learned.** The two routing mechanisms perform identically, so the routing rule
was never the problem. The signal is. No threshold choice rescues the approach;
the flat sweep is the visual proof. This is the mechanism RQ1 names, now tested
directly.
**Artefacts.** analyse_routing_thresholds.py, routing_threshold_sweep.png,
results_threshold_routing.csv.
**Next.** Quantify *why* the signal fails → full calibration study.

---

### 2026-06-13: [ADMIN] Supervisor DPP feedback received
**Context.** Individual DPP feedback came back through Canvas (and by email). The
verdict was positive: the RQs, aims and methodology were described as clear and
specific, and a strong start.
**Action.** Noted three points to carry into the IPR and FPR. First, the project
plan should use a Gantt chart that shows parallel activities (for example drafting
the report alongside the practical work) rather than a strict waterfall. Second,
the artefact only needs to be complete by the FPR on 1 September, not the IPR on
20 July: the IPR reports progress so far plus the plan to completion. Third,
there is a difference between references and citations: the reference list is fine
but the body needs in-text Harvard citations. Co-authorship on a future paper was
raised and the supervisor will check UH rules later.
**Learned.** The IPR framing is "progress to date plus plan to finish", not a
finished artefact. The Gantt and the in-text citations are concrete, low-effort
fixes that should be built into the IPR from the start.
**Next.** Build the parallel-activities Gantt and add Harvard citations when
drafting the IPR.

---

### 2026-06-20: [RQ1] Confidence calibration study
**Context.** The qualitative finding ("confidence does not separate correct from
wrong") needed to be made quantitative and grounded in calibration theory.
**Action.** Built calibration_analysis.py: Expected and Maximum Calibration
Error, Brier score, overconfidence, a reliability diagram, the AUROC of
confidence as a predictor of correctness (discrimination), and post-hoc Platt
scaling to test whether recalibration helps. Noted that classical temperature
scaling needs per-class logits, which a self-reported scalar confidence does not
provide, so Platt is the appropriate scalar method.
**Result (real run, N=46).**
- Accuracy 45.7%, mean confidence 87.4% → overconfidence +41.7 points.
- ECE 0.417, MCE 0.547, Brier 0.429 (well-calibrated is ECE < 0.05).
- AUROC 0.461, below 0.5: confidence is, if anything, faintly anti-correlated
  with correctness.
- Reliability diagram non-monotonic: the 0.90-confidence cluster had the *lowest*
  accuracy (31.8%).
- Platt scaling: ECE 0.417 → 0.000, but AUROC stayed at chance (0.46 → 0.54),
  logistic slope negative.
**Learned.** Calibration (scale) and discrimination (ranking) are distinct. Platt
scaling is a monotonic transform, so it can drive calibration error to zero but
cannot manufacture discrimination that is absent, proven empirically by ECE→0
while AUROC stays ~0.5. The deficit is intrinsic to the small model's confidence
signal, not a fixable scaling artefact. This is why routing on its confidence is
unsafe at any threshold.
**Caveats (for limitations).** N=46 with only four distinct confidence values is
small; Platt was fit and evaluated on the same data (a larger set would allow a
train/test split).
**Artefacts.** calibration_analysis.py, reliability_diagram.png,
confidence_histogram.png, calibration_metrics.csv.

---

### 2026-06-20: [RQ2] RAG diagnosis vs rule baseline, and knowledge-base size
**Context.** RQ2 asks whether RAG-grounded diagnosis beats rule-based diagnosis,
and at what knowledge-base size RAG begins to help (DPP specified 10/30/50).
**Action.** Built run_rag_experiment.py with a 60-incident labelled knowledge
base (10 per category) held *separate* from the 50 evaluation cases, with
deliberately distinct wording to prevent leakage. For KB sizes {10,20,30,40,50,
60}, eval cases were diagnosed by TF-IDF retrieval of the top-3 incidents and a
majority-category vote, averaged over 5 random seeds. Random-choice (1/6) and
majority-class baselines stand in for rule-based diagnosis, which cannot identify
category from numeric retry/delay signals.
**Result (mean over 5 seeds).**
- Rule baselines: random 16.7%, majority class 18.2%, i.e. at chance.
- RAG accuracy by KB size: 10→50.0%, 20→62.2%, 30→73.5%, 40→79.5%, 50→79.0%,
  60→81.4%.
- Marginal gain per +10 incidents: 10→20 +12.3, 20→30 +11.4, 30→40 +5.9, then
  flat. Clear knee at KB ≈ 30–40.
- Error bars shrink as KB grows (±4.3 at 10 → ±0.9 at 60).
**Learned.** For diagnosis, RAG is not a marginal gain over rules: it is the
difference between chance (18%) and 79%, because rules cannot distinguish failure
*types* from numeric signals. Returns diminish sharply past ~30 incidents, so
knowledge-base curation effort has a natural stopping point. Small knowledge
bases are not only less accurate but less *stable*, because category coverage
depends on which incidents happen to be included.
**Caveats (for limitations).** Uses TF-IDF retrieval and retrieval-vote diagnosis
rather than the production MiniLM + LLM generation pipeline; the trend is robust
to method. The script has an optional LLM-diagnosis path to confirm on the full
pipeline.
**Artefacts.** run_rag_experiment.py, rag_kb_size_curve.png, results_rag_kbsize.csv.

---

### 2026-06-25: [RQ1] Self-consistency confidence extension
**Context.** Since the model's self-reported confidence is non-discriminative,
tested whether an agreement-based signal (Wang et al., 2022, self-consistency)
does better: query the model K times at temperature > 0 and measure how often it
agrees with itself.
**Action.** Built run_self_consistency.py. For each anomaly case, sampled K=5
routing decisions at temperature 0.7 (every sample cached for reproducibility),
took the modal decision as the prediction and the agreement fraction as the
confidence signal. Added an entropy-based variant and a two-class scoped analysis
restricted to decisions the model can represent (AUTO_REMEDIATE vs INVESTIGATE).
**Result (real run).**
- All 44 cases: accuracy 43.2%, AUROC 0.548 (up from self-reported 0.461). A
  clean monotonic reliability ladder: 0.60→39.1%, 0.80→45.5%, 1.00→50.0%.
- Two-class scoped (31 cases): accuracy 61.3%, AUROC 0.566, steeper ladder
  0.60→56.2%, 0.80→62.5%, 1.00→71.4%.
- Entropy variant gave identical AUROC because no case ever produced a three-way
  split: the model's uncertainty is always binary.
- ESCALATE was sampled exactly once across all 220 samples.
**Learned.** Agreement-based confidence carries more signal than self-reported
confidence (AUROC 0.46 → 0.55), and within the model's representational capacity
the relationship is clear (unanimous agreement → 71% accuracy). But discrimination
is still weak overall, and two independent symptoms confirm the binding
constraint is the model's competence, not the uncertainty mechanism: it cannot
represent ESCALATE, and its disagreement is never diffuse across all three
actions. Combined with the calibration study and the threshold sweep, RQ1 is now
answered from three independent angles, all pointing to the same conclusion.
**Caveats (for limitations).** K=5 gives only five distinct agreement levels;
two-class scoping reduces N to 31. No results-hacking: the full ablation
(all-cases, scoped, entropy) is reported together.
**Artefacts.** run_self_consistency.py, results_self_consistency.csv,
self_consistency_curve.png.

---

### 2026-06-26: [RQ1] Model scale comparison (8B vs 70B)
**Context.** Every RQ1 result so far used llama-3.1-8b-instant. The obvious
question a reader would ask is whether the calibration failure is just a
small-model weakness that a bigger model fixes. To answer it, the Config C and
calibration pipeline was made model-agnostic (a `--model` flag, with each model
writing to its own cache and result files) and re-run on llama-3.3-70b-versatile,
roughly nine times the parameter count.
**Result (real run).**

| Model | N | Accuracy | Mean conf | Overconf | ECE | AUROC | AUROC (Platt) |
|-------|---|----------|-----------|----------|-----|-------|---------------|
| llama-3.1-8b | 46 | 45.6% | 87.4% | +41.7 | 0.417 | 0.461 | 0.539 |
| llama-3.3-70b | 44 | 38.6% | 79.3% | +40.7 | 0.407 | 0.522 | 0.522 |

- Detection (Config C) reached a perfect 100% precision, recall and F1 with 0%
  FPR on the 70B. It correctly classified all three noisy-normal cases as benign,
  where the 8B had caught only one (EVAL-048).
- The 70B finally used the escalate option: EVAL-011 was routed to ESCALATE at
  0.9 confidence. The 8B never escalated once across hundreds of calls.
- Calibration was essentially flat across the 9× size jump: ECE 0.417 → 0.407,
  AUROC 0.461 → 0.522 (still near the 0.5 chance line), overconfidence ~40 points
  in both. The reliability table stayed non-monotonic, and Platt scaling again
  drove ECE to 0.000 while leaving AUROC unchanged.
- Routing accuracy actually fell to 38.6% because the 70B collapsed 40 of 44
  cases into INVESTIGATE: a bucket-collapse effect, not worse discrimination.
**Learned.** Scale fixes *capability*: semantic detection became perfect and the
model could finally represent escalation. But it does almost nothing for
*self-knowledge*. The confidence-calibration failure persists, near-identically,
across a 9× increase in model size. This is the strong form of the RQ1 finding:
the inability to self-assess confidence reliably is intrinsic to LLM
self-reporting, not an artefact of using a small model. It also sharpens the
overall thesis to "scale improves what the model can do, but not how well it
knows what it has done."
**Caveats (for limitations).** Two models is a comparison, not a scaling law; a
third point (for example gpt-oss-120b) would make the trend firmer. The 70B's low
routing accuracy reflects bucket-collapse into INVESTIGATE, so it should not be
read as a regression in capability.
**Artefacts.** run_experiment.py (with `--model`), compare_models.py,
results_routing_llama-3.3-70b-versatile.csv, calibration_metrics_*.csv,
reliability_diagram_llama-3.3-70b-versatile.png.

---

### 2026-08-13: [RQ1] Third model scale (gpt-oss-120b)

**Context.** The 8B-vs-70B comparison had only two points, which an earlier draft
of the report described as showing calibration "essentially unchanged" with scale.
Two points cannot support that. A third model was run to test it.
**Action.** Full Config C and calibration pipeline on openai/gpt-oss-120b via the
existing --model flag, with its own cache and result files.
**Result (real run, N=44).** Accuracy 52.3%, mean confidence 85.4%, overconfidence
+33.1 points, ECE 0.331, MCE 0.442, Brier 0.358, AUROC 0.565. Detection (Config C)
perfect: 100% precision, recall and F1 at 0% FPR. ESCALATE used twice, against once
for the 70B and never for the 8B.
**Learned.** The two-point claim was wrong and had to be corrected in the report.
Across 8B, 70B and 120B, ECE falls 0.417 to 0.407 to 0.331 and AUROC rises 0.461 to
0.522 to 0.565: calibration improves with scale, monotonically, and far too slowly
to matter. At 120B the ECE is still about seven times the 0.05 threshold. The
corrected claim is stronger than the original, not weaker.
**Caveats (for limitations).** The step to 120B crosses model families, so part of
the gain may be architecture rather than size. At N=44 the difference between an
AUROC of 0.46 and 0.57 sits inside the noise band.
**Artefacts.** results_routing_openai_gpt-oss-120b.csv,
calibration_metrics_openai_gpt-oss-120b.csv, compare_models.py.

---

### 2026-08-16: [RQ2] RAGAS evaluation of the diagnosis layer

**Context.** The RQ2 size sweep used a TF-IDF proxy and was scored only against my
own baseline, which makes it hard for anyone else to compare. RAGAS is the standard
framework for evaluating retrieval-augmented systems.
**Action.** Built run_ragas_evaluation.py over the same knowledge base and the same
44 anomaly cases, at KB sizes 10, 30 and 60. Three practical obstacles: RAGAS pulls
LangChain versions that conflict with the agent stack, so it runs from a separate
virtualenv; it imports a langchain-community module that no longer exists, needing a
stub; and Groq rejects n>1, so the judge wrapper needs bypass_n.
**Result (real run, 8B as both generator and judge).**

| KB size | Faithfulness | Context precision | Context recall | Diagnostic accuracy |
|---------|--------------|-------------------|----------------|---------------------|
| 10 | 0.648 | 0.182 | 0.477 | 54.5% |
| 30 | 0.669 | 0.260 | 0.489 | 72.7% |
| 60 | 0.624 | 0.360 | 0.470 | 81.8% |

**Learned.** Diagnostic accuracy of 54.5%, 72.7% and 81.8% reproduces the original
curve (50.0%, 73.6%, 81.4%) from a different pipeline on a different run, so the
finding does not depend on the proxy. Context precision climbing 0.182 to 0.360 is
the coverage mechanism measured directly. Context recall is flat at about 0.47:
top_k is fixed at three, so recall is bounded by what three documents can cover, and
the reference answers include a case-specific analyst note that no generic incident
can support. Faithfulness is flat at 0.62 to 0.67, so better retrieval does not stop
the model padding its explanation. The classification is stronger than the generation.
**Caveats (for limitations).** The judge is the 8B, a weak judge and since withdrawn,
so the run cannot be repeated as-is. Single seed. Answer relevancy was dropped: the
query is a log line rather than a question, which that metric fits poorly.
**Artefacts.** run_ragas_evaluation.py, results_ragas_final.csv,
ragas_kb_size_curve.png.

---

### 2026-08-16: [RQ1] [RQ3] Validation on realistic log syntax

**Context.** Every result so far used the primary set, whose error signatures are
plain-language summaries. That leaves open the objection that the semantic layer
succeeds only because the input is tidy English.
**Action.** Built a separate held-out set of 28 cases using authentic error formats
from Oracle NetSuite documentation and standard integration protocols: SuiteScript
governance codes with stack traces, X12 999 rejections, HTTP statuses, SOAP faults.
Four per category plus four normals, two of them false-positive traps. Added a
--ground-truth flag so output files are namespaced and the primary results cannot be
overwritten. Run on the 70B, the deployed model at the time.
**Result (real run).** Detection (Config C): 100% precision, 100% recall, 100% F1,
0% FPR, identical to the synthetic set, with both false-positive traps correctly
classified. Routing accuracy 37.5% against 38.6% synthetic. The ESCALATE column is
entirely empty: 8 of 24 cases required escalation and none was escalated, with 22 of
24 collapsing into INVESTIGATE. Calibration (N=24): ECE 0.444, MCE 0.478, Brier
0.410, AUROC 0.552, still non-monotonic, Platt again driving ECE to 0.000 with AUROC
unchanged. Eighteen of 24 cases reported exactly 0.80 confidence and were 27.8%
correct.
**Learned.** Detection generalises to realistic error text, which is a genuine
external-validity result for RQ3. Routing does not, and the failure is therefore not
an artefact of clean synthetic wording. On a split of 9, 7 and 8 across the three
actions, a constant classifier predicting the majority action scores 37.5%; the agent
scored 37.5%. One thing did change: on the 8B synthetic run the dominant error sent
escalate-needed cases to AUTO_REMEDIATE, whereas here every one went to INVESTIGATE.
Still wrong, but wrong in the direction of under-reaction rather than over-action,
which changes the risk profile without changing the conclusion.
**Caveats (for limitations).** The set is synthetic, built from documented error
formats rather than sampled from production incidents. N=24 is small, and the 0.92
and 0.95 bins hold one correct case each, which is noise rather than evidence.
**Artefacts.** realistic_validation.csv, scripts/migrations/add_ground_truth_flag.py,
runs/2026-08-16-realistic-validation/.

---

### 2026-08-16: [INFRA] Both Llama models withdrawn mid-project

**Context.** Groq announced the decommissioning of llama-3.1-8b-instant with effect
from 16 August 2026, the model behind the primary RQ1 baseline.
**Action.** Archived the cached model outputs and dated run snapshots to git before
the cutoff. Switched the deployed agent to llama-3.3-70b-versatile, which was already
characterised in the report.
**Result.** By 17 August the 70B had also gone: the deployed agent returned 404
model_not_found on every call, and the models endpoint showed neither Llama chat
model remaining. Switched the agent to openai/gpt-oss-120b, the only one of the three
study models still served and one for which full results already exist.
**Learned.** Two of the three models used in this study ceased to be served within a
month of producing the results. Research built on commercial inference APIs has a
reproducibility half-life measured in months, not years. The cached outputs and dated
snapshots kept since June are now the only complete record of those baselines, which
is the clearest return the reproducibility discipline has paid.
**Artefacts.** llm_cache_*.json, runs/2026-08-16-synthetic-70b/.

---

### 2026-08-17: [RQ1] Bootstrap confidence intervals on the scale comparison

**Context.** The three AUROC values were reported as point estimates and hedged in
prose as a suggestive trend. At N=44 that hedge needed quantifying.
**Action.** Bootstrap resampling, 10,000 iterations per model, over the cached
per-case confidence and correctness values. No new API calls.
**Result (real run).** 8B 0.461, 95% CI [0.294, 0.627]. 70B 0.522, [0.355, 0.688].
120B 0.565, [0.400, 0.725]. Pairwise differences: 70B minus 8B [-0.173, +0.292], 120B
minus 8B [-0.128, +0.333], 120B minus 70B [-0.191, +0.278].
**Learned.** Every interval contains 0.5, so no model's confidence is
distinguishable from chance at the 95% level. Every pairwise difference contains
zero, so the apparent improvement with scale is directional only and not a measured
effect. This strengthens the central claim and correctly weakens the scale claim, and
it is the answer to the obvious examiner question about noise at this sample size.
**Artefacts.** results_routing_*.csv (inputs).

---

### 2026-08-17: [INFRA] Deployed artefact aligned with the documented parameters

**Context.** An external review of the report against the artefact found that the
deployed demonstrator had drifted from Appendix B. Three files disagreed with the
documentation.
**Action.** Verified each claim against the code. models/train_anomaly_model.py
trained on a uniform box with no random seed and default estimators, rather than the
documented L-region with 200 estimators and seed 42. configs/rules.yaml set the retry
threshold to 5 rather than 3, and the rule engine compared with > rather than >=.
The evaluation harness in run_experiment.py was correct on every point, and it trains
its own model in-process, so no reported figure was affected: only the demonstrator
differed.
**Result.** train_anomaly_model.py rewritten to mirror the harness exactly, verified
by comparing predictions on eight test points (identical). The backend now trains the
detector in-process at startup rather than loading a pickle, which also removed a
dependency on a gitignored file of unknown age and a scikit-learn version coupling.
rules.yaml set to 3 and the comparison made inclusive, verified at the boundaries.
**Learned.** Two parallel implementations had grown: a correct evaluation harness and
a demonstrator that quietly drifted. The reported results were never at risk, but an
examiner opening the files named in the manifest would have found them disagreeing
with the parameters table. Worth checking the artefact against the report, not just
the report against itself.
**Artefacts.** models/train_anomaly_model.py, scripts/migrations/fix_artefact_report_mismatch.py,
scripts/migrations/fix_train_at_startup.py.

---

## Open threads / TODO

All three research questions are answered, with RQ1 confirmed across three model
scales and two independently constructed datasets. Practical work is complete.

- [x] [RQ3] Three-configuration detection comparison
- [x] [RQ1] Routing analysis, calibration study, threshold sweep, self-consistency
- [x] [RQ1] Model scale comparison across 8B, 70B and 120B
- [x] [RQ1] Bootstrap confidence intervals
- [x] [RQ2] RAG diagnosis vs rule baseline and knowledge-base size curve
- [x] [RQ2] RAGAS re-evaluation on the full pipeline
- [x] [RQ1] [RQ3] Realistic-syntax validation set
- [x] [INFRA] Deployed artefact aligned with Appendix B
- [ ] [WRITING] FPR (due 1 September): remaining edits to Chapters 4, 6, 7 and 8
- [ ] [ADMIN] Mock demo 27 August; assessed demonstration early September
