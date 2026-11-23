# WB-16-01 开工基线与分类契约

2026-11-20 按 `configs/workbench.yaml` 从正式管理库只读备份：[一致性副本](../../artifacts/wb16-01-samples/baseline.sqlite)、[分类查询](../../artifacts/wb16-01-samples/baseline-query.json)。schema 8，`quick_check=ok`，外键检查无错误；WB-13、WB-14、WB-15 为 done，WB-16 编号尚未占用。科研 12 项、工作台 22 项均为 done，待分类 0 项。副本是登记前观察值，文件状态仍依赖观察时工作区。工作区有未提交改动，不能把 HEAD 当作完整版本。

登记前复核发现其他工作新增了科研任务 S4-03（进行中、关联科研计划和路线），因此重新取得[登记基线副本](../../artifacts/wb16-01-samples/registration-baseline.sqlite)及[查询结果](../../artifacts/wb16-01-samples/registration-query.json)：科研 13 项（12 done、1 in_progress），工作台 22 项 done，待分类 0，WB-16 编号仍未占用。登记事务以该副本逐表比较，保留并发工作。

四条活动文档用途分别为 S4 科研执行计划、WB-13/14/15 工作台执行计划。历史交付 12 项均未关联任务且来源检测 changed；保留登记的章节、哈希和原始内容，不能从编号推断任务关联。主计划及具体任务结果见查询快照。

## 现有入口

| 入口 | 当前缺省范围及参数 |
|---|---|
| `/` | 项目级任务及固定里程碑；无分类参数 |
| `/tasks` | 项目级；`status`、`stage`、`q`，缺省为空 |
| `/documents`、`/artifacts` | 项目级；当前无分类参数 |
| `/next-work` | `category=research`；仅 research/workbench |
| `/api/workbench/v1/query` | `category=all`；另支持 research/workbench/unclassified，非法值 422 |
| `/roadmap` | 科研范围；`node`、`task`、`view` |
| `/tasks/{id}` | `node`、`category` 用于返回上下文 |
| `/tasks/{id}/plans/{reference_id}` | `category`；`/artifacts/{id}` 另支持 `version`、`offset`、`task`、`reference`、`category` |

## 共用查询契约

以项目 ID、分类和任务 ID 限定范围，分类取 `research`、`workbench`、`all`、`unclassified`。任务状态计数按 ID 去重，取消项单列；有效完成使用最新验收及固定证据可用性，原 done 状态不变，待复核另计。路线使用 `roadmap.snapshot` 的节点及任务集合、纳入范围和证据复核，不将路线分母当作全部任务分母。保留 `scope`、`observed_at`、`source`、任务 ID/类别/状态、`counts`、焦点与活动近期任务、主计划及缺失项；文件检测为实时观察而非数据库快照。

文档分类依据活动用途及同项目活动计划引用，跨类可共享、全部范围按文档 ID 去重；证据不足或待复核列入待核对。成果依据明确的同项目任务关联及验收记录，按成果 ID 去重，历史证据保留固定版本；不能靠编号或文件名推断分类。历史交付只用登记的 `task_id` 关联，未关联和来源变化分别展示。

基线查询快照生成于修复前，其 `historical_deliveries` 被近期任务历史覆盖，不可用于历史交付核对；已修复变量覆盖，历史数据以 `deliveries.list_historical_deliveries` 和修复后的查询为准，并增加分类回归。

## 隔离样本

[脚本](../../scripts/wb16_01_samples.py) 在副本及独立工作区验证两类活动任务、焦点、阻塞与跨类前置、有效主计划、来源变化和章节缺失：[结果](../../artifacts/wb16-01-samples/sample-results.json)。隔离工作区重定向使原有文档的检测结果不能代表正式文件状态。

[补充样本脚本](../../scripts/wb16_01_edge_samples.py) 在新建隔离库验证空项目、待分类、跨类用途及同一文档的两项主计划、两类任务共用同一固定证据、历史待补登及显式关联、来源变化与固定证据失效；[结果](../../artifacts/wb16-01-edge-samples/results.json)记录 ID、版本和观察结果。分类列表聚合属于 WB-16-02/03，样本验证底层依据，并不代表页面验收。
