# Item intake form — fill this in, then run the scaffolder

<!--
This is the plain-text way to author an item. You do NOT write JSON.

  python -m acnlb new --intake my-item.md --out items/real

Header lines  → item metadata (§3.3)
## Prompt     → the exact instruction the model receives
## Documents  → paths, relative to the items dir; leave the section empty for open-book items
## Gold answer→ the model answer a competent lawyer would produce  (§3.6: write this FIRST)
## Rubric     → optional; if omitted you get a §3.4 skeleton with the negative taxonomy pre-filled

Delete this comment block when you fill it in. Copy the example below to start.
-->

## EXAMPLE (copy from here down, delete the example, keep your own)

id:                 core-tx-0011
track:              core
category:           Transaction
task_type:          合同审查与风险点识别
task:               识别增资协议中的重大风险条款并出具审查意见
jurisdiction:       CN-mainland
has_context:        true
authority_basis:    《民法典》, 《公司法》(2023修订)
notes:              SYNTHETIC — 合成示例

## Prompt

你是一家中国律师事务所的执业律师。客户拟以增资方式取得某有限责任公司 20% 股权。
请审阅附件《增资协议》，出具审查意见，指出重大风险条款并给出修改建议。
要求分「条款定位 + 风险 + 建议」三段式呈现，并援引现行有效的法律依据。

## Documents

- docs/core-tx-0011-capital-increase.md

## Gold answer

（在这里写「一名胜任律师会产出的回答」。这是本表最重要的一栏：
 先写完参考答案，再据此逐条提炼 rubric，顺序不能反 —— §3.6。）

## Rubric

（可留空。留空时会生成 §3.4 骨架，并把 §3.5 的负分分类全部预填好，你只需挑用。）

## Notes

（可选：来源、是否合成、审核人、日期等。）


## FIELD REFERENCE

| field | required | notes |
|---|---|---|
| `id` | yes | 唯一标识；建议 `<track>-<缩写>-<编号>`，如 `core-tx-0011` |
| `track` | yes | `core` \| `workflows` \| `retrieval` |
| `category` | no | 如 `Transaction` / `Litigation` |
| `task_type` | yes | 中文任务类型，如 `合同审查与风险点识别` |
| `task` | yes | 一句话任务名 |
| `jurisdiction` | no | 默认 `CN-mainland` |
| `has_context` | no | `true`/`false`；留空则按是否列了 Documents 推断 |
| `authority_basis` | no | 逗号/顿号分隔的法源，如 `《民法典》, 《公司法》(2023修订)` |
| `notes` | no | 公开示例请注明 `SYNTHETIC` |

**Retrieval items** additionally need graded gold. Add a `retrieval_gold` block to the
generated JSON by hand:

```json
"retrieval_gold": {
  "class": "similar_case",
  "gold_items": [
    {"ref": "（2021）最高法民申1234号", "tier": "高", "note": "焦点与规则均吻合"},
    {"ref": "（2020）京民终5678号", "tier": "中", "note": "案由相同，焦点部分重合"}
  ],
  "tier_points": {"高": 2.0, "中": 1.0, "低": 0.5}
}
```

tier 只能取 `高` / `中` / `低`。类案检索的层级需两名评阅人一致确定（§2.6）。
