# acnlb — alpha CN Legal Bench

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![last eval run](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/amphibi-ch/acnlb/master/results/latest.json&label=last%20eval&query=%24.started_at&color=4f8cff)](results/latest.md)
[![sample items](https://img.shields.io/badge/sample%20items-10-informational)](items/sample)
[![run on GitHub](https://img.shields.io/badge/run%20eval-GitHub%20Actions-2f6fe4)](../../actions/workflows/run-eval.yml)

A **work-product-and-rubric** benchmark harness for Chinese-law tasks — for internal
model & skill selection and regression testing. It scores the **deliverable** a
Chinese-law task would require against a rubric of atomic propositions, with a closed
negative-point taxonomy for the CN-specific failure modes.

> `items/sample/` (the demo set) and `items/bench10/` are **SYNTHETIC**. Real
> matters are added privately — see [items/README.md](items/README.md) and "Point
> this at your real items" below. Those two directories are the only item sets
> published here.

Design rationale, item schema (§3.3), rubric format (§3.4), the negative-point
taxonomy (§3.5), and the scoring loop (§3.8) come from
`CN-Legal-Benchmark-Design.md`. This repo implements them; the CLI is the single
source of truth and the GitHub Actions workflow shells out to the very same command.

---

## What it measures

Three tracks (`core`, `workflows`, `retrieval`). Each item is a task + optional
documents + gold answer + rubric.

## Two ways to run it, same code:

1. **Local CLI** — bring your own OpenAI-compatible key.
2. **One-click GitHub Actions** — the key comes from a repo secret.

## Just want the item set?

The [site](https://amphibi-ch.github.io/acnlb/) serves the downloads itself, so getting
the item set does not mean navigating GitHub:

| Download | Unpacks to | Use it for |
|---|---|---|
| `acnlb-bench10.zip` | `bench10/` | drop straight into `--items` |
| `acnlb-workspace.zip` | `acnlb/` | the harness too — runnable without a clone |
| `acnlb-bench10.bundle.json` | — | every item in one file, rubric + gold inlined |
| `SHA256SUMS`, `manifest.json` | — | confirm what arrived is what was published |

They are built by `tools/build_bundle.py` at deploy time and are byte-reproducible:
fixed archive timestamps, sorted entries, no wall-clock in the manifest. CI asserts
it, so a rebuild that changed nothing produces identical bytes.

```bash
python tools/build_bundle.py --items items/bench10 --workspace --out _site/download
cd _site/download && shasum -a 256 -c SHA256SUMS
```

## Adding an item from an issue

No clone, no local tooling, no write access: open an issue with the
[item form](.github/ISSUE_TEMPLATE/new-item.yml), fill in the fields, and an Action
turns it into files and opens a **draft pull request**.

```
issue form  →  items/incoming/<id>.json + <id>.rubric.md + gold/<id>.md
            →  branch item/<id>  →  draft PR
```

What the Action does, in order:

1. reads the issue body out of a **file** (`$RUNNER_TEMP/item/body.md`), never out of
   the shell, because it is text a stranger typed;
2. validates the id and every attachment path as path components — an id of
   `../../etc/passwd` or an absolute document path is refused before anything is
   written;
3. leaves the id blank? It is filled from the published set's own numbering
   (`items/bench10` → the next `core-tx-…`, `wf-…`, `ret-…`), so a contributor never
   has to guess a number;
4. runs `python -m acnlb validate` on what it produced, and posts the output in the
   PR — **draft** while it fails, ready for review once it passes;
5. edits to the issue re-run the whole thing on the same branch, so the PR is updated
   instead of duplicated.

The default branch is never written to, and `items/incoming/` is invisible to the
site, to the bundled downloads and to CI's item list until somebody moves the item
into a real set. Attachments still have to be added to the PR by hand — the form can
only carry their paths.

Locally, the same tool is the debugging path:

```bash
python tools/issue_to_intake.py --body issue.md --out /tmp/x --intake-out /tmp/x.intake.md
```

## Adding an item from the browser

The site has a form. Fill it in, export, and you get **exactly** the three files
`acnlb new --intake` writes — `<id>.json`, `<id>.rubric.md`, `gold/<id>.md`:

- one item at a time, or paste/import several intake forms at once (a second form
  starts at an `id:` line, or after a lone `%%%` line);
- `Export all (.zip)` downloads the whole draft, ready to unpack into `items/`;
- the export also round-trips: a `.bundle.json` downloaded from the site imports back
  into the form;
- drafts live in the browser's `localStorage`; nothing is uploaded and no account is
  needed.

The fields are constrained by **what the published set already uses**, not by a list
someone typed into the page. `tools/build_items_index.py` derives `vocab` from
`items/bench10` — the categories, task types, jurisdictions, authority citations,
document paths and ids that exist, plus one real value per field for the grey hints —
and the page offers those:

- **track, then id** — the track picks the rubric skeleton and the id family, so it is
  asked first. The id field's grey text is the number that row would actually get, and
  the button beside it fills that in;
- **category / task_type / jurisdiction** — a closed list whose last entry hands the
  field back to you as free text. The schema keeps these fields free strings on
  purpose, so the list is a suggestion that stops `合同审查` / `合同审核` /
  `contract review` becoming three task types no report can group by;
- **documents** — one per line, plus a picker of the paths the set already ships;
- **authority_basis** — a plain text field, deliberately **not** a dropdown: a
  citation is typed, not picked, and the grey example teaches the shape the set
  converges on (short title *and* article number) better than an option list does;
- **has_context** — not asked. It is derived from the document list and shown
  read-only, because a checkbox beside that list is a second source of truth that can
  only disagree with it;
- **rubric** — a switch between two ways of writing the same text: a row editor (one
  row per point: part, sub-label, score, text) fed by per-track templates in
  `acnlb/scaffold.py`, or the markdown. Exactly one of them is on screen at a time,
  and a rubric the rows cannot carry line for line forces the markdown rather than
  being quietly trimmed;
- **retrieval gold** — a small table, one row per `tier | ref | note`.

Every text field carries a hint. It is a value the set already contains wherever
there is one, and a format template otherwise — never a value no item has used, which
would be the page inventing a spelling one layer quieter than a hand-typed dropdown.

What it will not do is commit. The site is static and the repo is public, so an item
still enters the benchmark the way any change does — a commit by someone with write
access, or a pull request that a maintainer merges.

Its validation is not a re-typing of the rules. `tools/build_site_schema.py` exports
the tracks, tiers, negative codes, rubric skeleton and per-track templates out of the
package that owns them, the page fetches that file, and `tests/test_form_parity.py`
runs both the JavaScript and the Python on the same input — all ten shipped rubrics,
the id and path rules, and the next-free-id answer — and compares. Code the form
accepts, `validate` accepts.

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
git clone https://github.com/amphibi-ch/acnlb.git && cd acnlb
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

Real items need no code change. **You don't write JSON by hand** — fill in a plain-text
intake form and the scaffolder emits a correctly-shaped item directory:

```bash
cp items/INTAKE.template.md my-item.md     # edit it
python -m acnlb new --intake my-item.md --out items/real
python -m acnlb validate --items items/real
python -m acnlb run --items items/real --model models.yaml --judge manual
```

`new` writes `<id>.json` + `gold/<id>.md` + `<id>.rubric.md`, computing
`max_positive_points` from the rubric so the two can't disagree, and pre-filling the
rubric's negative section with the full closed taxonomy. It refuses to overwrite
unless you pass `--force`, and warns about missing documents. `validate` rejects any
item whose rubric or gold answer still contains `TODO`.

Then, to keep the items private: put them under `local/` (gitignored), and for
Actions point the `item_path` input at them from a private checkout or self-hosted
runner.

There's also a raw-JSON route if you prefer to write it directly — the schema is
§3.3, the sample items are the reference, and `items/_template.item.json` is a
blank one (`_`-prefixed files are skipped by the loader). The harness, the schema,
the negative taxonomy, and the site are unchanged either way — only the `--items`
path differs. Details: [items/README.md](items/README.md).

## Repo layout

```
acnlb/            cli, schema, rubric parser, pure scorer, retrieval, judge, runner, model, report,
                  scaffold (intake → files), vocab (suggestions derived from the item set)
items/sample/     10 synthetic items + fixtures (the demo set)
items/bench10/    10 synthetic items, no fixtures (the working set)
items/incoming/   staging area for issue submissions — not a published set; move the
                  item into items/bench10 (or your real set) to make it count
site/             static front door (no build step) — reads results/latest.json,
                  items.json, schema.json, and download/manifest.json
results/          committed latest.json + latest.md
docs/             item source documents
notebooks/        quickstart notebook
local/            NOT IN THE REPO — local-only work, gitignored (see below)
.github/          workflows (run-eval, ci, deploy-pages, item-from-issue)
                  + ISSUE_TEMPLATE/new-item.yml (the submission form)
tools/            build_items_index.py, build_site_schema.py, build_bundle.py, issue_to_intake.py,
                  preview_site.py, stamp_assets.py, verdicts_skeleton.py, grading_pack.py, make_verdicts.py
tests/            determinism, relevance, kappa, schema, intake scaffolding, item authoring,
                  issue→item conversion, site contract, and JS/Python form-parity tests
```

`local/` is where anything unpublished goes — CLI bridges, per-machine config,
scratch scripts. It is ignored in one line, so "is this safe to push?" is a single
look rather than a grep. It exists on a maintainer's machine and nowhere else; a
fresh clone will not have it and nothing in the harness requires it.

## License

MIT — see [LICENSE](LICENSE).
