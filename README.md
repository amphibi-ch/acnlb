# acnlb — alpha CN Legal Bench

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![last eval run](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/OWNER/acnlb/main/results/latest.json&label=last%20eval&query=%24.started_at&color=4f8cff)](results/latest.md)
[![sample items](https://img.shields.io/badge/sample%20items-10-informational)](items/sample)
[![run on GitHub](https://img.shields.io/badge/run%20eval-GitHub%20Actions-2f6fe4)](../../actions/workflows/run-eval.yml)

A **work-product-and-rubric** benchmark harness for Chinese-law tasks — for internal
model & skill selection and regression testing. It scores the **deliverable** a
Chinese-law task would require against a rubric of atomic propositions, with a closed
negative-point taxonomy for the CN-specific failure modes.

> Sample items under `items/sample/` are **SYNTHETIC**. Real matters are added
> privately — see [items/README.md](items/README.md) and "Point this at your real
> items" below. Only `items/sample` is public.

Design rationale, item schema (§3.3), rubric format (§3.4), the negative-point
taxonomy (§3.5), and the scoring loop (§3.8) come from
`CN-Legal-Benchmark-Design.md`. This repo implements them; the CLI is the single
source of truth and the GitHub Actions workflow shells out to the very same command.

---

## What it measures

Three tracks (`core`, `workflows`, `retrieval`). Each item is a task + optional
documents + gold answer + rubric. Two ways to run it, same code:

1. **Local CLI** — bring your own OpenAI-compatible key.
2. **One-click GitHub Actions** — the key comes from a repo secret.

## Scoring

```
score = Σ(affirmative points hit) − Σ(negative points),  floored at 0
```

Reported **per-item _and_ per-track** — never only a mean (§3.8). Negatives come from
the closed taxonomy:

| Code | Error | Points |
|---|---|---|
| `HALLUC_FACT` | 编造事实 / fabricated fact | −1 each |
| `HALLUC_CITE` | 编造引用 / fabricated citation | −1 each |
| `REPEALED_LAW` | 引用已废止法律 / repealed law | −1 each |
| `WRONG_HIERARCHY` | 效力位阶错误 / hierarchy error | −1 each |
| `EXTRATEXT` | 冗余/错误引申 / extraneous | −0.5 each |
| `FORMAT_BREACH` | 格式违规 / format breach | task-specific |

## Grading: human-first

- `--judge manual` exports a **grading worksheet** per item and accepts a
  **verdicts file** directory.
- `--judge llm` scores each `Does the response state X?` item as binary with the
  gold answer in the judge's context. It emits the same verdict shape, so scoring is
  identical — and it is marked **UNVALIDATED** until `judge-validate` reports
  Cohen's κ ≥ threshold on a labeled set. **Do not make model decisions off an
  unvalidated judge** (§4.4).

## Determinism

Scoring is pure given `(response, rubric, verdicts)`. Model generations are cached by
`sha256(item_id, model, rendered_prompt)`, so re-scoring after a rubric change needs
no new inference. The `score` command takes no network path at all.

```
python -m acnlb score \
  --response items/sample/fixtures/core-tx-0001.good.txt \
  --verdicts items/sample/fixtures/core-tx-0001.good.verdicts.json \
  --rubric   items/sample/core-tx-0001.rubric.md      # run twice → identical
```

---

## Quickstart (local)

```bash
git clone <this-repo> && cd acnlb
pip install pyyaml
export MODEL_API_KEY=sk-...            # your OpenAI-compatible key; never commit it
export MODEL_BASE_URL=https://api.openai.com/v1   # optional; or set base_url in YAML

python -m acnlb validate --items items/sample
python -m acnlb run --items items/sample --model models.example.yaml --judge manual
python -m acnlb report --run runs/latest
```

`run --judge manual` with no `--verdicts` writes `runs/latest/worksheets/*.worksheet.md`
and exits. Grade them, save `<id>.verdicts.json` files, then re-run with
`--verdicts <dir>`. `models.example.yaml` shows the OpenAI-compatible config shape
(any endpoint speaking `POST {base_url}/chat/completions` works).

## One-click (GitHub Actions)

Open **Actions → run-eval → Run workflow** and pick the item path and model.
The job runs `python -m acnlb run …`, uploads `runs/latest` as an artifact, commits
`results/latest.json` + `results/latest.md` for the site, and **fails if zero items
scored or any item errored** — no silent empty runs. The Pages site (`site/`) is the
front door and deep-links to that workflow.

---

## Point this at your real items

Real items need no code change:

1. Put them under a private path, e.g. `items/real/`, using the same JSON schema and
   the same rubric markdown. Keep that directory out of the public repo (gitignore it
   or use a private submodule).
2. `python -m acnlb validate --items items/real`
3. `python -m acnlb run --items items/real --model models.yaml --judge manual`
4. For Actions: point the `item_path` input at `items/real` (run it from a private
   checkout or a self-hosted runner if the items must stay confidential).

The harness, the schema, the negative taxonomy, and the site are unchanged — only the
`--items` path differs. Details: [items/README.md](items/README.md).

## Repo layout

```
acnlb/       cli, schema, rubric parser, pure scorer, retrieval, judge, runner, model, report
items/sample/  10 synthetic items + fixtures (the demo set)
site/       static front door (no build step) — reads results/latest.json
results/    committed latest.json + latest.md
.github/workflows/  run-eval.yml (dispatch) + deploy-pages.yml
tools/      make_verdicts.py (regenerates fixture verdicts from rubrics)
tests/      determinism, relevance, kappa, schema tests
```

## License

MIT — see [LICENSE](LICENSE).
