# Quality test (eval)

Runs the 40 test questions through the real backend code (AIService, Retriever, ChromaDB, Mistral). It skips HTTP, Moodle and the chat DB and scores:

- **Retrieval**: was the chunk holding the answer (the `EVIDENCE` patterns in `build_dataset.py`) among the chunks sent to the LLM? If not, why:
  `pdf_not_indexed` · `evidence_not_in_index` · `below_min_score` · `outside_top_n` · `not_in_top60`.
  The run also reports whether at least the right PDF was in the context.
- **Answer**: an LLM judge (`mistral-large-latest`) grades it `correct` / `partial` / `wrong` against the expected answer. Questions for a user who is not enrolled are graded by a rule instead: no course chunk may reach the LLM and no course PDF may be cited.
- **Language** of the answer, and whether the expected **source is cited**.

Every run is saved to `eval/results/<timestamp>_<label>/`, as `results.json` and as `results.csv` (`;`-separated, opens in Excel). Each run is compared with the previous one, so you see what a change fixed and what it broke.

## Run (from `api/`, venv active)

```
python -m eval.run_eval --judge-only            # 1st time: check the judge against your manual Yes/No
python -m eval.run_eval --label baseline        # full run
python -m eval.run_eval --retrieval-only        # search step only, seconds, ~free
python -m eval.run_eval --only 5,13,27          # selected questions
python -m eval.run_eval --n-results 8 --label n8
python -m eval.run_eval --no-retrieval-translation --label no-tr
python -m eval.run_eval --as-chats              # replay in chat order with history
```

`--concurrency` (default 3) is limited by Mistral's rate limit. Requests that fail with 429 are retried automatically.

## Changing the questions

Edit `chatbot_test.xlsx`, then rebuild the dataset with `pip install openpyxl` and `python -m eval.build_dataset path\to\chatbot_test.xlsx`. A broken expected-answer cell can be fixed with `EXPECTED_OVERRIDES` in `build_dataset.py`.

Note: questions run as separate single-turn chats unless `--as-chats` is given, so the results are reproducible. Answers come from the LLM and vary a little from run to run, so treat a ±1 change on a single question as noise.
