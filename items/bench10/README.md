# items/bench10 — the 10-item example set (converted from the benchmark doc)

This directory is the harness-shaped form of the benchmark set delivered as a single
document (`cn-law-benchmark-10.md`). One JSON per item, plus `gold/`, `docs/`, and the
rubrics. **All items are SYNTHETIC.**

## What the conversion changed

The source embedded its material inside each item's Prompt and noted "落库时存为
docs/…". Here that material is persisted as real files under `docs/`, and the prompt
keeps only the instruction — the runner appends `documents[]` to the prompt, so leaving
both would have doubled the text and buries the instruction the model is actually
graded against.

| effect | before | after |
|---|---|---|
| `has_context` | `true` with material inline | `true`, `documents[]` populated |
| prompt | instruction + full contract/case text | instruction only |
| material | inside the prompt | `docs/<id>-*.md` |

Items whose source said `has_context: false` (open-book) stayed that way: `core-lit-0004`
(数据出境检索) and `ret-0009` (法条检索) — no documents, pure legal-knowledge retrieval.
`core-tx-0002` is labeled open-book in its notes but the source gave it `has_context: true`
with a deal brief now stored as `docs/core-tx-0002-deal-context.md`; flag it if you'd
rather it be truly document-free.

## What carried over verbatim

**Gold answers** and **rubric content** are the source's own text; only the *format*
changed. Rubrics are now §3.4 markdown (Structure / Style / Substance + Negative with a
`[CODE]` on every negative line) instead of the source's prose "Rubric:" blocks, and the
closed negative-point taxonomy is enforced. `max_positive_points` is computed from each
rubric, so item and rubric can't disagree.

Two source conventions map onto the taxonomy as follows:

- **"3-pt insight"** (`core-lit-0003`) → three high-weight affirmative points (3/2/2).
- **一票否决项 / HALLUC_LAW** → a negative line at −1 or −2, marked in the rubric text
  as decisive. The harness has no separate hard-fail channel yet, so these currently
  deduct rather than void the item. **That's the one real gap** — see below.

## Gap to decide on

Several items define a **veto**: REPEALED_LAW in `core-tx-0001`, 双重获赔 in
`core-lit-0003`, WRONG_HIERARCHY + 虚构规范 in `core-lit-0004`, non-JSON / 编造缺失字段
in `wf-0006`, 表头不一致 in `wf-0007`, 未识别担保矛盾 in `wf-0008`, 仅引《合同法》§114
in `ret-0009`, 分级错误 in `ret-0010`. The scoring loop (§3.8) only subtracts, so a veto
currently shows up as a large deduction, not a failure. If your grading needs a true
hard-fail, that wants a small addition: a `veto: true` flag on selected negative lines
and a `--veto-hard-fail` scoring mode. Say the word and I'll add it.

## Fixtures

`items/bench10` ships **no** good/bad response fixtures — unlike `items/sample`, this set
is for real grading. Run it with `--judge manual` to export worksheets, grade them, and
re-run with `--verdicts`. Rescoring needs no new inference (generations cache by content
hash).

```
python -m acnlb validate --items items/bench10
python -m acnlb run --items items/bench10 --model models.yaml --judge manual
python -m acnlb run --items items/bench10 --model models.yaml --judge manual --verdicts <graded-dir>
```
