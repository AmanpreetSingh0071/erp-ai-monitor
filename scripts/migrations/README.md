# One-off migration scripts

Each script in this directory was written to apply a single change to the
project, was run once against the repository root and is kept only as a record
of how that change was made. None of them is imported by the application or by
the evaluation harness, and none needs to be run again. Every script checks
whether its change is already present and exits without doing anything if so.

Each script expects to run from the repository root, with one exception:
`add_ground_truth_flag.py` expects the `evaluation/` folder. Every script checks
its working directory on startup and exits with a message if it is wrong, so
running one from the wrong place is harmless.

| Script | Applied | What it changed |
|---|---|---|
| `fix_rag_and_worker.py` | 14 Aug 2026 | Split the knowledge base into one chunk per incident so FAISS retrieval returns a genuine top 3 instead of the whole file. Also made the retry worker claim rows before spawning threads. |
| `fix_duplicate_agent_runs.py` | 14 Aug 2026 | Moved the row claim into `run_ai()` so that the ingest path and the retry poller can no longer both process the same transaction. |
| `add_ground_truth_flag.py` | 16 Aug 2026 | Added a `--ground-truth` flag to `evaluation/run_experiment.py` and namespaced the output files by case set, so a held-out run cannot overwrite the original results. |
| `fix_artefact_report_mismatch.py` | 17 Aug 2026 | Changed the `HIGH_RETRY` threshold in `configs/rules.yaml` from 5 to 3 and the rule engine comparison from `>` to `>=`, matching Appendix B. |
| `fix_train_at_startup.py` | 17 Aug 2026 | Made the backend train the detector at startup rather than loading `models/anomaly_model.pkl`, which is git-ignored and therefore of unknown provenance. |
| `update_findings_log.py` | 19 Aug 2026 | Replaced the project title in `FINDINGS_LOG.md` with the FPR title and appended six entries plus milestone rows covering work after 26 June. |

Dates are the date each script was first committed.

## Related but not held here

`evaluation/fix_ragas_vertexai.py` is deliberately not tracked by git. It
patches a file inside the RAGAS virtualenv rather than anything in this
project, so it counts as environment setup. It remains on disk and is listed
in `.gitignore`.
