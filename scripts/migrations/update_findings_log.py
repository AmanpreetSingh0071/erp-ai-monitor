"""
Bring FINDINGS_LOG.md up to date.

Three changes:
  1. Line 3 project title: replace the old DPP title with the FPR title, so
     Appendix D matches the title page.
  2. Six new entries covering work done after 26 June: the third model scale,
     the RAGAS evaluation, the realistic-syntax validation, the model
     deprecations, the bootstrap confidence intervals and the artefact
     alignment. Appendix D of the report already describes these.
  3. Six new milestone-table rows, and a refreshed TODO section.

Written in the post-style-pass convention: colons rather than em dashes.
Idempotent, so running it twice changes nothing.

Run from the repo root:
    python update_findings_log.py
"""

import re
import sys
from pathlib import Path

LOG = Path("FINDINGS_LOG.md")

NEW_TITLE = ("**Project:** Towards Autonomous ERP Integration Monitoring: An Agentic LLM "
             "System for Confidence-Calibrated Failure Detection, Diagnosis and Autonomous "
             "Routing")

MILESTONES = """| 2026-08-13 | [RQ1] | Third scale (gpt-oss-120b): ECE 0.331, AUROC 0.565, detection perfect |
| 2026-08-16 | [RQ2] | RAGAS evaluation reproduces the KB-size curve; gain is retrieval precision |
| 2026-08-16 | [RQ1] | Realistic-syntax set: detection holds at 100%, routing fails identically |
| 2026-08-16 | [INFRA] | Groq withdraws llama-3.1-8b-instant; llama-3.3-70b follows by 17 Aug |
| 2026-08-17 | [RQ1] | Bootstrap CIs: all three AUROCs include 0.5, no pairwise difference |
| 2026-08-17 | [INFRA] | Deployed artefact aligned with Appendix B after external review |
"""

ENTRIES = """
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
**Artefacts.** realistic_validation.csv, add_ground_truth_flag.py,
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
**Artefacts.** models/train_anomaly_model.py, fix_artefact_report_mismatch.py,
fix_train_at_startup.py.
"""

NEW_TODO = """## Open threads / TODO

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
"""


def main():
    if not LOG.exists():
        sys.exit("Run this from the repo root (the folder containing FINDINGS_LOG.md).")
    src = LOG.read_text()
    done = []

    # 1. title
    if "Towards Autonomous ERP Integration Monitoring" in src:
        print("  title: already updated")
    else:
        src = re.sub(r"^\*\*Project:\*\*.*$", NEW_TITLE, src, count=1, flags=re.M)
        done.append("title")

    # 2. milestone rows, after the last existing dated row
    if "2026-08-17 | [INFRA]" in src:
        print("  milestones: already added")
    else:
        rows = list(re.finditer(r"^\| 2026-\d\d-\d\d \|.*\|$", src, flags=re.M))
        if not rows:
            sys.exit("Could not find the milestone table.")
        last = rows[-1]
        src = src[: last.end()] + "\n" + MILESTONES.rstrip("\n") + src[last.end():]
        done.append("milestones")

    # 3. entries, before the TODO section
    if "Third model scale (gpt-oss-120b)" in src:
        print("  entries: already added")
    else:
        m = re.search(r"^## Open threads / TODO", src, flags=re.M)
        if not m:
            sys.exit("Could not find the '## Open threads / TODO' heading.")
        src = src[: m.start()] + ENTRIES.strip("\n") + "\n\n---\n\n" + src[m.start():]
        done.append("entries")

    # 4. replace TODO section
    m = re.search(r"^## Open threads / TODO.*\Z", src, flags=re.M | re.S)
    if m and "Practical work is complete" not in m.group(0):
        src = src[: m.start()] + NEW_TODO
        done.append("todo")
    else:
        print("  todo: already updated")

    LOG.write_text(src)
    print(f"\nUpdated FINDINGS_LOG.md ({', '.join(done) if done else 'no changes needed'})")
    print("Check with: head -5 FINDINGS_LOG.md && grep -c '^### 2026' FINDINGS_LOG.md")


if __name__ == "__main__":
    main()
