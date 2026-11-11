# CLI 与后续接口契约

## B1 数据语义与治理 v2

显式选择 `--adapter themecat-v2` 使用 schema_version `2`；`themecat-v1` 和版本 1 治理保持原有语义。v2 在 `test.mass_normalized_volume_flow` 保存质量归一体积流量及参考温压、催化剂质量分母、气体范围和定义来源；独立 `test.reactant_ratio` 保存 H2/CO2 比值与定义来源。`test.flow_mode=mass_normalized_reactants` 时这两个字段及其完整基准必需，允许完整进料未报告，不要求体积 GHSV；其余温度、绝压、来源、组成、指标定义和审核门禁仍生效。体积 GHSV 原字段与旧门禁继续适用于默认模式，禁止质量流量推算 h^-1。v2 初始材料放在 `synthesis.initial_materials`，不填实际前驱体；材料组成基准为全催化剂材料 mol%，不代表元素原子分数或逐行实测核验。数据集级证据在 provenance 中注明，不替代原论文行级证据。

历史 SQLite、原始载荷、治理结果、审核和快照不原地迁移；v2 是对原文件的版本化解释。现有 ingest 依据原始指纹拦截重导，因此已接入记录只能 dry-run 对照，正式产生新版本须等待 B2 修订接口记录父记录、补丁、证据和版本，重新治理并重新人工审核。不得改变原始字段绕过判重。无通用迁移器，不提供假迁移命令；严格快照规则不变。

当前只提供离线 CLI 与 Python API，无HTTP服务。`catalyst-ai --config <yaml> <command>`；配置相对路径按当前目录解析。stdout 为 JSON，stderr 为可读摘要或错误；dry-run不写任何项目文件（报告输出 stdout）。`--dry-run --report` 组合拒绝，避免“只校验”意外落盘。

| 命令 | 已实现行为 |
|---|---|
| init | 幂等建表、目录；不填业务数据 |
| status | 数量、默认容量、核验研究数量，明确模型/优化未实现 |
| ingest --input --source? --dry-run? --report? | 本地CSV/JSON→Pydantic→质量治理→staged/curated；部分坏行不丢弃合格行 |
| validate --run-id? --report? | SQLite完整性/外键、该次导入raw哈希检查；重导出**当次历史治理报告**，不是按新规则全库重治理 |
| review --record-id --reviewer --decision --evidence | 整条curated记录人工核验事件；warning批准必须显式确认 |
| dataset build --target --record-id? --output? | 人工核验研究记录冻结JSON；不带record-id时选择全部research curated记录，任何未核验记录均导致失败，不静默跳过 |
| dataset build --demo ... | 仅synthetic_demo软件测试快照；仍要求审核；写demo子目录，禁止科研训练 |
| dataset qualify --target --target-definition --target-unit --record-id ... | 只读检查显式所选记录，输出目标资格、排除原因和覆盖计数，不默认扫描整库 |
| dataset qualify ... --report? --freeze? --demo? | 可保存JSON；显式freeze重查全部输入并冻结合格记录、保存关联；demo仍隔离且禁止科研训练 |
| batch check --capacity? --candidate-id ... | 容量与槽位ID校验；未持久化、未推荐候选 |

`train/evaluate/screen/batch plan/import-results` 仍为规划，CLI 不提供假实现。

## Python 调用边界

```python
from pathlib import Path
from catalyst_ai.config import Settings
from catalyst_ai.ingest import ingest

settings = Settings(database=Path("data/catalog.sqlite"))
report = ingest(Path("data/examples/synthetic_demo.json"), settings, dry_run=True)
assert report["dataset_kinds"] == ["synthetic_demo"]
```

`review_record(settings, record_id, reviewer=..., decision=..., evidence=..., acknowledge_warnings=...)` 只记录操作者已完成的核验。不会读取PDF并代替复核，不会因为ingest或validate成功自动运行。

`build_verified_snapshot(settings, target=..., record_ids=..., output=..., demo=False)`：

1. 检查curated身份和数据类别；研究/模拟不得混用。
2. 检查review_status=verified、有独立verified审核事件，且审核内容哈希与当前治理内容一致。
3. 检查原始文件存在且SHA256一致；导入时的原始抽取状态保持不变，审核事件提供有效核验层。
4. 检查目标确实存在、有有效标准值/定义，所选记录目标定义与单位一致；不做语义相似匹配或条件标准化。
5. 冻结完整记录、各层实体ID、定位、哈希、治理与审核元数据；相同内容幂等，内容不同生成新ID，已有文件不同内容拒绝覆盖。

快照完整保留测试条件与表征作为证据，不是模型特征表。`split_policy_required=[source_id,recipe_id,synthesis_id]` 仅说明后续分组需求；`split_status=not_performed`，不声称已实现防泄漏切分。`model_run_id=null`，没有正式模型或科研结果。

## I1：目标资格视图（规则版本1，已实现）

Python入口位于`catalyst_ai.datasets.eligibility`：

- `build_target_eligibility(settings, *, record_ids, target, target_definition, target_unit, demo=False, rule_version="1")`：必须显式提供非空ID集合，去重排序后检查；目标定义/单位精确匹配，不执行语义推测。只读数据库及原件，不自动核验、不写快照。
- `freeze_qualified_snapshot(settings, qualification, *, output=None)`：核验清单内容哈希，重新检查包括排除项在内的全部原始选择；内容/审核/原件/软件配置变化使清单过期。通过后仅把非空合格record_ids交给原快照入口；不改变dataset build的原有行为。

清单包含qualification_id、content_sha256、完整输入ID、payload/raw_payload/原件哈希、审核证据、目标定义/单位、规则版本、记录/观测级原因、各层实体ID与覆盖计数。qualification_id由content哈希决定，不含生成时间；同一软件配置、记录与审核状态下重复检查得到同一清单。snapshot关联位于外层，不改变资格内容身份。

观测粒度为observation_id，保留原值、标准值与缺失状态，不填标签。多个同目标观测只有在有效且不同的time_on_stream可区分时才准入；优先用观测时间，未报告时用test时间，h/min仅用于明确的秒数换算。无法区分的重复样/时间点整条排除，尚不支持独立重复样标签。任一同目标观测不合格时整个record排除，以兼容现有完整记录快照；不切除坏观测后偷偷冻结。

常见排除原因：`not_curated`、`not_reviewed`、`missing_target`、`missing_target_value`、`target_not_normalized`、`target_definition_mismatch`、`target_unit_mismatch`、`ambiguous_observation_context`。原值/治理内容变化、原件缺失/哈希不符、审核拒绝/撤销、审核状态不一致、数据类别混入、未知ID等列为integrity_errors，阻断整次冻结，不能用排除坏记录来掩盖。

status为ready/empty/blocked；ready仅表示至少一条通过当前资格规则，仍需冻结门禁。`scientific_use`沿用数据类别标记，模拟恒为false，不能单独据此认定样本合格或模型可信；本阶段split_status始终为not_performed。

CLI退出码：全部准入为0；存在普通排除或空集为2；完整性阻断、显式freeze空集为1，均输出完整资格JSON。参数或IO错误沿用既有错误处理，可能只有stderr。`--freeze`允许在普通排除后冻结剩余合格记录，仍返回2以提醒检查报告；不会把空列表传给旧快照函数。`--report`只接受新.json路径；冻结成功时返回qualification_path，并在快照目录下的qualifications保存完整清单与snapshot_id/path关联，已有内容相同幂等，不同则拒绝覆盖。

限制：单机可信操作者；资格复查与快照函数之间无跨调用并发事务。快照先于关联清单落盘，关联/额外报告写入失败可能留下已生成快照，修复路径后可幂等重试。新接口不提供训练行特征、分组切分或模型。

## 未来接口（规划内容）

`interfaces.py` 中仅声明 DesignFeatureBuilder、PerformancePredictor、CandidateRecommender Protocol；没有可运行模型。后续开发必须实现：A/B/C严格分层、真实核验快照→描述符→分组切分→基线评价；模型/优化需持久化配置、随机种子、适用域、不确定性与证据。推荐接口输出proposed，绝不能宣称实验已验证。

真实实验反馈导入、计划/实际值分离、批次状态机、模型回流尚未实现；现有通用导入器可保存内部来源数据，但不等于完成实验闭环。

## 当前恢复和权限限制

SQLite为事实源；staged/curated JSON是当次导出，不跟随后续审核变动。报告中的review_status=pending也属于导入时历史状态，不能当作当前审核结果。整库当前状态以数据库为准。文件导出发生在数据库提交之后，尚无跨文件系统事务；导出失败需保留错误并根据run_id重导报告。当前只支持单机可信操作者，没有服务端鉴权、OS只读保护、并发审核仲裁或数据库迁移。

## TheMeCat 独立审计脚本（2026-11-10）

`python scripts/validate_themecat.py --input <CSV> --output <新目录> [--check-relations]` 是独立文件审计接口，不属于 `catalyst-ai validate`，不读取/更改业务数据库。严格匹配 v1 的25列表头和顺序，原始字符串判重，输出物理行范围；统计分母是包括重复在内的非空记录，全空行单列。缺失仅识别空白/NA，其他不可解析或非有限数字单独标记。

输出 `quality_summary.json`（输入/脚本哈希、计数、检查状态）、`column_quality.csv`（原始缺失与有效/无效数值分开）、`row_diagnostics.csv`（位置、原值、代码和关系式诊断细节）。默认不作关系式检查；显式启用后其状态为 diagnostic_only，`scientific_use=false`、`approves_records=false`，不补标签、不赋核验状态。公式比较的条件、阈值及边界见[实施方案](themecat_implementation_plan.md)。

退出0：审计完成且MD5匹配；退出2：审计完成但MD5不匹配；退出1：解析/IO/已有输出目录等失败。存在异常提示也可能退出0，调用方须检查报告，不能将其作为研究准入成功码。报告目录与原件目录分离，已有目录拒绝覆盖；多文件导出无跨文件原子性，失败后可能留有不完整新目录，应保留排查并换新目录重试。

B1 的 v2 契约与适配器见本文开头；修订命令和历史数据迁移仍为 B2 规划，不提供占位命令。审核与快照门禁不变。

## B2 修订与重治理

`revise` 为已有 staged/curated 记录追加一个不可覆盖的版本，父记录、原始行和旧审核均保留。先从导入或修订报告的 `rows[].governed_sha256` 取得父内容哈希，准备 UTF-8 JSON 对象作为补丁：每个键完整替换对应的顶层领域字段，数组和对象不做递归合并。例如只替换 `test` 时必须提供完整的 `test` 对象。然后运行：

```powershell
catalyst-ai revise --parent-record-id <记录ID> --expected-parent-sha256 <父内容哈希> --patch patch.json --reason "修订理由" --operator "操作人" --evidence "原文及具体位置" --report revision-report.json
```

对于原始 `themecat-v1` 导入，可增加 `--base-adapter themecat-v2`，先从已保存原件按物理行重建 v2 语义，再应用补丁；仅做语义升级时补丁文件可为 `{}`。该基线只适用于原始 v1 导入，后续修订以直接父版本为基础，避免丢失先前更正。补丁仍需证据；数据集定义不自动代表原文核验。

修订前检查父内容哈希、原始行指纹及原件文件哈希；同父记录只允许一个子版本，相同请求幂等返回原报告，不同请求须改基于最新子版本。修订记录保留父 ID、补丁、理由、操作人、证据、原始指纹、内容哈希与代码/配置/治理版本哈希。原始行指纹继续用于普通导入判重；同 ID 实体内容冲突和已存在的观测 ID 均阻断，必要时显式提供新的实体及关联 ID。通过治理的新版本为 pending，必须重新人工审核；快照拒绝同时纳入同一原始行的多个版本。

报告和修订链随事务存入 SQLite，可用 `validate --run-id <修订运行ID>` 重导出报告；`--report` 是可选文件输出，拒绝覆盖。SQLite 提交与可选报告文件写入不构成跨介质原子事务，文件写入失败时可用相同请求重试或通过 validate 恢复。该接口不自动执行实际数据修订、原文审核或冻结。

### TheMeCat 公开数据集来源接受策略

用户于 2026-11-10 决定暂缓 B3 原文逐条核验，接受已公开发表的 TheMeCat v1 数据集作为来源证据。`dataset qualify --accept-themecat` 显式选择该策略，仅对原件 SHA-256 为 `46000f00323ac64a79f63777e54c05634e83d1a6476176c8b6569122bd03dfbd` 的 research 记录有效。该策略可让通过全部治理但仍为 pending 的记录进入目标资格；不创建 review_event、不更改审核状态，也不代表逐行原文核验。已拒绝的记录、治理 block、原件/内容完整性和目标定义/单位检查仍生效。冻结产物明确标记 `published_dataset_accepted_not_row_verified` 并包含来源接受依据；默认严格人工审核路径不变。模拟数据不能使用此策略。

首次真实资格检查以 CO₂ 转化率为目标，定义为 `100 * (CO2 inlet molar flow - CO2 outlet molar flow) / CO2 inlet molar flow`，单位 `%`，依据[数据集说明论文的性能指标定义](https://www.nature.com/articles/s41597-025-06482-8)。选择所有 821 条 TheMeCat v1 导入事件（包括 1 条重复事件）进行检查，原始记录没有自动补写该定义。结果详见 [资格清单](../artifacts/reports/themecat-b4-20261110/qualification.json)：821 条排除、0 条合格，空集合停止冻结；旧 v1 治理中 821 条有压力类型未知阻断，且旧流量与组成语义需经 B2 v2 修订。逐条问题见清单中的 `governance_blocks`；其中包含重复事件，计数不是独立样本数。

## I2 论文分组命令

`catalyst-ai dataset split --snapshot <快照.json> --qualification <资格清单.json> --seed 42 --report <新清单.json>`：检查输入内容哈希及两者关联；按规范 DOI 整组划分，默认 seed=42，按组数近似 70/15/15。缺失 DOI、来源歧义、已知重复跨 DOI、少于 3 组、集合交叉时失败。输出记录归属、分组、样本和论文数、材料家族/温压覆盖、交叉检查和内容哈希，不进行模型训练。分组依据 DOI，不把同名或同组成自动视为同一个样品；未知跨论文样品关系继续保留为限制。


## I3：设计输入特征（design-features-v1）

`catalyst-ai dataset features --snapshot SNAPSHOT.json --qualification QUALIFICATION.json --split SPLIT.json --report NEW.json` 校验并重建 I2 划分，输出带内容哈希的特征表，拒绝覆盖。Python 入口为 `catalyst_ai.features.design.build_feature_table` 和 `design_input`。记录 ID 和集合仅用于关联；`composition_values` 和 `values` 是设计输入，签名及状态是追踪/缺失元数据，不将签名或 ID 当作特征。

组成词表只从训练集合拟合，键包含基准、范围、角色与物种；保留 mol%、wt%、atomic% 差别，不做原子化换算或归一化。签名仅消除排列差异，不代表配方或批次身份。未知基准/范围、缺失数量和孤立数量使组成不可用。未列物种为 null，不推断为零；未见物种数标记训练词表之外的组成。数值缺失不填补；交叉验证必须在各训练折重新拟合词表和缺失处理。

工况准入温度、绝压、催化剂质量、指定参考条件的反应物质量归一化流量及 H₂/CO₂ 比；单位或基准不符则标记不可用。不准入目标、表征、名称、来源文本或历史合成。独立 `design_input(..., planned_synthesis=...)` 仅接受白名单计划煅烧/还原温度和时间的 Measurement；调用者须确认事先可获得，快照导出不自动将历史合成当计划。

## I4：论文留出单目标基线

先安装建模依赖 `uv sync --extra modeling --extra dev`。运行 `catalyst-ai dataset baseline --snapshot SNAPSHOT.json --qualification QUALIFICATION.json --split SPLIT.json --features FEATURES.json --output NEW_DIRECTORY --seed 42`；输入须可通过 I1–I3 哈希、关联和划分重建检查。每记录必须恰有一条目标观测且口径一致；空集合、篡改或不一致明确失败。输出目录必须不存在；执行中途 IO 失败可能留下部分目录，检查后改用新目录重试。

固定使用训练集词表、训练中位数填补及缺失指示、训练均值/标准差缩放，比较均值 Dummy、Ridge(alpha=1) 和 Extra Trees(100 棵树、最小叶节点 2、固定 seed)。仅验证集 MAE 选型，平局按名称排序，未用验证集重新拟合；完成选型后计算各模型测试指标。输出清单记录输入 ID、代码和锁文件哈希、依赖、配置、模型文件哈希、覆盖和逐条测试预测。`models.joblib` 为 Python 序列化文件，只应加载可信产物；推理需与训练相兼容的环境。R² 在记录数不足或目标无变化时为 null 并说明原因。

当前接口仅支持既定训练/验证/测试论文划分，不提供训练侧交叉验证或超参数搜索。合成信息、跨论文重复样品和来源审核的局限沿用快照；模型未提供适用域、校准不确定性或候选推荐。

## I5：解释、经验适用域与显式候选筛选

安装 `uv sync --extra modeling --extra explain --extra dev`。`catalyst-ai dataset diagnose` 接受 I4 的 `--snapshot`、`--qualification`、`--split`、`--features`，以及 `--baseline report.json --model models.joblib --report NEW.json`。该命令重建特征、检查 I4 报告和模型哈希及依赖版本，并核对保存的测试预测，才加载和诊断可信模型。当前仅支持 I4 选择 Extra Trees 的运行。输出验证集五次置换重要性、Tree SHAP 和加和误差、按论文分组误差、训练集排除同论文最近邻距离的 95% 分位阈值、验证/测试组覆盖及树预测分散度。

距离使用训练拟合的填补、缺失指示和缩放；阈值是启发式，未见组分和工况超出训练范围另计，距离本身无法识别未见组分。树间标准差仅是经验分散度；预测 ±2 倍标准差只是用于描述覆盖的固定带宽，不是校准区间，没有名义覆盖率。同一论文内记录相关；验证集曾用于选型，I4 已查看同一测试集，故本诊断不构成全新前瞻验证。重要性不代表物理因果。

`catalyst-ai dataset screen` 接受上述共同输入及 `--diagnostic DIAGNOSTICS.json --spec SPEC.json --report NEW.json`，只筛选明确给出的候选，不生成合成路线。SPEC 需要 `capacity`（默认 4，上限 6）、非空 `allowed_species`、`condition_bounds`（`temperature_k`、`pressure_bar_abs`、`catalyst_mass_g`、`h2_co2_ratio`、`reactants_flow_nl_g_h` 各为 `[min,max]`）、领域契约格式的共同 `fixed_test`、`constraint_evidence`（`equipment`、`chemistry_compatibility`、`precursors`、`cost_risk` 各为非空证据文本）和 `candidates`。每个候选提供 `candidate_id`、I3 支持的 `recipe`、`planned_synthesis`（`route`、`evidence`，可选 I3 白名单 Measurement `parameters`）。这些证据由操作者提供，程序不验证其真实性或完整性。训练集中没有可用合成参数，因此路线和参数不参与本模型预测。

[模拟筛选配置](../data/examples/screening_spec.synthetic_demo.json)仅展示字段形式，所有数值、材料及证据均为虚构，不能用于真实实验；真实配置须由操作者另行提供并审核。

筛选拒绝未闭合组成、非允许或训练未见物种、无路线/证据、缺失或非正工况、超过所给边界或训练工况范围、超过距离阈值的候选。其余按固定工况下预测转化率降序排序，最多选取容量数量，余项保留；每项标记 `proposed` 和 `caution`、未校准树分散度、最近训练记录定位及已知限制。候选、配置、拒绝原因、输入哈希和代码哈希写入新报告，已有文件拒绝覆盖。操作者仍须独立确认所有约束和可操作性，模型输出不是实验批准或实测结果；输入不足时明确失败，不自动填补真实候选。
