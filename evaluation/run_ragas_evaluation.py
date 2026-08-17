"""
RQ2 extension: RAGAS evaluation of the RAG diagnosis pipeline
=============================================================
Re-expresses the RQ2 knowledge-base-size finding in the standard RAG evaluation
metrics (RAGAS) rather than only bespoke diagnostic accuracy.

Metrics
-------
  faithfulness        : is the generated diagnosis grounded in the retrieved
                        incidents, or does the model invent detail?
  answer_relevancy    : does the diagnosis actually address the error signature?
  context_precision   : of the incidents retrieved, how many were relevant?
  context_recall      : did retrieval surface the incidents needed to answer?

context_precision and context_recall speak directly to RQ2: if the KB-size curve
plateaus because retrieval recall saturates, these metrics show it explicitly.

Method
------
- Reuses the SAME 60-incident knowledge base and the SAME TF-IDF top-k retrieval
  as run_rag_experiment.py, imported from that file so there is one source of
  truth and no risk of the two experiments diverging.
- Evaluation cases are the 44 anomalies from ground_truth.csv (error_signature
  as the query, expected_root_cause as the reference).
- For each KB size, the LLM generates a diagnosis grounded ONLY in the retrieved
  context; RAGAS then judges that generation. Generations are cached to disk so
  re-runs cost nothing.

IMPORTANT: install RAGAS in a SEPARATE virtualenv. Its LangChain pins conflict
with the langchain-core / langgraph versions the production agent depends on.

    python -m venv ragas_env
    source ragas_env/bin/activate
    pip install ragas langchain-groq

Three of the four metrics are LLM-only and need nothing further. Answer relevancy
additionally needs an embedding model; install these only if you want it (large,
pulls in torch):

    pip install langchain-huggingface sentence-transformers

Outputs: console table, results_ragas.csv, results_ragas_per_sample.csv,
         ragas_kb_size_curve.png
"""

import os
import csv
import json
import time
import argparse
import hashlib
import importlib.util
from pathlib import Path

import numpy as np
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# -------------------------------------------------------------------
# Reuse the RQ2 knowledge base and category list (single source of truth)
# -------------------------------------------------------------------
def load_rq2_module(path):
    """Import run_rag_experiment.py by path so KB/CATEGORIES are never duplicated."""
    path = Path(path)
    if not path.exists():
        raise SystemExit(
            f"Could not find {path}.\n"
            "Pass --rq2-script with the path to run_rag_experiment.py "
            "(it lives in evaluation/runs/2026-06-20-rq2/)."
        )
    spec = importlib.util.spec_from_file_location("rq2_experiment", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def flatten_kb(KB):
    docs, labels = [], []
    for cat, items in KB.items():
        for t in items:
            docs.append(t)
            labels.append(cat)
    return docs, labels


def load_eval(path, categories):
    """Anomaly cases only: same filter as run_rag_experiment.py."""
    cases = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["expected_root_cause"] in categories:
                cases.append({
                    "case_id": r["case_id"],
                    "signature": r["error_signature"],
                    "category": r["expected_root_cause"],
                    "notes": (r.get("notes") or "").strip(),
                })
    return cases


def retrieve(signature, kb_docs, kb_labels, vectoriser, kb_matrix, top_k):
    q = vectoriser.transform([signature])
    sims = cosine_similarity(q, kb_matrix)[0]
    order = np.argsort(sims)[::-1][:top_k]
    return [kb_docs[i] for i in order], [kb_labels[i] for i in order]


# -------------------------------------------------------------------
# Diagnosis generation (cached)
# -------------------------------------------------------------------
GEN_PROMPT = """You are diagnosing an ERP integration failure.

Error signature:
{signature}

Similar past incidents retrieved from the knowledge base:
{context}

Using ONLY the retrieved incidents above, state the most likely root cause of
this failure and briefly explain why, referring to the evidence in the retrieved
incidents. Do not introduce facts that are not supported by the retrieved text.
Answer in two or three sentences."""


def cache_key(signature, contexts, model):
    blob = model + "||" + signature + "||" + "||".join(contexts)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def generate_answer(llm, signature, contexts, cache, cache_file, model, delay):
    key = cache_key(signature, contexts, model)
    if key in cache:
        return cache[key]

    prompt = GEN_PROMPT.format(
        signature=signature,
        context="\n".join(f"- {c}" for c in contexts),
    )
    attempt = 0
    while True:
        try:
            answer = llm.invoke(prompt).content.strip()
            break
        except Exception as e:
            msg = str(e)
            if ("rate_limit" in msg or "429" in msg) and attempt < 5:
                import re
                wait = 20
                m = re.search(r"try again in ([0-9.]+)s", msg)
                if m:
                    wait = float(m.group(1)) + 1
                print(f"   rate limited, waiting {wait:.0f}s...")
                time.sleep(wait)
                attempt += 1
                continue
            raise

    cache[key] = answer
    json.dump(cache, open(cache_file, "w"), indent=2)
    time.sleep(delay)
    return answer


def write_outputs(summary_rows, per_sample_rows):
    """Write both CSVs from whatever has completed so far."""
    if not summary_rows:
        return
    cols = list(summary_rows[0].keys())
    with open("results_ragas.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in summary_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v)
                        for k, v in r.items()})
    if per_sample_rows:
        with open("results_ragas_per_sample.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(per_sample_rows[0].keys()))
            w.writeheader()
            w.writerows(per_sample_rows)


# -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rq2-script",
                    default="runs/2026-06-20-rq2/run_rag_experiment.py",
                    help="path to run_rag_experiment.py (KB source of truth)")
    ap.add_argument("--ground-truth", default="ground_truth.csv")
    ap.add_argument("--kb-sizes", default="10,30,60",
                    help="comma-separated KB sizes to evaluate")
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0,
                    help="seed for KB subsampling (matches RQ2 seeding)")
    ap.add_argument("--limit", type=int, default=0,
                    help="evaluate only the first N cases (0 = all). Use a small "
                         "value for a smoke test before the full run.")
    ap.add_argument("--model", default="llama-3.3-70b-versatile",
                    help="Groq model that GENERATES the diagnoses under test")
    ap.add_argument("--judge-model", default=None,
                    help="Groq model used as the RAGAS judge. Defaults to "
                         "--model. Set separately to keep generations fixed "
                         "while swapping the judge (useful when the generator "
                         "model has exhausted its daily token quota, or to test "
                         "whether scores depend on judge capability).")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--no-relevancy", action="store_true",
                    help="skip answer relevancy (avoids needing an embedding "
                         "model). The other three metrics are LLM-only.")
    ap.add_argument("--workers", type=int, default=2,
                    help="RAGAS concurrency. Keep low on the Groq free tier.")
    args = ap.parse_args()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY not set.")

    # Imports deferred so the argparse errors above are fast
    from langchain_groq import ChatGroq
    from ragas import evaluate, EvaluationDataset
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.run_config import RunConfig

    rq2 = load_rq2_module(args.rq2_script)
    KB, CATEGORIES = rq2.KB, rq2.CATEGORIES
    docs, labels = flatten_kb(KB)

    cases = load_eval(args.ground_truth, CATEGORIES)
    if args.limit:
        cases = cases[: args.limit]

    kb_sizes = [int(s) for s in args.kb_sizes.split(",")]

    print("RQ2 extension — RAGAS evaluation of RAG diagnosis")
    print("=" * 62)
    print(f"Evaluation cases : {len(cases)} anomalies")
    print(f"Knowledge base   : {len(docs)} incidents, {len(CATEGORIES)} categories")
    print(f"KB sizes         : {kb_sizes}   top_k={args.topk}")
    print(f"Generator model  : {args.model}")
    print(f"Judge model      : {args.judge_model or args.model}\n")

    safe_model = args.model.replace("/", "_")
    cache_file = f"ragas_answers_cache_{safe_model}.json"
    cache = json.load(open(cache_file)) if os.path.exists(cache_file) else {}

    llm = ChatGroq(model=args.model, api_key=api_key, temperature=0)
    judge_name = args.judge_model or args.model
    judge_llm = (llm if judge_name == args.model
                 else ChatGroq(model=judge_name, api_key=api_key, temperature=0))
    # bypass_n: ResponseRelevancy asks for n=strictness completions in one call.
    # Groq rejects n>1, so tell RAGAS to issue n separate calls instead. Without
    # this, answer_relevancy returns NaN.
    judge = LangchainLLMWrapper(judge_llm, bypass_n=True)

    metrics = [
        Faithfulness(llm=judge),
        LLMContextPrecisionWithReference(llm=judge),
        LLMContextRecall(llm=judge),
    ]

    if not args.no_relevancy:
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.metrics import ResponseRelevancy
            embeddings = LangchainEmbeddingsWrapper(
                HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2")
            )
            metrics.append(ResponseRelevancy(llm=judge, embeddings=embeddings))
            print("Metrics: faithfulness, context precision, context recall, "
                  "answer relevancy\n")
        except ImportError:
            print("Metrics: faithfulness, context precision, context recall")
            print("(answer relevancy skipped - no embedding model installed)\n")
    else:
        print("Metrics: faithfulness, context precision, context recall\n")
    run_config = RunConfig(max_workers=args.workers, timeout=300)

    summary_rows = []
    per_sample_rows = []

    for size in kb_sizes:
        rng = np.random.default_rng(args.seed)
        idx = rng.choice(np.arange(len(docs)), size=min(size, len(docs)),
                         replace=False)
        sub_docs = [docs[i] for i in idx]
        sub_labels = [labels[i] for i in idx]

        vec = TfidfVectorizer().fit(sub_docs + [c["signature"] for c in cases])
        kb_matrix = vec.transform(sub_docs)

        print(f"--- KB size {size}: generating diagnoses ---")
        samples, meta = [], []
        for i, c in enumerate(cases, 1):
            contexts, cat_labels = retrieve(
                c["signature"], sub_docs, sub_labels, vec, kb_matrix, args.topk
            )
            answer = generate_answer(llm, c["signature"], contexts, cache,
                                     cache_file, args.model, args.delay)
            # Reference = the labelled root cause plus the analyst note recorded
            # in ground_truth.csv. A bare category name is too terse for
            # context_recall to judge fairly; the note is ground-truth data, not
            # anything invented here.
            reference = (f"The root cause of this failure is "
                         f"{c['category'].replace('_', ' ').lower()}.")
            if c["notes"]:
                reference += f" {c['notes']}"
            samples.append(SingleTurnSample(
                user_input=c["signature"],
                response=answer,
                retrieved_contexts=contexts,
                reference=reference,
            ))
            retrieved_vote = Counter(cat_labels).most_common(1)[0][0]
            meta.append({
                "case_id": c["case_id"],
                "expected": c["category"],
                "retrieved_vote": retrieved_vote,
                "vote_correct": int(retrieved_vote == c["category"]),
            })
            if i % 10 == 0:
                print(f"   {i}/{len(cases)} generated")

        print(f"--- KB size {size}: RAGAS scoring ({len(samples)} samples) ---")
        result = evaluate(
            dataset=EvaluationDataset(samples=samples),
            metrics=metrics,
            run_config=run_config,
            show_progress=True,
        )

        df = result.to_pandas()
        metric_cols = [c for c in df.columns
                       if c not in ("user_input", "response",
                                    "retrieved_contexts", "reference")]

        row = {"kb_size": size}
        for col in metric_cols:
            row[col] = float(np.nanmean(df[col].astype(float)))
        row["retrieval_vote_accuracy"] = float(
            np.mean([m["vote_correct"] for m in meta])
        )
        summary_rows.append(row)

        for m, (_, r) in zip(meta, df.iterrows()):
            out = {"kb_size": size, **m}
            for col in metric_cols:
                out[col] = r[col]
            per_sample_rows.append(out)

        pretty = "  ".join(f"{c}={row[c]:.3f}" for c in metric_cols)
        print(f"   KB={size}: {pretty}  "
              f"vote_acc={row['retrieval_vote_accuracy']*100:.1f}%")

        # Write after EVERY KB size, so a rate-limit abort still leaves usable
        # results on disk instead of losing the whole run.
        write_outputs(summary_rows, per_sample_rows)
        print(f"   (results so far saved: {len(summary_rows)} KB size(s))\n")

    cols = list(summary_rows[0].keys())

    print("=" * 62)
    print("SUMMARY (mean per KB size)")
    header = "KB".rjust(5) + "".join(c[:18].rjust(20) for c in cols[1:])
    print(header)
    for r in summary_rows:
        line = str(r["kb_size"]).rjust(5)
        line += "".join(f"{r[c]:.3f}".rjust(20) for c in cols[1:])
        print(line)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        sizes = [r["kb_size"] for r in summary_rows]
        plt.figure(figsize=(8, 5))
        for c in cols[1:]:
            plt.plot(sizes, [r[c] for r in summary_rows], marker="o", label=c)
        plt.xlabel("Knowledge-base size (incidents)")
        plt.ylabel("Score")
        plt.title("RAGAS metrics vs knowledge-base size (RQ2)")
        plt.ylim(0, 1.02)
        plt.grid(alpha=0.3)
        plt.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig("ragas_kb_size_curve.png", dpi=160)
        print("\nWrote results_ragas.csv, results_ragas_per_sample.csv, "
              "ragas_kb_size_curve.png")
    except Exception as e:
        print(f"\n(plot skipped: {e})")
        print("Wrote results_ragas.csv, results_ragas_per_sample.csv")


if __name__ == "__main__":
    main()
