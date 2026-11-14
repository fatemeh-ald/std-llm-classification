# LLM-based Security Technical Debt Detection — Replication Package

Code accompanying the paper *A Comparative Evaluation of Large Language Models for
Security Technical Debt Detection, CWE Classification, and Explainability*.

Each source-code comment (or issue text) is sent to an LLM with a fixed system prompt.
The model returns a binary STD label, a single CWE identifier, and a one-sentence
explanation.

## Repository layout

```
prompts/system_prompt.txt   Full, verbatim prompt used for all models
src/providers.py            API wrappers (Chat Completions, Responses, Anthropic Messages)
src/run.py                  Experiment runner (resume, retries, repeated runs, metadata)
data/                       Place SSATD_COMMENTS.xlsx here (see "Data")
outputs/                    Generated results + run metadata (git-ignored)
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then set AVALAI_API_KEY
```

All models are called through the AvalAI gateway (`https://api.avalai.ir`). Use
`--base-url` to point to another OpenAI/Anthropic-compatible endpoint.

## Data

The evaluation uses 234 developer-text instances (code comments and issue reports) selected from the SSATD dataset published by Díaz Ferreyra et al. (2024). Ground-truth STD labels and CWE annotations are taken from that dataset. Models receive only the textual content of each instance (no surrounding source code).

Place the input Excel file (with a `text` column) at `data/SSATD_COMMENTS.xlsx`, or pass a custom path with `--input`.

## Reproducing the experiments

| Model | Provider flag | Command |
|-------|---------------|---------|
| DeepSeek-V3.1 | `chat` | `python src/run.py --provider chat --model deepseek-v3.1 --label deepseek` |
| GPT-4.1 | `responses` | `python src/run.py --provider responses --model gpt-4.1 --label gpt41` |
| Claude Sonnet 5 | `anthropic` | `python src/run.py --provider anthropic --model claude-sonnet-5 --label claude --max-tokens 4000 --request-interval 6.5 --user-template "Comment:\n{comment}\n"` |

Add `--runs N` to repeat the whole experiment N times (columns `<label>_run1_*`,
`<label>_run2_*`, …) so that confidence intervals or significance tests can be computed.
Interrupted runs resume automatically from `outputs/<label>_results.xlsx`.

## Experimental configuration

| Setting | Value |
|---------|-------|
| Prompt | `prompts/system_prompt.txt` (SHA-256 recorded in each metadata file) |
| Temperature / top-p | Not set — provider defaults (Claude Sonnet 5 does not accept sampling parameters) |
| Max output tokens | Provider default (Claude: 4000) |
| Access date | September 2026 |
| Model versions | deepseek-v3.1, gpt-4.1, claude-sonnet-5 (via AvalAI) |

Every run writes `outputs/<label>_metadata.json` with the model, endpoint, parameters,
prompt hash, and start/finish timestamps (UTC).

## Output columns

For each run: `<label>_runK_raw` (verbatim model output) plus the parsed
`<label>_runK_classification`, `<label>_runK_cwe` and `<label>_runK_explanation`.
Rows that failed after all retries contain `ERROR: ...` and are retried on the next
invocation.

## Notes

- The user message is the bare comment for DeepSeek and GPT-4.1. For Claude the original
  experiment wrapped it as `Comment:\n<text>\n`; the command above reproduces that.
- Model outputs are validated against the required three-line format; malformed outputs
  are retried.
