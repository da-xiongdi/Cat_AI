# D-06 独立评价流程

本阶段交付的是评价入口和报告格式。当前独立评价待数据，尚无正式结果。此流程采用 [D-04 v2 协议](../artifacts/reports/d-04-20261119-01/protocol.md)，评价对象为冻结的 S3 R2 `F_base/ExtraTrees` 模型。TheMeCat 作为已认可的来源，资格审查针对新增候选。后续可使用已有外部实测资料。

## 准备冻结材料

由资格审查人员按协议登记来源、样品与已用数据的重叠证据、组成、工况和目标基准，填写独立组及纳排依据。标签保管人单独保管实测值并记录访问历史。脚本检查登记材料和文件完整性，来源独立性与实验定义的可比性由审查人员判断。

在一个新目录保存以下 UTF-8 文件。

| 文件 | 内容 |
| --- | --- |
| `protocol.md` | D-04 v2 协议原件，按原字节保存。 |
| `source-ledger.md` | 来源台账，记录检索范围、定位、可比性以及样品或实验重叠的审查证据。 |
| `candidates.json` | JSON 数组，纳入与排除候选都登记。每项含唯一 `record_id`、`source`、`locator`、`decision`（`eligible` 或 `excluded`）和 `reason`（纳排依据或证据定位）。合格项须有 `source_group` 和 `input`。排除项的 `source_group` 可为空，候选组数报告已分组的候选。`input` 使用[标准预测格式](../configs/s2_prediction.example.json)，含材料组成和四项标准化工况。 |
| `label-access.json` | JSON 对象，含 `custodian`、`eligible_labels_unseen_by_evaluators: true` 和 `history`（实际封存及访问记录的字符串数组）。 |
| `freeze.json` | 顶层含 `version: "d04-evaluation-freeze-v1"`、`candidate_scope`（候选登记和检索范围）、`coverage_scope`（组成、工况及目标的覆盖和限制）和 `sha256`。 |

`sha256` 使用下表中的键，值为文件原始字节的小写 SHA-256。标签保管人提供 `labels.json` 的哈希，将文件留在单独的封存位置。文件内容是 JSON 数组，每项有 `record_id` 和 0–100 的实测 `co2_conversion_pct`，记录 ID 与合格候选一一对应。

| `sha256` 键 | 对应文件 |
| --- | --- |
| `protocol.md`、`source-ledger.md`、`candidates.json`、`label-access.json` | 冻结目录内同名文件。 |
| `labels.json` | 单独封存的标签文件。 |
| `model-manifest.json`、`model.pkl` | [S3 R2 模型包](../artifacts/models/s3-20261118-01/r2/manifest.json)内的 `manifest.json` 与 `model.pkl`。 |
| `rule.json` | [D-03 冻结规则](../artifacts/reports/d-03-20261118-01/rule.json)。 |
| `features.json` | [D-03 所绑定的特征表](../artifacts/reports/s1-b-20261113-v4/features.json)。脚本只取模型训练记录的组成和工况作距离参照。 |

## 就绪检查

```powershell
uv run --extra modeling python scripts/d06_evaluate.py --bundle "path/to/frozen-bundle"
```

默认命令核对冻结输入、模型与规则绑定、合格记录及独立组数，输出 JSON。此步骤无需提供标签文件，也无需运行模型。至少 **30 条合格记录且 10 个独立组**时返回 `ready`，样本不足时返回 `insufficient_evidence`，材料缺失或绑定不一致时命令报错。标签内容和绑定哈希留待正式执行核对。若报告 `run_record_exists: true`，该目录已有执行记录。

## 正式执行与结果

在合格评价集就绪、需要推进 D-06 时，由标签保管人向运行人员提供封存文件，一次性执行。

```powershell
uv run --extra modeling python scripts/d06_evaluate.py --bundle "path/to/frozen-bundle" --execute --labels "path/to/sealed-labels.json"
```

脚本调用正式预测入口，应用 D-03 冻结诊断规则，再读取标签计算误差。输出写入冻结目录下的 `d06-run/`。

- `inputs.json` 记录文件哈希、标签读取起始时间和执行状态。以 `status: "completed"` 为结果可用标志。执行记录已存在时同一目录会拒绝再次执行。遇到失败，保留记录并核查材料或标签是否已访问，再由 D-04 协议决定如何处理。
- `row-results.json` 保存每条合格记录的来源、分组、入口状态、警示或拒绝原因、预测值、实测值、适用域和绝对误差。D-03 域标签与入口状态分别保留。
- `group-metrics.json` 汇总资格覆盖率、入口可用率、拒绝原因、域分层覆盖、记录等权 MAE、RMSE 和组等权 MAE。各项保留记录数、组数及相应分母。误差仅纳入入口提供点预测的记录。空分母记 `null`。分层需至少 **10 条记录且 5 个独立组**，覆盖和误差各按自己的分母标记证据是否足够。

报告结论以冻结数据声明的来源和覆盖范围为限。本轮执行点预测评价。预测区间按后续协议处理。
