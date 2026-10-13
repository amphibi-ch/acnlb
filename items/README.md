# items — how to add real items

The public repo ships **`items/sample/` only**: ten clearly-labeled **SYNTHETIC**
items whose purpose is to exercise every code path (the three tracks, the graded
retrieval path, all six negative-point codes, and a `STYLE = N/A` rubric).

Real matters are added **privately**. Nothing about the harness changes when you do.

## Layout of an item

```
items/sample/
  <id>.json              one item, schema from design doc §3.3
  <id>.rubric.md         markdown rubric, §3.4
  gold/<id>.md           the gold answer the rubric was written from
  docs/<id>-*.md         supplied documents (omit for open-book items)
  fixtures/
    <id>.good.txt        a frozen good response
    <id>.bad.txt         a frozen bad response
    <id>.good.verdicts.json   human verdicts for the good response
    <id>.bad.verdicts.json    human verdicts for the bad response
```

## Adding a real item

**Preferred: the intake form** (no JSON by hand).

```bash
cp items/INTAKE.template.md my-item.md      # fill it in
python -m acnlb new --intake my-item.md --out items/real
```

`new` writes `<id>.json`, `gold/<id>.md`, and `<id>.rubric.md` (with the negative
taxonomy pre-filled). Then:

1. Write the **gold answer first**, then derive the rubric from it (§3.6) — never the
   reverse.
2. Every substance line must be an atomic ``Does the response state X?`` question and,
   where possible, traceable to a specific 条.
3. Any negative line must carry a ``[CODE]`` from the closed taxonomy in
   ``acnlb/negatives.py``. ``validate`` rejects anything else.
4. Keep `max_positive_points` equal to the rubric's affirmative sum. `new` sets this
   for you; if you edit the rubric by hand, update it (or re-run `new --force`).
5. Run:
   ```
   python -m acnlb validate --items items/real
   python -m acnlb run --items items/real --model models.yaml --judge manual
   ```

**Raw JSON route** — if you'd rather write the item file directly, copy
`items/sample/<id>.json` or `items/_template.item.json` (the `_` prefix makes the
loader skip it) and fill in the §3.3 fields. Everything else is identical.

## Keeping real items private

Put them under a path that is not published, e.g. `items/real/` with that
directory gitignored (or a private submodule), and point the CLI / the Actions
workflow input at it. The harness, the schema, and the site are unchanged; the
site never reads anything but `results/latest.json` and `items/sample`.

See `../README.md` → "Point this at your real items".
