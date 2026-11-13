"""Classify source-code comments as Security Technical Debt (STD) with an LLM.

Examples
--------
# DeepSeek-V3.1 via Chat Completions (provider default sampling)
python src/run.py --provider chat --model deepseek-v3.1 --label deepseek

# GPT-4.1 via Responses API
python src/run.py --provider responses --model gpt-4.1 --label gpt41

# Claude Sonnet 5 via Messages API (same user-message format as the original study)
python src/run.py --provider anthropic --model claude-sonnet-5 --label claude \\
    --max-tokens 4000 --request-interval 6.5 --user-template "Comment:\\n{comment}\\n"

# Repeat the experiment 5 times (for confidence intervals / significance tests)
python src/run.py --provider chat --model deepseek-v3.1 --label deepseek --runs 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

from providers import DEFAULT_BASE_URLS, PROVIDERS, build_client, complete

ROOT = Path(__file__).resolve().parent.parent

OUTPUT_RE = re.compile(
    r"^\s*Classification:\s*(?P<classification>Security Technical Debt|Not Security Technical Debt)\s*\n"
    r"\s*CWE:\s*(?P<cwe>\S+)\s*\n"
    r"\s*Explanation:\s*(?P<explanation>\S.*)",
    re.DOTALL,
)

FATAL_STATUS_CODES = {401, 403, 404}  # bad key / permissions / model name: retrying will not help


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", required=True, choices=PROVIDERS)
    p.add_argument("--model", required=True, help="Exact model name sent to the API.")
    p.add_argument("--label", required=True, help="Short name used in output columns/files.")
    p.add_argument("--input", default=str(ROOT / "data" / "SSATD_COMMENTS.xlsx"))
    p.add_argument("--output-dir", default=str(ROOT / "outputs"))
    p.add_argument("--prompt", default=str(ROOT / "prompts" / "system_prompt.txt"))
    p.add_argument("--comment-column", default="text")
    p.add_argument("--base-url", default=None, help="Override the default gateway URL.")
    p.add_argument("--temperature", type=float, default=None, help="Omit to use the provider default.")
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--runs", type=int, default=1, help="Number of independent repetitions.")
    p.add_argument("--user-template", default="{comment}",
                   help='Format of the user message; "{comment}" is replaced by the comment text.')
    p.add_argument("--request-interval", type=float, default=0.5,
                   help="Minimum seconds between two requests.")
    p.add_argument("--retries", type=int, default=6)
    p.add_argument("--retry-delay", type=float, default=5.0)
    p.add_argument("--rate-limit-wait", type=float, default=20.0)
    p.add_argument("--save-every", type=int, default=20)
    return p.parse_args()


class RateLimiter:
    """Enforces a minimum interval between consecutive requests."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self._last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last = time.time()


def status_code(exc: Exception) -> Optional[int]:
    return getattr(exc, "status_code", None)


def classify_with_retries(args, client, system_prompt, comment, limiter) -> str:
    """Return a valid model output, or an ``ERROR: ...`` string after all retries."""
    user_message = args.user_template.replace("\\n", "\n").format(comment=comment)

    for attempt in range(1, args.retries + 1):
        try:
            limiter.wait()
            output = complete(
                client, args.provider, args.model, system_prompt, user_message,
                temperature=args.temperature, max_tokens=args.max_tokens,
            )
            if not OUTPUT_RE.match(output):
                raise ValueError(f"Unexpected output format: {output[:120]!r}")
            return output

        except Exception as exc:  # noqa: BLE001 - SDK exception types differ per provider
            code = status_code(exc)
            if code in FATAL_STATUS_CODES:
                raise  # bad key / model name / permissions: abort the whole run
            tqdm.write(f"  attempt {attempt}/{args.retries} failed: {exc}")
            if attempt < args.retries:
                base = args.rate_limit_wait if code == 429 else args.retry_delay
                time.sleep(base * attempt)

    return "ERROR: request failed after retries"


def parse_output(raw) -> dict:
    match = OUTPUT_RE.match(raw) if isinstance(raw, str) else None
    if not match:
        return {"classification": None, "cwe": None, "explanation": None}
    return {
        "classification": match["classification"],
        "cwe": match["cwe"],
        "explanation": match["explanation"].strip(),
    }


def is_done(value) -> bool:
    return isinstance(value, str) and bool(value) and not value.startswith("ERROR")


def save(df: pd.DataFrame, path: Path, columns_prefixes: list[str]) -> None:
    """Write the workbook, adding parsed columns next to each raw output column."""
    out = df.copy()
    for prefix in columns_prefixes:
        parsed = out[f"{prefix}_raw"].apply(parse_output).apply(pd.Series)
        for field in ("classification", "cwe", "explanation"):
            out[f"{prefix}_{field}"] = parsed[field]
    out.to_excel(path, index=False)


def main() -> None:
    args = parse_args()
    load_dotenv()

    api_key = os.getenv("AVALAI_API_KEY")
    if not api_key:
        sys.exit("AVALAI_API_KEY is not set (put it in .env or export it).")

    system_prompt = Path(args.prompt).read_text(encoding="utf-8").strip()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{args.label}_results.xlsx"
    meta_path = out_dir / f"{args.label}_metadata.json"

    # Resume from an earlier (possibly interrupted) run when the output exists.
    source = output_path if output_path.exists() else Path(args.input)
    print(f"Loading {source}")
    df = pd.read_excel(source)

    if args.comment_column not in df.columns:
        sys.exit(f"Column {args.comment_column!r} not found. Columns: {list(df.columns)}")

    prefixes = [f"{args.label}_run{i}" for i in range(1, args.runs + 1)]
    for prefix in prefixes:
        col = f"{prefix}_raw"
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df), dtype="object")
        df[col] = df[col].astype("object")

    # Strip stale parsed columns from a resumed file; they are regenerated on save.
    df = df[[c for c in df.columns if not any(
        c == f"{p}_{f}" for p in prefixes for f in ("classification", "cwe", "explanation"))]]

    started = datetime.now(timezone.utc)
    metadata = {
        "label": args.label,
        "provider": args.provider,
        "model": args.model,
        "base_url": args.base_url or DEFAULT_BASE_URLS[args.provider],
        "temperature": args.temperature if args.temperature is not None else "provider default",
        "max_tokens": args.max_tokens if args.max_tokens is not None else "provider default",
        "user_template": args.user_template,
        "runs": args.runs,
        "input_file": str(args.input),
        "n_rows": int(len(df)),
        "prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "started_utc": started.isoformat(timespec="seconds"),
    }

    client = build_client(args.provider, api_key, args.base_url)
    limiter = RateLimiter(args.request_interval)
    since_save = 0

    try:
        for prefix in prefixes:
            col = f"{prefix}_raw"
            print(f"\n=== {prefix} ({args.model}) ===")
            for idx in tqdm(df.index, desc=prefix):
                if is_done(df.at[idx, col]):
                    continue
                comment = df.at[idx, args.comment_column]
                if pd.isna(comment) or not str(comment).strip():
                    df.at[idx, col] = ""
                    continue

                df.at[idx, col] = classify_with_retries(
                    args, client, system_prompt, str(comment).strip(), limiter
                )
                since_save += 1
                if since_save >= args.save_every:
                    save(df, output_path, prefixes)
                    since_save = 0
    finally:
        # Persist partial results even on Ctrl+C or a fatal API error.
        save(df, output_path, prefixes)
        metadata["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    n_err = sum(
        isinstance(v, str) and v.startswith("ERROR")
        for p in prefixes for v in df[f"{p}_raw"]
    )
    print(f"\nFinished. Results: {output_path}\nMetadata: {meta_path}\nFailed rows: {n_err}")


if __name__ == "__main__":
    main()
