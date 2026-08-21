"""
Build the single plain-text artefact file required by the submission brief.

The brief asks for the project source as one .txt, named in the same style as
the report. Appendix E of the report lists the components and their order, so
this script follows that order and writes a separator header before each file
stating its path and its role.

Run from the repo root:
    python build_artefact_txt.py

Writes: 23089700-Amanpreet-Ahluwalia [artefact].txt
"""

import os
import sys
from datetime import date

OUT = "23089700-Amanpreet-Ahluwalia [artefact].txt"

# Order and roles follow Appendix E of the report.
MANIFEST = [
    ("services/agent/erp_agent.py",
     "Agent graph: four-node LangGraph agent (retrieve, diagnose, route, log)"),
    ("services/ai/rag_root_cause.py",
     "RAG diagnosis: embedding, FAISS retrieval, structured diagnosis"),
    ("services/rule_engine/rule_engine.py",
     "Rule engine: YAML-driven threshold detection"),
    ("configs/rules.yaml",
     "Rule configuration: delay and retry thresholds"),
    ("models/train_anomaly_model.py",
     "Anomaly model training over the L-shaped synthetic normal region"),
    ("backend/main.py",
     "Backend API: FastAPI ingestion, persistence, dashboard endpoints"),
    ("backend/database.py",
     "Backend: database connection and schema helpers"),
    ("frontend/src/App.js",
     "Frontend: React monitoring dashboard"),
    ("ai_knowledge/incidents.txt",
     "Diagnostic knowledge base used for retrieval"),
    ("evaluation/run_experiment.py",
     "Detection experiment: three-configuration harness (RQ3)"),
    ("evaluation/calibration_analysis.py",
     "Calibration experiment: ECE, MCE, Brier, AUROC, Platt scaling (RQ1)"),
    ("evaluation/analyse_routing_thresholds.py",
     "Threshold sweep over cached routing responses (RQ1)"),
    ("evaluation/run_self_consistency.py",
     "Self-consistency experiment: K=5 sampling and agreement (RQ1)"),
    ("evaluation/compare_models.py",
     "Scale comparison across 8B, 70B and 120B (RQ1)"),
    ("evaluation/runs/2026-06-20-rq2/run_rag_experiment.py",
     "Knowledge-base size sweep: retrieval-vote accuracy (RQ2)"),
    ("evaluation/run_ragas_evaluation.py",
     "RAGAS re-evaluation of the diagnosis layer (RQ2)"),
    ("evaluation/build_ground_truth.py",
     "Ground-truth dataset builder"),
    ("evaluation/ground_truth.csv",
     "Labelled evaluation dataset, fifty cases"),
    ("evaluation/realistic_validation.csv",
     "Realistic-syntax validation set, twenty-eight cases (Section 4.6)"),
    ("requirements.txt",
     "Python dependencies"),
    ("README.md",
     "Repository overview"),
]

BAR = "=" * 78


def main():
    if not os.path.exists("backend/main.py"):
        sys.exit("Run this from the repository root.")

    parts, included, missing = [], [], []

    parts.append(f"""{BAR}
PROJECT ARTEFACT SOURCE LISTING
{BAR}

Towards Autonomous ERP Integration Monitoring: An Agentic LLM System for
Confidence-Calibrated Failure Detection, Diagnosis and Autonomous Routing

Amanpreet Ahluwalia, Student ID 23089700
MSc Artificial Intelligence and Robotics, 7COM1086
Generated {date.today().isoformat()}

Files appear in the order given in Appendix E of the report. Each is preceded
by a header stating its path and its role in the system. Virtual environments,
dependency trees, build output, cached model responses and result files are
excluded; the results are reported in the report itself and the raw outputs are
retained in the repository under evaluation/runs/.

{BAR}
CONTENTS
{BAR}
""")

    for path, role in MANIFEST:
        mark = " " if os.path.exists(path) else " [NOT FOUND] "
        parts.append(f"{mark}{path}\n      {role}\n")
        (included if os.path.exists(path) else missing).append(path)

    for path, role in MANIFEST:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
        except UnicodeDecodeError:
            with open(path, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        lines = body.count("\n") + 1
        parts.append(f"\n\n{BAR}\nFILE: {path}\nROLE: {role}\nLINES: {lines}\n{BAR}\n\n{body}")

    parts.append(f"\n\n{BAR}\nEND OF ARTEFACT LISTING\n{BAR}\n")

    text = "".join(parts)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)

    print(f"Wrote {OUT}")
    print(f"  {len(included)} files, {len(text.splitlines()):,} lines, "
          f"{len(text)/1024:.0f} KB")
    if missing:
        print("\n  NOT FOUND, check these paths before submitting:")
        for m in missing:
            print(f"    {m}")


if __name__ == "__main__":
    main()
