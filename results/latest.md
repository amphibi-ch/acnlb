> **Illustrative run.** Computed from the frozen fixture responses shipped with
> `items/sample`, not from a live model call. Sample items are SYNTHETIC.

# acnlb run report — `run-20261013-055038`

- Model: `gpt-4o-mini`  @ `https://api.openai.com/v1`
- Judge: `manual`
- Started: 2026-10-13T05:50:38+00:00
- Versions: acnlb 0.1.0, protocol acnlb-protocol-1, schema acnlb-item-1
- Items scored: **10/10**
- Overall: **100.0%** (95% CI 100.0–100.0)

> ⚠️ scored from frozen responses in /private/tmp/resp (no model call)

## Per-track

| Track | Items | Score | % |
|---|---:|---:|---:|
| core | 5 | 52/52 | 100.0% |
| retrieval | 2 | 16.5/16.5 | 100.0% |
| workflows | 3 | 33/33 | 100.0% |

## Per-item

| Item | Track | Task type | Ctx | Score | Max | % | Neg |
|---|---|---|:-:|---:|---:|---:|---:|
| `core-lit-0003` | core | 案例分析 (请求权基础) | ✓ | 12 | 12 | 100.0% | 0 |
| `core-lit-0004` | core | 法律检索报告 (数据出境) | — | 10 | 10 | 100.0% | 0 |
| `core-lit-0005` | core | 诉讼文书起草 (起诉状) | ✓ | 9 | 9 | 100.0% | 0 |
| `core-tx-0001` | core | 合同审查与风险点识别 | ✓ | 12 | 12 | 100.0% | 0 |
| `core-tx-0002` | core | 合同起草 (保密协议) | — | 9 | 9 | 100.0% | 0 |
| `ret-0009` | retrieval | 法条检索 | — | 8 | 8 | 100.0% | 0 |
| `ret-0010` | retrieval | 类案检索 | — | 8.5 | 8.5 | 100.0% | 0 |
| `wf-0006` | workflows | 要素抽取 (合同字段) | ✓ | 15 | 15 | 100.0% | 0 |
| `wf-0007` | workflows | 风险点清单 (固定表格) | ✓ | 8 | 8 | 100.0% | 0 |
| `wf-0008` | workflows | 尽职调查清单 | ✓ | 10 | 10 | 100.0% | 0 |

_Scoring: Σ(affirmative points hit) − Σ(negative points), floored at 0. One number is never the whole story — read the track breakdown._