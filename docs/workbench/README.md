# WB-01 首次导入草案与管理对象契约

日期：2026-11-13（Asia/Shanghai）。本目录是待确认的导入草案，不是已导入的管理库，也不代表新验收。机器可读的[清单](first_import.json)由[JSON Schema](first_import.schema.json)约束；任务和来源 ID 在重复导入时应保持不变。路径相对工作区根目录，来源的 section 用于人工定位，实际导入前应重新检查文件、记录 SHA-256 和 Git 状态；文件缺失时保留引用并报告，不静默替换其他版本。原始成果和数据库未修改。

## 阶段与里程碑关联

| 总体阶段 | 首批关联 | 范围 |
|---|---|---|
| A 工程 | S1-A | 存储与导入基础；不是整个工程阶段已完成 |
| B 治理 | S1-A、S1-B | 来源、资格、属性与映射；构建沿用治理边界 |
| C 预测 | S1-B、S2、S3 | 构建、配置、训练、预测与比较 |
| D 诊断 | S2、S3 | 家族对照资格和模型评价；不宣称全部诊断完成 |
| E 推荐 | 暂无 | 后续阶段，未拆分任务 |
| F 反馈 | 暂无 | 后续阶段，未拆分任务 |

S1-A、S1-B 为 S1 的两个里程碑；R1/R2 是实验预设，F_cond/F_base/F1/F2 是特征集，均不是里程碑。R1 已有比较和预测证据，但不代表 S2/S3 整体完成。S1-A 的 done 是来自历史验收的导入建议，正式管理验收记录和证据快照须在后续导入时建立；S1-B 保持 in_review。清单列出具体检查项及 S2 拆分，负责人和计划日期留空。

## 差异预览

`DIFF-S1B`：总体设计顶部和进度“下一步”仍称 S1-B 待完成；[构建说明](../s1_b_build.md)指向 v4 selection/features。两者记录的是不同时间的状态，不能自动用文件存在推断验收完成。建议复核清单 S1B-01 的各项，特别是 454/47/52 分区、逐值核对、输入版本与测试证据，并由操作员保存结论；再更新相关状态文档。现有数据不声明模型性能提升，来源接受不等于逐篇原文核验。

## 后续持久化管理 schema（逻辑契约）

下表定义 WB-02/03 的目标对象，不表示数据库表或迁移已实现。所有对象属于 project；ID 稳定且项目内唯一，时间以 UTC 保存，展示时转换为 Asia/Shanghai。外键需校验同项目归属；历史修订和事件追加保存。

| 对象 | 身份、字段及关系 |
|---|---|
| project | id、name、workspace_root、timezone、focus_task_id、revision |
| milestone | id、project_id、name、goal、planned_date、sort_order |
| task | id、project_id、milestone_id、title、goal、stages、primary_stage、status、priority、owner、planned_date、criteria_version、revision |
| task_dependency | predecessor_id、successor_id、created_at；关系唯一，禁止自依赖和环 |
| acceptance_criterion | id、task_id、criteria_version、description、required、sort_order |
| acceptance_review | id、task_id、criteria_version、conclusion、actor、time、检查结果及固定证据版本快照 |
| artifact / artifact_revision | 逻辑 ID、类型、内容 ID；修订包含版本、位置、文件及内容哈希、输入引用、检测状态和时间 |
| task_artifact | task_id、artifact_revision_id、purpose、criterion_id |
| decision / decision_revision | ID、项目、当前版本；修订包含内容、状态、来源、替代关系及时间 |
| task_decision | task_id、decision_id、影响说明 |
| activity_event | ID、项目、对象、动作、操作者、UTC 时间、摘要、对象修订号；只追加 |
| index_scan | ID、项目、范围、起止时间、状态、错误、已发布代次 |
| run_reference | ID、项目、原运行标识、报告、输入绑定、结果、来源及观察时间 |

任务状态与转换以[方案第5节](../architecture/project_workbench_plan.md)为准；修订号、请求 ID、事件和状态变更应在同一事务内处理，过期写入返回冲突。证据变化不覆盖历史验收；已完成任务标为证据待复核。管理库迁移前使用 SQLite 备份接口。导入应先预览并由用户选择确认，重复导入按稳定 ID 更新关联而不重复创建；本阶段没有执行导入。

## 验证

清单通过 Pydantic 契约校验，包括来源引用、任务依赖存在性、循环依赖和主阶段归属；来源路径在当前工作区存在性单独核对。JSON Schema 仅约束结构，跨对象约束须通过 Python 模型验证。源文件是工作区版本，部分未跟踪或被 Git 忽略，须随管理库另行备份。
