# WB-15-01 基线与展示规则

2026-11-20（Asia/Shanghai）按 `configs/workbench.yaml` 只读检查 `data/workbench.sqlite`：`quick_check=ok`，schema 8；WB-15 前缀未占用。WB-13、WB-14 均为 done，WB-14 正式验收见 [记录](wb14_06_acceptance.md)。工作区存在未提交改动，代码基准提交为 `db4ea20ddfb2712c08864d365a262c96957babe2`，不能将该提交视为工作区完整版本。

科研类别 10 项全部 done、均无活动主计划；例如 S1A-01 应显示“待关联主计划”。工作台类别原有 16 项全部 done，均有活动且检测为 valid 的主计划；例如 WB-14-01 对应 `docs/workbench/wb14_implementation_plan.md` 的 `2. 子任务、实施顺序与交付物`。科研分类上下文不存在，工作台分类焦点为空；两类均无活动近期安排。工作台有一条不活动的 WB-13-08 近期记录，不应作为活动安排展示。

## 可复用入口与规则

- `queries.query` 在数据库一致性副本上返回分类任务、`contexts`、`primary_plans` 和 `missing`；文件检测是观察时的实时文件状态，并非数据库快照。`contexts.recent` 含不活动记录，展示时必须过滤 `active`。`default_order` 含历史任务，不能直接当作近期任务。
- `service.get_task` 返回交付物、当前版本验收项、前置任务 ID、评审及证据复核标记；就绪判定应沿用 `service._ready` 的依赖和证据规则，不得只看依赖任务状态。明确呈现阻塞原因，并允许跨类别追踪前置任务。
- 人工安排按 `sort_order`、任务 ID 排序，自动候选按就绪、优先级、计划日期、ID 稳定排序，按任务 ID 去重。done、cancelled 归历史；类别不匹配或失效焦点标记待复核。没有活动近期任务时展示空态，不把历史任务冒充待办。
- `plans.list_task_plan_references` 提供主计划和参考计划及最后核对记录；`valid` 可定位，`unverified` 和 `changed` 若章节仍可定位则允许查看并提示“计划待核对”。无主计划提示“待关联主计划”；`section_missing`、`section_ambiguous`、`missing_or_invalid`、`path_escape` 分别说明原因并保留引用及历史。打开时须重新检查文件，不能依赖列表加载时的结果。
- 现有 `/documents`、`/artifacts/{artifact_id}` 与 `index.preview` 提供文档入口和预览；`/roadmap?node=...&task=...` 与 `/tasks/{task_id}` 提供科研路线和任务定位。现有预览尚需 WB-15-03 补充章节稳定定位，不能假定已支持。

## 隔离样本和验证

[一致性副本及正式查询结果](../../artifacts/wb15-01-samples/baseline-query.json) 在登记前取得；[隔离样本结果](../../artifacts/wb15-01-samples/sample-results.json) 和 [复现脚本](../../scripts/wb15_01_samples.py) 使用副本及隔离文档，未修改正式科研任务。副本的工作区路径专门改为隔离目录，其他原有文档的检测结果因此不代表正式文件状态。

| 样本任务 | 分类 | 文档和章节 | 已验证状态及预期展示 |
|---|---|---|---|
| WB15-SAMPLE-R | 科研 | `R.md` · `科研计划` | 核对后 `valid`；修改正文为 `changed`，提示待核对；改名后 `section_missing`，提示章节缺失，保留核对记录。 |
| WB15-SAMPLE-W | 工作台 | `W.md` · `建设计划` | 已核对 `valid`；人工近期任务、焦点；状态 `blocked`，前置 WB15-SAMPLE-R，展示阻塞原因。 |
| WB15-SAMPLE-NONE | 科研 | 无 | 无主计划，提示待关联。 |

样本核对了两类 `queries.query` 焦点、活动近期任务和主计划结果；两项有效计划均已记录文件哈希和核对记录。`tests/unit/test_wb13_plans.py` 另覆盖章节歧义和文件缺失，`tests/unit/test_wb13_queries.py` 覆盖分类和无关联，`tests/unit/test_wb13_context.py` 覆盖近期排序及失效标记；这三组共 9 项通过。当前仅验证服务契约，页面入口和端到端交接属于 WB-15-02 至 04，尚未验收。
