# WB-13-01 基线盘点与数据契约

观察时间：2026-11-18 10:39–10:40（Asia/Shanghai）；本报告是只读观察，不是迁移或历史重新验收。代码基线 HEAD `6b1e8786af3b73c046d9fd28d9b4f5363957fbd2`；工作区不干净，下列哈希标识实际读取内容，不能仅以 HEAD 重现。

| 来源 | SHA-256 |
|---|---|
| `docs/workbench/wb13_implementation_plan.md` | `94e97d06f96290e41734598e017ea74d7fdfa50eb4ea7abd5a154e95396e81fb` |
| `docs/workbench/management_improvement_plan.md` | `686f4b7c026015c2d6c32bd291d7bd71466bbeec53c8d36271` |
| `docs/architecture/project_workbench_plan.md` | `c878b7893959646cb2fd44ee2b95a7c50f7069644f9d291eb0bc6b0dab14590c` |
| `src/catalyst_ai/storage/workbench.py` | `b13a203c1bd991753861e0656b9b4acd66d056d9e843251cca2a618c15315807` |
| `configs/workbench.yaml` | `2aa1ea98a33f0cf5c57b9921a9e17faa03d643945fc93d427a9864f34053cb59` |

## 实际基线与差异

配置指向 `data/workbench.sqlite`、项目 `cat-ai`。以 SQLite 只读连接、单个读事务观察 `user_version=7`；代码目标也是 7。项目焦点为空。任务 10 个：S1A-01、S1B-01、S2-01～06 为 done，S3-01、S3-02 为 planned；15 条依赖、40 条验收标准、18 条 review、55 条 evidence、142 条活动、120 条请求记录。没有 WB 任务。索引有 48 个 artifact（其中 document 7）、55 个固定版本、23 次扫描和 586 条观察；research_record 8、model_run 4、prediction_job 3。计数仅为观察时点快照，后续实施必须重查。

现有任务服务提供依赖、状态流转、版本化标准、验收、乐观修订、幂等和活动记录；索引提供文件版本与观察；project 有单个旧焦点。缺少任务类别、历史交付引用、路线节点及关联、计划章节核对和分类焦点/近期安排。状态机、科研阶段标签和 milestone 的既有含义不改变，类别不是状态，节点父子关系不是执行依赖。

历史范围以 [建设进度承接](../architecture/project_workbench_plan.md#21-既有建设进度承接) 及 [WB-02](wb02.md)、[WB-03](wb03.md)、[WB-04](wb04.md)、[WB-05](wb05.md)、[WB-06](wb06.md)、[WB-08](wb08.md)、[WB-09](wb09.md)、[WB-10](wb10.md) 为依据：WB-01 是草案，WB-05 已实际导入；WB-02～06、08～09 有记录的交付；WB-10 为模型证据台账，训练接入仍有剩余；WB-07、11、12 保留未交付范围，入口或占位不等于整体完成。历史文档证据不等于管理库验收记录。工作区还有未提交的架构文档、S2/S3 代码、配置及模型运行成果，属于并行工作，不能覆盖或视为本任务产出。

## 最终存储契约

以下名称固定为 WB-13-02 的目标，均位于管理库；后续变更须新增版本迁移。所有新实体具有稳定 ID、project_id，引用必须验证同项目。文本时间使用 UTC ISO 8601；修订从 1 开始。写接口均要求 actor、request_id、预期 revision，采用现有事务、request_log 和 activity 模式：同请求同内容重放原结果，不同内容冲突；修订过期、主键/唯一约束冲突返回冲突，缺失对象返回未找到，非法输入、跨项目、环与非法类别返回校验错误。实体及关系采用软停用或追加历史，禁止级联删除历史；变更、修订和活动同事务提交。初次创建无预期修订；无实际变化不增加业务修订。Web 映射沿用 404/409/422。历史记录保存旧值、新值、原因、actor、时间和修订，来源失效只标待复核。

| 对象及物理落点 | 字段、身份、约束及修改接口 |
|---|---|
| 任务类别：`task.category`、`task_category_revision` | category 可空或 `research`/`workbench`；空为待核对。任务 ID 沿用原 ID；历史表以 `(task_id, revision)` 唯一，保存 project_id、旧/新类别、原因、actor、时间。`set_task_category` 使用任务 expected revision，更新类别、任务 revision 和历史，不改目标、标准、状态或验收。只按目标及证据预览回填，未知保留空。 |
| 历史交付：`workbench_delivery`、`workbench_delivery_revision` | 稳定 ID，project_id、original_wb_id、delivered_scope、remaining_scope、source_path、source_section、source_sha256、original_delivered_at（未知可空）、registered_at、可空 task_id、revision、active；每项目 original_wb_id 唯一。`upsert_workbench_delivery` 追加修订；来源路径和章节失效保留原记录，正式任务可后关联，禁止伪造原验收。 |
| 科研节点：`research_node`、`research_node_revision`；关联 `task_node_link`、`task_node_link_revision` | 节点 ID、project_id、stage、parent_id、sort_order、source_path、source_section、source_sha256、revision、active；关联 ID、project_id、task_id、node_id、role（`primary`/`reference`）、revision、active。活动关联 `(task_id,node_id,role)` 唯一，活动 primary 每任务最多一条；同项目、无自环/祖先环、阶段关系合法，仅 research 任务可关联。`save_research_node` / `save_task_node_link` 验证并记录修订；停用保留历史，汇总按 task ID 去重。 |
| 计划：`task_plan_reference`、`task_plan_reference_revision`、`task_plan_verification` | 引用 ID、project_id、task_id、document artifact ID、project-relative path、section locator、purpose、is_primary、revision、active；每任务活动主计划最多一条，相同活动任务/文档/路径/章节/用途唯一。核对记录 ID、reference_id、project_id、文件 SHA-256、actor、时间及引用修订，追加不可覆盖。`save_task_plan_reference`、`verify_task_plan_reference`；检测实际文件和唯一章节，缺失、歧义、路径越界或哈希变化返回明确结果，不自动改核对记录。复用索引的路径安全边界。 |
| 分类上下文：`category_context`、`category_context_revision`、`category_recent_task`、`category_recent_task_revision` | context ID、project_id、category、focus_task_id、revision；项目/类别唯一；近期引用 ID、context_id、project_id、task_id、sort_order、revision、active，活动 context/task 唯一。`set_category_focus`、`set_category_recent_tasks` 验证任务项目和类别，按上下文预期修订整体事务写入；任务完成、取消或改类别后保留引用历史并提示修正。 |
| 文档用途：`document_purpose`、`document_purpose_revision` | ID、project_id、document artifact ID、purpose（`construction_plan`/`research_plan`/`execution_plan`/`acceptance`）、适用 category（可空表示通用）、revision、active；活动的项目/文档/用途/类别唯一，空值须用表达式索引或等效约束确保唯一。`set_document_purpose` 验证 artifact 属于项目且 kind 为 document；复用索引，不复制正文。 |

上述每个 `_revision` 表以实体 ID 和 revision 唯一并保存完整变更前后、actor、时间、原因；关联和近期顺序变更亦如此。SQLite 部分唯一索引只约束 active 行；跨项目、节点环、单主计划等由同一写事务中的服务校验和可用的数据库约束共同保证。批量排列必须先验证全集及预期版本，失败全回滚。字段及约束不替代后续服务与迁移测试。

## 兼容、迁移和保护

旧 `list_tasks(path, project_id)` 及 URL 继续返回所有原任务，不因空类别被过滤；新查询显式支持 `research`、`workbench`、`all`、`unclassified`，all 包含空类别并单列。旧创建不传 category 时存 NULL；不推断 ID 前缀。旧焦点仍为兼容事实源：迁移时若焦点类别确定则写对应 category_context，未知保留 project.focus_task_id 并提示；新旧入口的读写适配在 WB-13-06 中统一为同一事实源，无法确定类别时不得覆盖旧值。分类焦点各自独立，不静默覆盖另一类别。

WB-13-02 实施前重新核对活动库、编号、修订、文件版本；用 SQLite backup API 取得一致备份，拒绝覆盖已有备份，在隔离副本按下一可用版本增量迁移并重复执行验证。迁移 DDL、版本号和数据变更须处于同一原子事务，失败回滚；不改已应用的迁移历史。回填先输出任务、目标、依据、旧值、拟议值、预期 revision、冲突和未知项，再显式应用；过期重新预览，重复应用无额外业务修订。

迁移前后在一致快照上按主键排序导出并逐项比较 task 原字段、dependency、criterion、review、evidence、artifact 及其 location/revision、活动与请求记录；task 只允许授权的类别及相应 revision 变化，核对差异须解释。记录 schema、计数和规范化行哈希；对计划及历史来源文件记录路径和 SHA-256，并报告缺失。对领域库、原始数据、模型和特征文件建立操作前后清单及哈希，针对本操作涉及对象比较，区分同期合法更新。完整备份除管理库外还须包含引用的源文件或明确可用的备份位置；恢复演练检查引用、旧验收和新对象。旧备份在新代码下迁移；新库不交给旧代码直接打开。回退需先导出迁移后新增写入并协调合并，禁止直接用旧备份覆盖同期工作。

本次未运行迁移、回填、备份恢复或测试，以上是实施契约和后续验证要求；实际库可能继续变化。
