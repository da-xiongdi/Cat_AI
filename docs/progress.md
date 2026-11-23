# 实施进度（截至2026-11-23，Asia/Shanghai）

## 2026-11-23 科研进度

S4-03 已完成正式验收；S4-04 九组固定内部实验、证据核对、铜基配对及适用范围分析已完成，并在正式工作台登记验收为 `done`。铜基模型未显示可确认的稳定增益；跨 DOI 与随机实验的样本及覆盖不同，不能直接作因果归因。结果不构成外部验证。[S4-04 最终报告](s4_04_final_report.md) · [证据复核](s4_04_evidence_audit.md) · [对照分析](s4_04_comparison_analysis.md) · [适用范围](s4_04_applicability_coverage.md)

以下 2026-11-20 条目保留当时状态，科研任务当前状态以上述记录和正式工作台为准。

## 2026-11-20 工作台进度

WB-15 五个子任务和父任务已在正式管理库通过验收。科研与工作台建设可分别查看近期任务、依赖和历史，并从任务进入现有文档预览的对应章节。改类后留在旧分类的人工安排会保留正确的主计划链接和返回路径。全量 248 项测试、Edge 三种尺寸及发布前后备份恢复通过。工作台建设下一项为 WB-16 页面整合与维护入口。[WB-15 验收与交付](workbench/wb15_05_acceptance.md) · [统一排期](workbench/management_improvement_plan.md)

WB-16 已在正式库登记，WB-16-01 已通过验收。WB-16-03 完成任务、文档与成果分类筛选的开发验证，正式库副本及 Edge 三种尺寸检查通过。历史建设交付的 12 条来源版本差异已列入维护页复核范围。[WB-16 实施方案](workbench/wb16_implementation_plan.md) · [WB-16-03 验证记录](workbench/wb16_03_verification.md)

## 2026-11-20 科研进度

S4-02 已完成全体系和铜基数据视图冻结并通过正式工作台验收。593 条目标父记录中，15 条实验身份未决记录暂排但保留原始证据；目标视图全体系 578 条、铜基 211 条，共同特征资格分别为 542 条和 211 条。铜基覆盖 16 个 DOI，前四篇贡献 66.4%。用户确认探索性训练至少 100 条及 5 个独立分配单元、测试至少 20 条及 20 个独立分配单元；默认 80/20、训练内五折，实际分组和覆盖留待后续核验。尚未启动 S4-03，未划分或训练。 [S4-02 冻结与验收](s4_02_acceptance.md) · [S4-01 交付与证据](s4_01_acceptance.md) · [下一阶段实施计划](Cat_AI_next_stage_execution_draft_20261120.md)

## 2026-11-19 结论与当时的下一步

**科研主线已推进至 D 阶段上游能力建设。** 正式管理库中 S1 两项、S2 六项、S3 两项共十项均为 `done`。S3-01 的 R2 默认预设选中 F_base/ExtraTrees，全部 OOF 论文等权 MAE 为 5.373464 个百分点，入口可用为 274/454 条（含 caution），开发验证集可用为 28/47 条。S3-02 已完成配置训练、指定模型包预测、失败路径和独立重放验收。见 [S3 比较报告](s3_01_comparison.md)和 [S3-02 验收登记](../artifacts/reports/s3-02-20261118-02d/registration.json)。

**D-06 本轮评价流程建设已完成，正式独立评价待数据。** D-04 v2 协议、冻结材料核查、独立评价入口和报告输出已就绪，软件测试已通过。用户确认本阶段聚焦上游能力，具体验证留待有合格独立评价集时开展。TheMeCat 的权威性已认可，后续资格审查针对新增候选来源。见 [D 阶段实施分解](d_implementation_plan.md)和 [D-06 评价流程](d06_evaluation_workflow.md)。

**工作台建设的下一步是 WB-14 科研路线图。** WB-13-08 已完成正式部署，八个子任务和 WB-13 父任务均在 schema 8 正式库通过验收。九条主计划已核对，12 条历史交付和 14 个科研节点来源有效，8 条科研任务关联已复核；部署后恢复核对通过。后续依次推进 WB-14～WB-17，WB-07 训练接入列为本轮之后的优先候选。[WB-13 正式部署与验收](workbench/wb13.md) · [WB-14 实施计划](workbench/wb14_implementation_plan.md) · [统一排期](workbench/management_improvement_plan.md)

**当前优先级**是整理 D 阶段上游交付和证据，工作台建设可沿自己的顺序推进。B3 全库逐条人工核验按原决策暂缓，A/B1 家族对照待可信逐记录标签，E/F 筛选和实验闭环留在后续阶段。

### 近期阶段记录

2026-11-18 补齐 WB-14 科研路线图实施方案，按数据与统计、树形列表、画布、任务互定位、节点维护、专项验收六步交付。实施从 WB-13 父任务验收通过后启动。[WB-14 实施方案](workbench/wb14_implementation_plan.md)

2026-11-18 WB-13 计划编制时，确定按 WB-13-01～08 顺序交付。细项与通过条件见[任务分解](workbench/wb13_implementation_plan.md)。

2026-11-18 S3-01 完成独立核算与比较报告，S3-02 完成端到端、失败路径及独立重放。见 [S3-01 比较报告](s3_01_comparison.md)和 [S3-02 验收登记](../artifacts/reports/s3-02-20261118-02d/registration.json)。

2026-11-18 S2-03 收尾验收完成：资格报告、553条逐记录状态、36个DOI及原分区覆盖已固定；缺少经核验的标准家族标签，全部 A/B1 家族对照有依据地跳过，不阻断统一模型。管理库备份、副本演练后登记为 done（当时 revision 6、criteria_version 2），完整性和外键检查通过，领域库、原件、快照及其他任务未变。S2 六项任务验收后进入 S3-01 和 S3-02。详见 [S2-03 验收](s2_03_acceptance.md)。

2026-11-18 S2-02 工程验收完成：默认基准和自定义多模型 CLI、单模型 Python、模型包重载及单条/混合批次预测贯通，R1旧包47条结果完全重放。新增 F1/F2 边界及包绑定篡改回归；全量 pytest **210 passed**，Ruff 检查及格式检查通过。管理库备份、副本演练后依次登记 S2-06、S2-02 为 done，详见[验收与交付清单](s2_02_acceptance.md)。该批验收时 S2-03 为 ready，现已按上条记录另行收尾；S3 正式配对比较和整体验收仍待执行，本次不产生科研性能结论。

2026-11-18 工作台排期统一：既有 WB 交付与剩余范围继续保留，本轮原 WP1–WP5 依次映射为 WB-13–WB-17，按“分类与关联基础 → 科研路线图 → 下一步与计划交接 → 页面整合与维护入口 → 整体验收”执行。WB-07 训练接入列为本轮之后的优先候选，WB-11/12 按 E/F 阶段安排。详见 [统一顺序](workbench/management_improvement_plan.md#0-统一执行顺序与当前下一步)。

科研需求基准：[项目开发指引](project_development_guide.md)第9节的 A–F 路线；增量验收依据见[实施与验收清单](implementation_amendment.md)和[TheMeCat 专项方案](themecat_implementation_plan.md)。本节汇总当前状态，下文按日期保留历史记录；历史中的“无真实快照”“下一项 B1”“尚未训练”等不代表现状。

整体架构与实施主线见[总体设计](architecture/system_design.md)。本文件集中维护当前状态、运行证据和当前下一步；系统模块/版本链在总体设计维护，任务公式和细节在专项方案维护。

2026-11-17 S2方案与任务部署：专项方案更新为v0.8，明确S1-A/S1-B已验收；保留S2-01/02/03，新增S2-04特征适配、S2-05训练评价、S2-06增强模型包与预测，S2-02负责入口集成及工程回归。执行顺序与逐项验收见[S2任务分解](s2_implementation_plan.md)，实际管理库部署和备份证据见[部署记录](workbench/s2_deployment.md)。本轮只更新方案及管理任务，未实现训练配置、未训练F1/F2、未形成新的性能结论。

2026-11-17 S1-B 工程验收完成：v4 完整重放、553 条记录/5,530 个逐值索引、公式、换序/合并及规范预测输入一致性全部通过，192 项测试通过，原件和领域库哈希不变。S1B-01 已完成，DIFF-S1B 已解决。当前研发下一步为 S2 配置训练与增强预测绑定，见 [S1-B 验收](s1_b_acceptance.md)。下方带日期的旧进展保留历史，不再表示当前待办。

2026-11-17 WB-06 预测执行已交付：网页提交固定 R1 模型批量预测，独立 CLI worker 执行，逐行结果/日志自动登记，支持取消、心跳中断识别和关联重试，管理库 schema 7。真实 R1 数值与原 Python 入口一致，浏览器与独立进程恢复已验证。执行成功与科研验证、任务验收继续独立，见 [WB-06](workbench/wb06.md)。当时下一项安排为 WB-07 扩展构建和训练操作；当前工作台顺序以 2026-11-18 的增量排期为准，WB-07 原任务和领域依赖保留。

2026-11-17 WB-05/WB-08 收口：实际库导入 7 项任务并验证重复导入不覆盖验收，关联固定成果，完成 S1-A 历史工程范围管理验收；四组导航、独立研究分类、技术问题、总览范围和进度导出已实现。管理库 schema 6，完整备份恢复及真实 Edge 桌面/窄屏流程通过。S1-B 仍需科研交付复核，S2/S3 不随工作台交付完成。详见[WB-05记录](workbench/wb05.md)与[WB-08记录](workbench/wb08.md)。

2026-11-16工作台增量交付 WB-09，补齐数据基础登记、36 项字段领域映射、v1.0/v1.1 JSON/CSV 迁移校验、事务重试和管理库/成果备份恢复。全量 185 项 pytest 及隔离 Edge 浏览器主流程通过，详见[WB-09交付记录](workbench/wb09.md)。

2026-11-13新增[Web项目管理工作台方案](architecture/project_workbench_plan.md)，规划项目总览、任务验收、成果索引、决策及文档浏览。该日期交付为规划文档，首版建议按WB-01至WB-05实施，详细技术选型与分期验收见方案。

2026-11-13当前汇总：3.1–3.3 R1基础路径及S1-A数据准备与资格检查已验收，联合支持553/593条。S1-B物化计算、R2及3.4配置仍待完成，下一任务为S1-B。详见[S1-A收尾验收](s1_a_acceptance.md)；下文历史记录保留当时状态。

## 当前阶段：C 特征工程与预测能力完善，D 辅助评价

TheMeCat 的数据治理、冻结、DOI 分组、特征构建、模型比较、保存加载和独立预测已连通，S1–S3 已完成本轮验收。当前科研重点转向 D 的模型适用性与独立验证，沿用 C 已交付的可配置训练预测能力。E/F 保留为后期路线，现有筛选接口与探索清单用于后续准备。

**2026-11-10 用户重申的执行共识：先完善上游，从特征工程和性能预测开始；实验属于后期。** 当前模型研究不以补齐实验候选、设备或前驱体约束为前置条件，也不把正式筛选、批次或实验反馈列为近期任务。B3继续按既有决定暂缓。

### 预测模型是否已经确定

当前工作基线为 **F_base/ExtraTrees**，预测目标为 CO₂ 转化率，输入为完整来源角色／物种的材料 mol% 和四项工况。R2 同子集比较中，ExtraTrees 的 F1、F2 相对 F_base 的全部 OOF 论文等权 MAE 分别增加 0.557559、0.514140 个百分点，本轮保留 F_base。配置入口仍支持 F1/F2 和白名单内的自定义模型参数。后续能否推广到独立来源和新配方，取决于适用性复核和独立验证。见 [S3 比较报告](s3_01_comparison.md)。

| 总体任务 | 已实现/已运行的范围 | 尚未完成的验收或研究证据 |
|---|---|---|
| A — 骨架与数据契约 | 首期工程交付完成；实体关系、CLI、环境和容量约束已有测试 | 历史打包验收对应当时版本，不代表当前代码已重新发布 |
| B — 接入与治理 | 首期工程链路完成；B0–B2 已实现；820 条 v2 修订中609条 curated、211条 staged；冻结593条 CO₂ 转化率记录 | B3 按用户决定暂缓；人工审核事件0；绝压为用户假设；不把来源接受称为逐行核验，211条阻断仍保留 |
| C — 特征与基线 | R1 基础路径、S1–S3 已验收；S1-B 保留 454/47/52 条，S3 选中当前工作基线 | 材料家族留出、工艺建模及甲醇目标扩展留后续 |
| D — 解释及适用域 | I5 已交付历史诊断和模型卡。D-06 本轮已完成独立点预测评价流程建设 | 正式独立评价待合格数据，预测区间尚未校准 |
| E — 筛选与推荐 | 已实现显式候选筛选、固定工况预测、约束输入检查和槽位上限；另有4项探索性组成清单 | 未取得真实制备路线、前驱体、设备与成本/风险依据；未完成真实候选筛选、Pareto/信息增益排序、对照/重复设计和实验批次规划 |
| F — 实验反馈与迭代 | 保留通用实验数据接入契约及容量检查 | 候选到实测的批次状态流转、计划/实际关联、失败案例回灌、新快照重训比较及真实实验闭环均未完成 |

以上状态是对总体设计的映射，不改变原开发指引。数据源接受策略和压力假设来自此前用户决策；原指引中的人工核验要求仍是后续强化证据的路径，当前快照显式标记 `published_dataset_accepted_not_row_verified`。

### 已验证成果与证据

- 数据：[治理摘要](../artifacts/reports/themecat-governance-20261110/summary.json)记录820条修订、609条治理通过；CO₂转化率593条合格，227条排除（211条未curated、16条缺目标）。原件保留，修订可追溯。
- 划分与特征：[I2说明](../artifacts/reports/themecat-i2-20261110/README.md)和[I3特征表](../artifacts/reports/themecat-i3-20261110/features.json)。论文分组隔离不证明未知跨论文样品独立。
- 当前模型比较：[R1验收摘要](../artifacts/reports/themecat-r1-comparison-20261112-verified/README.md)中F_base的OOF论文等权MAE为Dummy 5.906、ExtraTrees 5.546、Ridge 7.301个百分点，按既定规则选中ExtraTrees；OOF入口可用274/493。validation全体诊断MAE 4.128、入口可用29/47；已查看历史test全体诊断MAE 3.429、入口可用32/53。全体诊断包含未见物种，不能当作全体记录均可用的预测性能；历史test不参与选模。
- 历史 R1 独立预测在 47 条 validation 输入中有 29 条可用，模型加载和批量结果已复核。S3-02 随后验收了默认和自定义训练、指定包预测及旧 R1 包兼容。见 [R1 验收结果](../artifacts/reports/themecat-r1-prediction-20261112-final/prediction-verification.json)和 [S3-02 全链路记录](s3_02a_execution.md)。
- 历史基线：[I4报告](../artifacts/reports/themecat-i4-20261110/report.json)中验证集选中Extra Trees，测试MAE 2.872、RMSE 4.368个百分点，R² 0.270；测试集53行、5个论文组。该指标属于旧特征及选模路径，不替代当前R1分组评价，也不证明新的材料或批次泛化能力。
- 诊断及探索：[I5模型卡](../artifacts/reports/themecat-i5-20261110/model_card.md)与[组成探索清单](../artifacts/reports/themecat-exploration-20261110/README.md)。测试21/53行含训练未见组分，经验区间覆盖39/53；4项组成仅供讨论，不是已批准实验计划。
- 最近一次代码核对（2026-11-12）：`.venv/Scripts/python.exe -m pytest -q`：**120 passed**；同一环境的`ruff check src tests scripts`与`ruff format --check src tests scripts`通过（63 files already formatted）。已有模型包可加载，47条validation输入重放后的JSON结果与保存结果一致。本次未重新训练、筛选、审核或冻结数据；软件测试与预测重放不构成新增科研验证。
- 交付版本边界：当前工作区仍含未提交修改；R1核心代码、脚本、测试、方案和模型目录中有Git未跟踪文件。本汇总描述工作区可核对状态，不代表Git HEAD、已发布包或新环境安装已同步到该版本；保留现有文件，不以文档统一自动提交或发布。
- 2026-11-10历史文档检查：当时5份更新文档中的78个本地文件链接均存在，`git diff --check`通过；两份开发指引SHA-256仍相同且未改变（`64ba32d98cdfd4778cef1158f597e2179376c380ee3a816314dd9c31664a757e`）。本轮文档核对另记于下方2026-11-12记录。

### 本轮特征与预测交付回顾

S1-A已完成需求分类、来源与许可适用性核查、v2属性/映射入库、记录级来源处置和分层资格报告。正式联合支持553/593条，较v1新增5条LaMn/Cu系列；39条InNi3O0.5及1条CoGaAlO4证据不足，隔离且保留原因。来源接受仍不等于逐行原文核验，没有事实更正或新目标快照。详见[验收说明](s1_a_acceptance.md)、[许可核查](s1_license_review.md)和[目录接口](s1_catalog_interface.md)。

| 顺序 | 步骤 | 当前状态与边界 |
|---|---|---|
| 1 | S1-A需求与数据准备 | 已验收；正式资格同时绑定属性、映射和记录级处置版本；覆盖不等于已计算特征 |
| 2 | S1-B计算与特征构建 | 已验收；553 条固定特征、逐值索引、独立公式、换序/合并及规范输入复核通过 |
| 3 | S2模型与参数入口 | 六项任务均已验收；配置、训练评价、增强模型包及Python/CLI集成完成；家族资格检查完成，A/B1有依据地跳过 |
| 4 | S3运行与验收 | 两项均已验收。S3-01 完成共同支持子集上的正式配对比较，S3-02 完成整体端到端验收与登记 |

正式运行、逐条结果、验收与模型包交接可从 [S3-01 比较报告](s3_01_comparison.md)和 [S3-02 全链路记录](s3_02a_execution.md)定位。S2-03 已记录家族标签缺口，压力继续沿用绝压假设。

### 2026-11-13：S1-A收尾验收

- 固定mendeleev-data提交、数值原件和数据仓库MIT声明，236项值/状态与v1一致。登记v2多中心/小数计量映射及记录级处置，39条疑似O→C均登记evidence_insufficient、不生效更正；CoGaAlO4另1条保守隔离。执行者明确为自动证据/约定检查，不伪造人工审核。
- 新增规范化属性/物种单项查询和独立证据持久化。真实库重复迁移、dry-run/导入/重复导入、旧覆盖回放及正式资格重复运行通过。train支持454/493、validation 47/47、历史test 52/53；[逐记录/物种/DOI/分区资格](../artifacts/reports/s1-a-acceptance-20261113-final/qualification.json)保留分母和原因。
- 原事实表、原件、目标/资格快照、原DOI划分、旧配置和v1报告保持一致，SQLite完整性ok、外键错误0；升级前库备份留存，见[最终验收](../artifacts/reports/s1-a-acceptance-20261113-final/acceptance.json)。
- 本轮全量pytest、Ruff检查/格式检查、正式资格CLI重放及文档检查结果见[验证记录](../artifacts/reports/s1-a-closeout-20261113/verification.json)。S1-A完成，S1-B/S2剩余项待实施；未提交Git或发布。

### 2026-11-12：方案文档修订及用户顺序澄清（仅文档）

- 已完成：按“特征需求→导入/数据库→计算模块→模型和训练预测框架＋参数入口→运行验收”重排近期任务，补充存储/计算职责、用户配置及失败行为，保留科学计量和分组评价边界。
- 历史方案修订：此前R1/R2顺序开发安排改为实验预设，ADR-017替代ADR-016的相应顺序和参数限制；参数可配置不等于自动搜索或允许泄漏字段。
- 未执行：代码开发、导入/计算/数据库升级、新训练/预测、数据冻结或人工核验；所有新能力保持规划状态，不将历史测试和指标记为本轮结果。
- 本轮文档核对：8份文档的110个本地链接、6个章节锚点及1个YAML配置示例检查通过，错误0；两份开发指引与Git HEAD逐字节相同，SHA-256仍为`64ba32d98cdfd4778cef1158f597e2179376c380ee3a816314dd9c31664a757e`；`git diff --check`通过。本轮未运行pytest/ruff或科研评价。

## 历史交付与验收记录

以下保留A+B初次交付及后续切片的原始时间语境，当前阶段以上文汇总为准。

## 已实现功能

| 范围 | 已运行验证的实现 | 证据 |
|---|---|---|
| Task A 骨架 | src包、pyproject、CLI、YAML配置、独立Python环境、uv锁、可安装wheel/sdist | `artifacts/reports/acceptance/wheel_install.txt`；安装位置位于独立环境site-packages |
| Task A 契约 | 来源/定位、配方/成分、步骤化合成批次、测试工况、性能观测、独立表征；一对多ID及外键 | `tests/unit/test_contracts.py`、`test_boundaries.py`；`tests/integration/test_ingest.py` |
| Task A 容量 | 默认4；可配1–6；配置/契约/CLI均拒绝超容量 | pytest容量测试；CLI smoke 的默认、6槽、7槽和5个候选超默认4槽路径 |
| Task B 接入 | 明确来源/演示标识的UTF-8 CSV/JSON；dry-run；原件哈希留存；输入物理行/JSON索引追踪 | `cli_smoke.json`；`quality_report.json` |
| Task B 治理 | 百分数与闭合、零/未知/未报告/不适用/未测、温度/绝压基础单位、结构化GHSV基准、指标定义、来源、重复与同ID冲突 | unit质量/边界测试及integration导入测试；规则详见数据字典 |
| Task B 持久化 | SQLite领域实体、全部行staged档案、无block记录curated、JSON/可读摘要；默认pending | 工作区模拟导入1条；report/run/原件关联 |
| Task B 核验门禁 | 显式整记录审核事件、warning确认、审核内容哈希；未经审核不能生成已核验快照 | `tests/integration/test_snapshot.py`；CLI默认研究与未审核demo快照均失败 |
| Task B 快照接口 | 内容哈希命名JSON；目标定义/单位检查；核验/原件检查；幂等与拒绝覆盖；显式demo隔离路径 | 成功/幂等/篡改/审核撤销路径均通过模拟测试；无真实研究快照 |

## 已验证成果（仅软件工程）

环境：Windows / CPython 3.14.3；声明支持Python≥3.11，其他版本本轮没有实际验收。

| 实际命令 | 结果与证据 |
|---|---|
| `uv sync --extra dev` | 成功，使用uv.lock；核心运行依赖8个（含传递依赖），dev环境15个包 |
| `uv run pytest -q --junitxml=artifacts/reports/acceptance/pytest.xml` | **55 passed**，0失败/错误/跳过；见pytest.xml、pytest.txt |
| `uv run ruff check src tests scripts` | All checks passed；见ruff.txt |
| `uv run ruff format --check src tests scripts` | 30 files already formatted；见ruff.txt |
| `uv run python scripts/smoke_test.py --output artifacts/reports/acceptance/cli_smoke.json` | **14 steps passed**；隔离临时数据库，无审核批准 |
| `uv build` | 成功生成sdist和wheel；见dist目录与验收manifest中的哈希 |
| `uv pip install --python build/wheel-check/Scripts/python.exe dist/catalyst_ai-0.1.0-py3-none-any.whl` | 独立非editable安装成功，CLI --version/status可运行；见wheel_install.txt |
| `catalyst-ai ingest --source literature --input data/examples/synthetic_demo.csv --report artifacts/reports/acceptance/quality_report.json` | 1条curated、0条block，**8项warning仍保留，review_status=pending** |
| `catalyst-ai validate --run-id 7b0e94cb01574237989e9f42f75cecfd --report artifacts/reports/acceptance/quality_revalidated.json` | 数据库完整性/外键/raw哈希检查通过；重导出历史报告 |
| 生成schema与Pydantic实时schema比较 | 一致；未使用另一份手写契约替代实际校验 |

工作区实际导入：run_id=`7b0e94cb01574237989e9f42f75cecfd`，record_id=`7b0e94cb01574237989e9f42f75cecfd:1`，输入CSV物理行`2–2`。SQLite有1个来源、1个配方、1个合成批次、1个工况、2个观测；人工审核事件0，真实核验研究记录0，研究快照0。

8项warning分别为缺DOI、6个可选时间/碳平衡字段未报告、1个合成步骤温度单位暂未规范。演示数据不补造DOI/碳平衡/时间。缺关键单位/来源/定义的负例只在自动测试隔离库中验证，不污染本库。

验收索引：`artifacts/reports/acceptance/manifest.json` 保存时间、Python/依赖版本、软件/代码/配置证据、关键产物哈希。原指引与约定路径副本SHA256一致，原件保持不变。首次集成曾发现ORM提交后导出访问失效对象问题，已修复，随后全套55项测试通过；未将失败状态写作完成。

## 规划内容（尚未实现）

- Task B完整化：真实来源/授权审计、PDF/OCR/LLM抽取、字段多定位映射、复杂CSV映射、修订/冲突处理向导、版本化重治理及导出恢复工具。
- 更细粒度工艺/表征单位维度检查、极端值与同源复制检测；GHSV自由文本基准向结构化字段的人工映射。
- Parquet快照/训练表、A/B/C描述符实现、source/recipe/synthesis分组切分、真实数据覆盖分析及基线模型。
- Task C–F：模型评价/解释/适用域/不确定性、优化与推荐、实际实验计划状态机、实验反馈、模型版本迭代。
- Web UI、数据库迁移、设备控制、多人鉴权、复核人身份认证；本轮均未开发。

## 科研限制与下一轮

当前只有明确标记为synthetic_demo的结构测试输入。没有真实文献/自有数据接入，没有催化剂性能验证，没有模型训练或候选优化结论。通过单元测试不能证明实验真实性、模型可信度或跨材料泛化。

不统一异质工况性能，不从转化率/选择性推算收率或STY。组成闭合只对明确计量基准和范围执行，不自动补齐/归一化。未支持的单位保留并标风险；自动审核不存在。输入层保留pending，当前有效核验只能来自独立review_event。

快照的正常冻结/幂等路径已用显式demo模式验证；**真实research快照成功路径尚无真实数据证据**。快照当前仅冻结JSON证据包，没有训练表、分组切分或模型。SQLite与文件导出没有跨介质原子性，具体恢复边界见decisions/API契约。

下一轮真实数据工作：取得少量有授权、可定位的文献记录，确认指标与单位口径，逐项人工核验；完善真实数据治理与快照后，再按真实覆盖情况选择单一目标开展Task C。工程边界可用隔离的synthetic_demo fixtures并行验证，不据此报告科研效果。

## 2026-11-09：论文评审补充融合（本次仅文档）

- 已完成文档工作：新增implementation_amendment，将有效建议映射到原B–D任务，补充ADR-010、README入口和评审执行指令；未更改原开发指引、代码、数据库、既有接口或历史验收报告。
- 规划顺序：I1目标资格视图与覆盖清单 → I2分组清单与交叉检查 → I3组成编码与设计输入边界 → I4单目标基线；I5按原D/E/F阶段实施。
- 下一次代码任务建议仅做I1：显式记录目标准入/排除原因和样本粒度，复用现有严格快照入口，保留审核/原件/目标完整性检查。
- I1–I5均未实现、未验证；本次未新增模型或真实研究记录。文档检查结果见本次交付说明，上文55项测试等仍为此前验收记录，本次没有重新执行。

## 2026-11-09：I1目标资格视图交付

### 已实现

- datasets/eligibility.py：显式选择记录与目标定义/单位，记录纳入/排除原因、内容与证据哈希、观察ID、来源/配方/批次/工况/家族覆盖；不填标签、不覆盖原始记录。
- 多个目标观测逐条保留；不同有效time_on_stream可区分时准入，其余上下文不明整条排除；同记录目标观测部分不合格时不挑选好值绕过快照。
- dataset qualify CLI及可选--report/--freeze；冻结前重查包括排除项在内的原始选择，复用现有严格快照入口，持久保存资格清单与快照关联；模拟数据仍隔离。
- 原件丢失/篡改、治理内容变化、审核拒绝/撤销、数据类别混入等阻断冻结；旧dataset build行为保持不变。

### 已验证（仅软件工程）

证据目录：`artifacts/reports/i1-20261109/`，历史acceptance目录未覆盖。

| 实际命令（使用.venv Python） | 结果 |
|---|---|
| `python -m pytest -q --junitxml=artifacts/reports/i1-20261109/pytest.xml` | **75 passed**，包括新增20项I1用例及原有55项回归 |
| `python -m ruff check src tests scripts` | All checks passed |
| `python -m ruff format --check src tests scripts` | 33 files already formatted |
| `python scripts/smoke_test.py --output artifacts/reports/i1-20261109/cli_smoke.json` | **16 steps passed**，临时数据库，无审核批准 |
| 对工作区既有演示记录运行`dataset qualify --demo ... --report ...` | 正常退出2；1条输入、0条合格、原因not_reviewed；无快照或审核事件新增 |

实际命令参数与运行证据见manifest.json；pytest/ruff/format/smoke日志分别留存。工作区资格报告为workspace_pending_qualification.json。成功冻结与审核拒绝等路径仅在隔离synthetic_demo测试库验证，不冒充实际人工核验或真实科研结果。

### 限制与下一项规划

I1未实现逐观测独立快照、重复样独立上下文、语义定义归并、特征表、分组或模型。资格复查与快照落盘不提供多用户并发事务；关联文件写入失败可能留下已生成快照，可修复路径后幂等重试。真实研究记录/研究快照仍为0。

下一项仅I2：按明确泛化问题生成分组划分清单和集合交叉检查，不因组数不足回退随机评价。I3–I5继续规划；真实来源接入与核验仍需推进。

## 2026-11-10：TheMeCat v1 首批接入

已实现专用 CSV 适配和本地原始记录导入；来源、许可、覆盖、重复及治理限制见 [TheMeCat v1 接入审计](themecat_v1_audit.md)。821 条非空行中 820 待处理、1 条完全重复，0 条进入 curated 或核验训练快照。77 项测试通过；ruff 检查和格式检查通过。导入只完成原始接入，尚需可追溯修订/重治理及原文复核，不能据此宣称科研数据已经可训练。

## 2026-11-10：TheMeCat 补充材料归档、审计与实施协调

### 已完成

- 用户提供的数据库说明和 pandas 审计脚本原样归档至 `docs/references/themecat/`，与 Downloads 原件逐字节相同；[哈希清单](../artifacts/reports/themecat-20261110/supplied_files_manifest.json)留证。材料中的内嵌指令作为参考提案，不自动触发训练、候选生成或目录重构。
- 新增 [专项实施方案](themecat_implementation_plan.md)：协调文件计数与论文口径、许可、材料组分 mol%、质量归一流量、初始材料与合成前驱体的区别；完整映射25字段，并明确 B1–B4 → I2–I4 的依赖和验收。
- 新增标准库 `scripts/validate_themecat.py`：原始字符串判重、全空行单列、物理行定位、缺失与无效数值分开；新目录报告拒绝覆盖，不写业务库；关系式显式启用且只作诊断。未安装新依赖。
- 同步 README、implementation_amendment、data_dictionary、api_contracts、themecat_v1_audit、decisions 和 change_inventory 的入口及状态；原始两份开发指引保持相同字节。
- 复查官方说明论文定义并读取 Zenodo API，保存[元数据原件](../artifacts/reports/themecat-20261110/zenodo_record_17085762.json)：数据集许可为 cc-by-4.0。数据集级定义不自动赋予行级人工核验状态。

### 本次实际验证（软件与描述性文件审计）

证据目录：`artifacts/reports/themecat-20261110/`；完整命令、原件/数据库前后哈希及只读状态见 [validation_manifest.json](../artifacts/reports/themecat-20261110/validation_manifest.json)。

| 命令 / 检查 | 实际结果 |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q --junitxml=artifacts/reports/themecat-20261110/pytest.xml` | **83 passed**：原77项 + 新增6项审计边界测试 |
| `.venv/Scripts/python.exe -m ruff check src tests scripts` | All checks passed |
| `.venv/Scripts/python.exe -m ruff format --check src tests scripts` | 37 files already formatted |
| `.venv/Scripts/python.exe scripts/smoke_test.py --output artifacts/reports/themecat-20261110/cli_smoke.json` | **16 steps passed**；隔离临时数据库 |
| 仓库版审计脚本，官方哈希原件，`--check-relations` | MD5 匹配；25列、821非空行、303全空行、52原始DOI链接、1完全重复；报告在 profile-final/ |
| 关系式假设性诊断 | 组成728可比较/9超阈值；收率779/2；STY712/0；不补标签、不认定实验正确 |
| 原件、SQLite、基准文档保护 | 检查前后SHA-256一致；审核事件0、研究快照0；已核验研究记录仍为0 |
| 本地文档链接 | 检查通过；最终文档检查另存 final_doc_checks.json |

新增测试覆盖强制转换前判重、多行CSV物理位置、无效值/NA分离、关系式默认关闭、缺项组成不闭合、输出防覆盖/原件保护、未知schema失败、原值小数位和极端相对偏差JSON安全。

### 明确待实现

**下一项仅 B1：数据语义与治理 v2。** 本次未改 domain、适配器、govern、ingest、审核或快照运行行为。B1须先定接口与迁移/回放方案；B2再提供保持原始指纹的修订专用路径；B3开展真实人工原文核验；B4复用I1资格冻结；合格数据具备后再做I2–I4。

论文822行/44篇与文件821非空行/52 DOI的差异原因未解决。公式诊断吻合不解除 block；未新增 curated研究记录、人工批准、研究快照、模型或候选。

## 2026-11-10：B1 数据语义与治理 v2

新增显式 `themecat-v2` 适配器与版本 2 领域契约，独立表达材料 mol%、初始材料、反应物比值和质量归一流量及其定义来源；旧 v1 路径保留。v2 质量流量模式可保留未报告的完整进料，同时仍阻断未知绝压、无效数值、缺失指标定义等问题。体积 GHSV 门禁继续用于原模式，未做质量流量到 h^-1 的转换。具体字段与历史回放限制见 [API 契约](api_contracts.md)。

`uv run python -m pytest -q`：89 passed；`uv run python -m ruff check src tests scripts` 和 `uv run python -m ruff format --check src tests scripts` 通过。官方原始 CSV 的 v2 只读回放：821 条均被已有原始指纹判为重复，303 空行跳过；821 条均保留未知压力阻断，数据库 SHA-256 回放前后均为 `138f547b4d68acd816053a41e91b34548cb5765c6b7a0c09ba9e1d238daae07f`。此回放不产生新记录、人工审核或快照。后续 B2 须建立有父记录和证据链的新版本，不能更改原文绕过重复检查。

## 2026-11-10：B2 可追溯修订与重治理

新增 `revise` 专用命令及追加式修订关系表；保留父记录、原始指纹、补丁与证据、操作人和治理代码/配置哈希，通过乐观父内容哈希、单子版本约束和相同请求幂等处理冲突。支持从原始 TheMeCat v1 行重建 v2 基线，继续执行所有治理与实体冲突门禁；新的 curated 记录始终 pending，旧审核不继承。快照拒绝同一原始行的多个版本同时计入。使用方法、导出恢复和限制见 [API 契约](api_contracts.md)。

隔离测试：`.venv/Scripts/python.exe -m pytest -q` **92 passed**；`ruff check src tests scripts` 和 `ruff format --check src tests scripts` 均通过。覆盖原件保护、幂等和同父版本冲突、实体冲突、审核隔离、重复快照阻断和 v1 到 v2 原始行回放。未对工作区真实记录执行修订或人工审核；实际原文核验仍属于 B3。

## 2026-11-10：B4/I1 来源接受与首次真实资格检查

按用户决定暂缓 B3，新增显式 `--accept-themecat` 策略：仅接受固定哈希的公开 TheMeCat 数据集作为来源证据，不记录虚构的逐行审核。该策略仍要求整记录无治理 block、目标定义及单位匹配、原件和内容完整、未遭审核拒绝。冻结快照明确标记来源接受及未逐行核验；旧人工审核路径仍可用。修正 I1 对 v2 领域契约的解析。

对全部 821 条 TheMeCat v1 导入事件，以论文定义的 CO₂ 转化率（%）生成[资格清单](../artifacts/reports/themecat-b4-20261110/qualification.json)：0 合格、821 排除、空集合不冻结。其中有 1 条重复导入事件；全体记录尚未 curated、目标定义尚未写入记录，旧 v1 治理均有压力类型未知及旧流量/组成语义阻断。公开发表的可信度不能提供未记载的压力类型。未更改工作区原始数据、逐行审核或创建研究快照。后续需使用 B2 对原始行进行有证据的 v2 修订，尤其解决压力基准，才能获得通过现有治理的目标记录。

验证：全量 pytest 93 passed；ruff check 通过。来源接受成功/拒绝路径仅使用隔离测试数据验证，不将模拟审核当作真实核验。

## 2026-11-10：绝压默认假设与 TheMeCat 批量重治理

按用户指令，将 TheMeCat 原始数据未注明的压力类型按绝压处理；此为明确的用户假设，并非原始文献已证实，逐条写入修订补丁、来源说明和治理报告。根据[数据集论文](https://doi.org/10.1038/s41597-025-06482-8)记录四项性能指标的数据集级定义，不推算或填补缺失性能值。数值缺失时不再错误地以缺少数值单位作为额外 block，仍保留缺失 warning，目标资格仍会排除缺失目标值。

通过 B2 路径完成 820 条非重复原始记录的 v2 修订，无批处理失败：609 条 curated、211 条 staged；旧原始记录与 1 个重复导入事件保持不变。未通过项包括组成未确认、组分含量不完整或闭合偏差、质量归一流量缺失；问题可重叠，不能强制补值。完整计数见[治理摘要](../artifacts/reports/themecat-governance-20261110/summary.json)。

基于此前用户接受来源策略，CO₂ 转化率目标资格检查 820 条修订，593 条合格、227 条排除（211 条未 curated，16 条缺失目标值），生成[资格清单](../artifacts/reports/themecat-governance-20261110/qualification.json)和 593 条记录的研究[快照](../data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json)。快照标记 `published_dataset_accepted_not_row_verified`，不代表逐行原文核验；原件中的绝压并未得到独立证实。未训练模型，未做分组划分。批处理脚本为 `scripts/govern_themecat_20261110.py`，备份为 `artifacts/reports/themecat-governance-20261110/catalog-before.sqlite`。

校验：pytest 94 passed；ruff 检查和格式检查通过；SQLite integrity_check 为 ok、外键错误 0、修订 820、人工审核事件 0；原始 CSV SHA-256 保持不变。

## 2026-11-10：I2 论文 DOI 分组

实现 `dataset split --snapshot ... --qualification ... --seed 42 --report ...`：校验输入快照和资格清单哈希及关联，规范 DOI，以整篇论文为组并按组确定性分配训练/验证/测试；缺失 DOI、来源冲突、同引用异 DOI、已知重复跨 DOI、组数不足均拒绝划分，不回退按记录随机划分。分组不根据名称或组成认定同一样品。加入集合交叉检查和数据覆盖；记录级合成/配方 ID 不用于宣称样品留出。

对 593 条真实快照记录，Crossref 返回 37/37 DOI 元数据；分为训练 26 论文/493 条、验证 6 论文/47 条、测试 5 论文/53 条。记录、论文 DOI、来源 ID 跨集合交集均为零；存在少量跨集合相同材料家族标签，未知是否有跨论文重复样品。实际论文样品关联未确认。清单、外部元数据及不确定性见 [I2 报告](../artifacts/reports/themecat-i2-20261110/README.md)。

验证：pytest 97 passed，ruff check 与格式检查通过；实际分组重建和 JSON 内容哈希验证一致。未训练模型或进行样品留出评估。


## 2026-11-10：I3 设计输入特征

实现受限设计输入、组成签名和训练集词表；不从观测、表征、名称、来源文本或未确认的历史合成生成特征。组成按基准、范围、物种、角色、数量编码，不进行归一化或换算为元素原子分数；缺失不填补，未见物种单独计数。计划合成仅通过显式受限输入提供，快照导出不推断历史工艺为计划。

已有 I2 快照和划分生成 [特征表](../artifacts/reports/themecat-i3-20261110/features.json)：593 行（训练 493、验证 47、测试 53），训练词表 32 项；验证集 18 行、测试集 21 行含训练未见组分。重建结果及哈希一致。`uv run python -m pytest -q` 99 项通过；ruff 检查与格式检查通过。

该表没有进行模型训练；训练折交叉验证必须重新拟合词表和缺失处理，当前接口仅构建最终训练集词表。已接受数据集来源不代表逐行人工核验，绝压仍为用户假设；论文切分不证明样品/批次独立。参见 [I3 接口](api_contracts.md)。

## 2026-11-10：I4 单目标基线

使用唯一现有冻结目标 CO₂ 转化率（593 条）及 I2 论文切分；固定比较 Dummy、Ridge 和 Extra Trees。仅用训练集拟合组成词表、缺失填补和缩放；以验证集 MAE 选型，确定结果后才计算测试指标，未用测试集调参或选目标。训练全部为固定参数，未进行交叉验证调参；历史合成缺失，四项计划合成特征在训练集中全缺失而排除。

结果及完整配置、版本、覆盖、逐记录测试预测与模型哈希见 [运行报告](../artifacts/reports/themecat-i4-20261110/report.json)，模型见 [models.joblib](../artifacts/reports/themecat-i4-20261110/models.joblib)。训练/验证/测试分别为 493/47/53 行、26/6/5 论文组。验证集选中 Extra Trees（MAE 3.903 个百分点）；测试 MAE 2.872、RMSE 4.368 个百分点，R² 0.270。测试集中 Dummy 的 MAE 为 4.481，Ridge 为 4.151。此比较不证明对新样品或新批次的泛化。

验证：`uv run python -m pytest -q` 102 项通过，ruff 检查和格式检查通过。包括测试目标改变不影响选型、验证独有物种不进入训练词表、验证分布偏移不影响训练填补以及篡改特征被拒绝；同一输入再次运行报告一致，重新加载模型的测试预测最大差异为 0。来源接受不是逐行原文核验，压力按用户假设为绝压，未知跨论文样品关系、适用域和不确定性仍未解决；不据此进行候选推荐。

## 2026-11-10：I5 诊断与条件化筛选

已实现 I4 报告、模型、依赖及冻结输入校验；计算验证集置换重要性、Tree SHAP 和加和验证，训练集排除同论文的最近邻距离阈值，以及验证/测试按论文的误差与树预测分散度覆盖。数据证据、模型卡与详细限制见 [I5 报告](../artifacts/reports/themecat-i5-20261110/diagnostics.json)和[模型卡](../artifacts/reports/themecat-i5-20261110/model_card.md)。测试集 7/53 行超过距离启发式阈值，21/53 行含训练未见物种，1/53 行工况超训练范围；可能重叠。预测 ±2 倍树间标准差的经验覆盖测试集为 39/53，非校准区间且无名义覆盖率。训练后此前已查看过同一测试集，不作为新的前瞻确认。

实现显式候选筛选接口，固定共同工况并检查组成闭合、训练词表、给定条件边界、启发式距离与操作者提供的约束证据；最多六槽，输出 proposed/caution、来源定位和未经校准的树分散度。输入合同与[模拟配置](../data/examples/screening_spec.synthetic_demo.json)见 [API 契约](api_contracts.md)；模拟数据和证据均为虚构。当前未获得真实候选、路线、设备边界、兼容性、前驱体及成本/风险依据，因此未进行真实筛选、未创建真实候选或实验批次。模型不能评价训练中全缺失的合成参数。

验证：`uv run --extra modeling --extra explain --extra dev python -m pytest -q` 105 项通过；ruff 检查及格式检查通过。测试覆盖诊断哈希篡改、SHAP 加和、论文组计数、缺失约束、容量上限、模拟候选与未见物种过滤。诊断相同输入重建内容和哈希一致。上述筛选证据由操作者提供，软件不核验其真实性，且现有模型不提供已验证适用域或覆盖保证。

## 2026-11-10：固定工况探索性组成

根据用户要求，以 I4 已训练模型对训练集中现有材料组成及相同物种间转移 5 个摩尔百分点的变体做固定工况比较，输出四个不同物种/角色集合供研究讨论，完整候选及规则见[探索报告](../artifacts/reports/themecat-exploration-20261110/README.md)。完整工况的训练最高频组合有并列，按数值排序取一组；该组 19 条均来自同一篇论文。未把任一预测当作实测，也未声称配方或工况通过实验约束审查。

生成脚本为 `scripts/explore_compositions.py`；关联冻结输入、I4 模型和 I5 诊断哈希，完整生成、过滤、排序和原始记录定位见 [JSON](../artifacts/reports/themecat-exploration-20261110/candidates.json)。这不是 `dataset screen` 的正式候选计划，不伪造设备、前驱体、兼容性、成本/风险或合成路线证据。训练集仅包含 CO₂ 转化率目标，尚不能据此优化甲醇产率。

## 2026-11-12：R1 特征输入核心

新增 `features/pipeline.py`，保持历史 F0 不变；F_cond 和 F_base 使用相同的完整组成与四项工况筛选，F_base 按传入训练记录拟合正含量角色/物种词表，合并重复项，报告未见键和训练范围越界。`diagnostic=True` 保留未见键记录的诊断数组，默认转换拒绝该记录；它不等同于模型预测。筛选清单继承原 DOI 划分，并校验快照、资格及划分身份。

使用 `scripts/build_r1_features.py` 从现有冻结输入生成 [筛选清单](../artifacts/reports/themecat-r1-features-20261112/selection.json) 与 [特征表](../artifacts/reports/themecat-r1-features-20261112/features.json)。训练/验证/测试分别保留 493/47/53 条、26/6/5 篇论文；均无输入排除。训练词表 32 项，验证/测试分别 18/21 条含未见键。该表的词表仅用于最终训练集拟合及诊断，交叉验证必须按折重新拟合。

此交付为 3.1 特征构建与支持边界，不代表 3.2 的分组交叉验证、选模或 3.3 的模型包和独立预测入口已经完成；尚不能用该表声称完成预测或性能评估。来源接受不代表逐条核验，压力绝压沿用原假设。

## 2026-11-12：3.2 DOI 分组比较核心（部分实施）

新增 `modeling/experiments.py` 的 `compare_r1(snapshot, qualification, split)`：从校验后的原始输入重建筛选，固定按记录 ID 排序，在原 train 内按 DOI 执行三折 GroupKFold；每折单独拟合 F_cond/F_base、训练词表和 Ridge 缩放器，比较固定参数 Dummy、Ridge 与 ExtraTrees。以全部 OOF 记录的论文等权 MAE 在 F_base 模型中选型，同分按 dummy、extra_trees、ridge 决定；选定模型仅在原 train 重拟合并评估原 validation。报告包含逐行 OOF/validation 原始预测、未知键及越界状态、各折分配和分数；组数不足或预测非有限时停止，不缩减分母。Test 不读取用于评价或选型。

此项目前仅为 Python 内存接口和合成数据验证；不提供已验收的模型包、CLI、配置入口、可用率汇总、共同支持子集或正式 R1 结果。按计划 S1 所需物化数据与计算尚未完成，因此未启动 R1/R2 正式比较；已实现的核心不能视为 3.2 全部完成，也不构成独立预测或科研验证。

## 2026-11-12：3.2 可用率与证据校验

`compare_r1` 增加各特征集/模型的 OOF 可用率、拒绝原因、论文覆盖与可用子集指标；同时报告同一模型的 F_cond/F_base 共同可用子集，以及所有候选共同可用子集。无可用记录时指标为 null 并说明原因；这些子集均不替代全部 OOF 论文等权 MAE 选模。选中模型的 validation 报告同样包含可用率与可用子集指标。

研究数据调用时须通过 `raw_files={原件sha256: 文件路径}` 提供原件；训练前核对原件哈希、资格记录与快照的 payload、输入哈希、定位和目标定义。缺失或不一致直接报错。对现有 593 条冻结记录及对应原件完成只读一致性检查；没有运行正式模型比较。合成输入仍可用于软件测试。该检查不替代逐行来源核验，也不验证目录中数据库是否发生后续变更。

尚缺独立模型包/预测入口、正式比较运行与历史 test 对照，以及完整的配置和持久化流程；以上功能仍不能视为全部 3.2/3.3 交付。

## 2026-11-12：3.2 R1 默认比较与历史对照

完成默认三折 DOI 组内 OOF 比较及原 train 重训；脚本 `scripts/compare_r1.py` 在校验快照、资格、划分及原件后写入新目录，不覆盖旧结果。验证集与已查看历史 test 均在 OOF 选型后评估；分别列出 F_cond 和 F_base、入口可用率及共同可用子集。比较配置、全部 OOF 预测、逐记录折归属及留出结果见 [报告](../artifacts/reports/themecat-r1-comparison-20261112/report.json)，[筛选](../artifacts/reports/themecat-r1-comparison-20261112/selection.json)保留原分区。原 train/validation/test 为 493/47/53 条，筛选后均保留。

F_base 的 OOF 论文等权 MAE：Dummy 5.906、ExtraTrees 5.546、Ridge 7.301 个百分点，按预定规则选择 ExtraTrees；其 OOF 入口可用 274/493 条。选定模型的 validation 全体诊断 MAE 为 4.128，入口可用 29/47；已查看的历史 test 全体诊断 MAE 为 3.429，入口可用 32/53。全体指标包括未见物种诊断输出，不能将其当作全部记录的可用预测。复算报告内容哈希一致。

该结果是 R1 默认特征和参数的开发比较，不代表前瞻确认或经验证的实际适用域；来源接受不等于逐条核验，绝压为用户假设。S1 物化属性准备、R2 比较、3.3 独立预测包以及 3.4 配置训练入口仍另行完成，不因本次完成 3.2 默认比较而视为已交付。


## 2026-11-12：3.2 默认比较验收完成

在已有比较核心上补齐持久化接口 `write_r1_comparison`，脚本统一生成报告、筛选、有效默认配置、逐记录折归属和中文摘要。报告增加原分区与筛选后记录/DOI/组成签名覆盖；固定记录排序和 GroupKFold(shuffle=False) 明确写入配置。3.2 默认比较至此完成；3.3 独立预测包与 3.4 自定义配置仍待交付，不宣称整个 S2/S3 完成。

复跑真实 593 条记录，在[全新验收目录](../artifacts/reports/themecat-r1-comparison-20261112-verified/README.md)保留证据，不覆盖历史报告或修改原件/快照。训练/验证/历史测试保留 493/47/53 条、26/6/5 篇 DOI、100/31/12 个组成签名，均无输入排除。F_base 的 OOF 论文等权 MAE：Dummy 5.905647、ExtraTrees 5.546356、Ridge 7.300750 个百分点；选择 ExtraTrees。该模型 OOF 入口可用 274/493；validation 全体诊断 MAE 4.128214、可用 29/47；已查看历史 test 全体诊断 MAE 3.429310、可用 32/53。全体误差保留未见物种诊断，不能当作全体入口可用性能。

相同输入独立复算完整报告内容哈希一致：`0949ae11751408194818c01dfd130f7b32189ad3bbb94500f4e7fe6ff1e0ab44`。默认配置、折归属、逐行 OOF 与留出输出、可用率和共同支持子集均可复查；来源接受、绝压假设及历史 test 身份保持明确。

验证：全量 pytest **119 passed**，ruff check 与 format --check（src/tests/scripts）通过。新增验收覆盖同 DOI 多记录不跨折、Ridge 缩放只拟合折内训练、精确同分选择 Dummy、相同输入复现、非有限预测阻断、脚本端到端落盘、哈希校验和拒绝覆盖旧目录。Python 和脚本调用见 [API 契约](api_contracts.md#r1-默认比较32)。

## 2026-11-12：3.3 R1 独立预测接口

新增 R1 F_base 模型包保存/加载和单条、批量 JSON 预测，绑定训练记录、报告、特征实现、依赖与模型哈希；复用训练特征变换，明确拒绝非法输入和未见正含量物种，保留越界原始预测并拒绝非有限结果。输入格式与调用方法见 [接口契约](api_contracts.md)。合成数据重训、包重载一致性及失败路径已测试；全量 pytest 120 项通过，src/tests/scripts 的 Ruff 检查及格式检查通过。仓库根目录检查仍受既有 docs/references 文件格式问题影响。本次尚未在真实冻结数据上重新生成模型包或完成真实数据的命令行端到端验收；R2 和 3.4 仍待实施。

## 2026-11-12：3.3 真实数据预测验收

使用冻结快照、资格、原 DOI 划分及原件进行完整校验并重跑 R1 比较，选出 F_base / ExtraTrees，生成 [绑定模型包](../artifacts/models/themecat-r1-prediction-20261112-final/manifest.json) 和 [报告](../artifacts/reports/themecat-r1-prediction-20261112-final/report.json)。包清单包含输入字段、单位、版本及哈希；模型和词表绑定保存在包中。以 CLI 对原 validation 全部 47 条逐条预测：27 条 ok、2 条 caution、18 条因未见物种角色拒绝；29 条可用值与同次训练报告一致，见 [验收结果](../artifacts/reports/themecat-r1-prediction-20261112-final/prediction-verification.json)。全量 pytest 120 项通过，src/tests/scripts 的 Ruff 检查及格式检查通过。3.3 的 R1 独立预测已完成真实数据验收；自定义模型与特征选择按 3.4 后续交付，R2 仍待实施。此验收不构成前瞻性能确认。

## 2026-11-12：当前状态统一与核查

- 修订README、本文件顶部汇总、特征方案、实施验收清单、TheMeCat专项方案和API契约共6份文档：统一为3.1–3.3已完成；S1物化属性/映射入库与计算、R2及3.4配置仍待完成。删除当前汇总中“新能力均未实现”“独立预测包待完成”等过时表述，保留历史交付记录的时间语境。
- 当前优先级仍为C、D辅助评价；下一代码任务为S1-A数据准备与版本化入库，再补齐S1-B并复用R1完善S2/S3剩余能力。总体C、S1–S3及实验闭环均不标为全部完成。
- 本轮实际核查：`.venv/Scripts/python.exe -m pytest -q`为**120 passed in 12.04s**；同一环境的`ruff check src tests scripts`和`ruff format --check src tests scripts`通过（63 files already formatted）。通过`load_package`加载现有R1包、`predict_batch`重放47条validation输入，JSON序列化后的全部结果与既有`validation-predictions.json`一致，状态为27条ok、2条caution、18条unsupported_species_role。
- 文档核查：6份文档的128个本地链接及10个章节锚点均有效；`git diff --check`通过。两份原开发指引与Git HEAD逐字节一致，SHA-256仍为`64ba32d98cdfd4778cef1158f597e2179376c380ee3a816314dd9c31664a757e`。
- 本轮仅统一文档及执行核查，未更改业务代码、数据或模型，未重新训练、导入、审核、冻结或推进E/F；工作区已有未提交/未跟踪文件保留，未进行Git提交或发布。

## 2026-11-12：总体设计与文档入口整合（仅文档）

- 用户指出总体执行方案分散，需要整体设计。新增`docs/architecture/system_design.md`，集中说明目标与当前交付边界、模块职责、事实/属性/派生值存储、版本链、训练与预测工作流，以及后期设计/实验反馈的衔接。
- 明确A–F为总体路线，I1–I5和TheMeCat步骤为既有验收/来源切片，S1–S3为当前建设顺序，R1/R2为实验预设；不形成平行项目。下一步仍为S1-A，已有3.1–3.3成果及未完成边界不变。
- README收敛为整体介绍与阅读导航；进度负责当前事实，特征方案负责字段/公式/细化验收，专项方案负责来源接入，API契约负责实际调用；ADR-018记录文档分工。并修正特征方案模块表“以下文件均为规划”的过时说明，明确其中三个模块已有R1实现。
- 核查8份文档的165个本地链接、14个章节锚点及代码围栏闭合，错误0；`git diff --check`通过。两份原开发指引与Git HEAD逐字节相同。仅改文档，未重复运行pytest/ruff，不将上一轮120项测试记作本轮新验收；未更改代码、数据、模型或执行Git提交。

### 2026-11-13 S1-B 构建进展

已生成 [S1-B 特征快照与筛选结果](s1_b_build.md)：553 条保留、40 条排除，沿用原 DOI 分区和 S1-A 来源资格；新增中心加权计算、不可变构建及逐值存储。F1/F2 模型训练和预测绑定仍属于 S2，以上结果不表示模型性能验证。

## 2026-11-18：S2-02 集成进展

新增配置训练及指定候选打包 CLI、预测输入示例和接口说明。真实自定义配置在独立目录 `artifacts/runs/s2-02-smoke-20261118` 训练，F2/ridge 包在 `artifacts/models/s2-02-smoke-20261118` 重载，单条状态 ok，混合批次为 ok/invalid_input。全量 pytest 203 passed、1 条依赖弃用提示；Ruff 检查和格式检查通过。这是工程烟测，不是 S3 正式配对比较。S2-02 完整验收及登记尚需补齐，包括基准 CLI 重放、R1 旧包重放和交付证据固定。

## 2026-11-18：D-06 启动核查

D-04 冻结清单合格独立记录及组均为 0，D-06 独立评价未启动，覆盖率、误差及域分层均证据不足。D-04 协议和来源台账文本含大量问号，需恢复可读协议并冻结合格数据后再评价；D-05 区间尚未校准。详见 [D-06 核查记录](../artifacts/reports/d-06-20261118-01/summary.md)。

## 2026-11-19：D-06 本轮流程建设完成

D-04 v2 已重建协议和来源台账。D-06 点预测流程已实现，提供冻结材料就绪检查、显式评价入口、逐条结果和分层指标。使用合成数据和空清单完成软件检查，全量测试 243 项通过，有 1 条依赖弃用提示。按用户确认的本轮范围，流程建设已完成。正式独立评价待合格数据，尚未执行。入口和材料格式见 [D-06 评价流程](d06_evaluation_workflow.md)。

## 2026-11-19?D-07 ??????

?? [D-07 ???????????](d07_model_card.md)??????????? SHA-256 ?????????????????D-06 ???????????????????D-05 ????????????????????????????
