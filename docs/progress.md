# 实施进度（截至2026-11-10，Asia/Shanghai）

科研需求基准：[项目开发指引](project_development_guide.md)第9节的 A–F 路线；增量验收依据见[实施与验收清单](implementation_amendment.md)和[TheMeCat 专项方案](themecat_implementation_plan.md)。本节汇总当前状态，下文按日期保留历史记录；历史中的“无真实快照”“下一项 B1”“尚未训练”等不代表现状。

## 当前阶段：C 特征工程与预测能力完善，D 辅助评价

已跑通 TheMeCat 原始数据 → 版本化修订与治理 → 目标准入和冻结 → 论文分组 → 初版组成/工况特征 → 单目标基线 → 初步诊断。这里的“跑通”表示有最小可运行路径，特征工程和预测模型尚未定型。当前继续完善上游数据、特征、训练、评价和独立预测能力；D的解释/适用域用于检验和改进预测模型。E/F保留为后期路线，已有筛选接口和探索清单不改变当前优先级。

**2026-11-10 用户重申的执行共识：先完善上游，从特征工程和性能预测开始；实验属于后期。** 当前模型研究不以补齐实验候选、设备或前驱体约束为前置条件，也不把正式筛选、批次或实验反馈列为近期任务。B3继续按既有决定暂缓。

### 预测模型是否已经确定

**尚未定型。** I4仅比较了固定参数的Dummy、Ridge和Extra Trees，并在当前一次论文划分上按验证MAE选中Extra Trees，作为该次运行及后续诊断的工作模型。这不等于平台最终选定算法、特征方案或参数，也不代表最终目标和预测能力已验收。现有目标为CO₂转化率，初版输入为材料物种mol%和工况；还需完成特征版本对比、分组验证、必要的模型/参数比较，以及可复用的独立预测入口。

| 总体任务 | 已实现/已运行的范围 | 尚未完成的验收或研究证据 |
|---|---|---|
| A — 骨架与数据契约 | 首期工程交付完成；实体关系、CLI、环境和容量约束已有测试 | 历史打包验收对应当时版本，不代表当前代码已重新发布 |
| B — 接入与治理 | 首期工程链路完成；B0–B2 已实现；820 条 v2 修订中609条 curated、211条 staged；冻结593条 CO₂ 转化率记录 | B3 按用户决定暂缓；人工审核事件0；绝压为用户假设；不把来源接受称为逐行核验，211条阻断仍保留 |
| C — 特征与基线 | I1–I4 的组成+工况单目标路径已运行；37论文组，训练/验证/测试493/47/53行；Dummy、Ridge、Extra Trees模型与报告已保存 | 未确认真实样品/批次关系，尚无其独立留出评价；未完成材料家族留出、通用/专用模型比较、合成工艺建模和甲醇相关目标扩展；不能标为总体C全部验收完成 |
| D — 解释及适用域 | I5 已实现并运行置换重要性、SHAP、逐论文误差、距离启发式和树间预测分散度；模型卡已保存 | 适用域尚无独立可靠性验证；树间分散度未校准；相关性解释不等于机理证明 |
| E — 筛选与推荐 | 已实现显式候选筛选、固定工况预测、约束输入检查和槽位上限；另有4项探索性组成清单 | 未取得真实制备路线、前驱体、设备与成本/风险依据；未完成真实候选筛选、Pareto/信息增益排序、对照/重复设计和实验批次规划 |
| F — 实验反馈与迭代 | 保留通用实验数据接入契约及容量检查 | 候选到实测的批次状态流转、计划/实际关联、失败案例回灌、新快照重训比较及真实实验闭环均未完成 |

以上状态是对总体设计的映射，不改变原开发指引。数据源接受策略和压力假设来自此前用户决策；原指引中的人工核验要求仍是后续强化证据的路径，当前快照显式标记 `published_dataset_accepted_not_row_verified`。

### 已验证成果与证据

- 数据：[治理摘要](../artifacts/reports/themecat-governance-20261110/summary.json)记录820条修订、609条治理通过；CO₂转化率593条合格，227条排除（211条未curated、16条缺目标）。原件保留，修订可追溯。
- 划分与特征：[I2说明](../artifacts/reports/themecat-i2-20261110/README.md)和[I3特征表](../artifacts/reports/themecat-i3-20261110/features.json)。论文分组隔离不证明未知跨论文样品独立。
- 模型：[I4报告](../artifacts/reports/themecat-i4-20261110/report.json)中验证集选中Extra Trees，测试MAE 2.872、RMSE 4.368个百分点，R² 0.270；测试集53行、5个论文组。这是现有单次划分的探索性结果，尚未证明新的材料或批次泛化能力。
- 诊断及探索：[I5模型卡](../artifacts/reports/themecat-i5-20261110/model_card.md)与[组成探索清单](../artifacts/reports/themecat-exploration-20261110/README.md)。测试21/53行含训练未见组分，经验区间覆盖39/53；4项组成仅供讨论，不是已批准实验计划。
- 最近一次代码核对（2026-11-10，前一轮状态核查实际执行）：`uv run --extra modeling --extra explain --extra dev python -m pytest -q`：**106 passed in 13.92s**；`uv run ruff check src tests scripts`通过；`uv run ruff format --check src tests scripts`：54 files already formatted。本次仅更新文档，未重新训练、筛选、审核或冻结数据；不将已有结果记作新增科研验证。
- 本次文档检查：5份更新文档中的78个本地文件链接均存在，`git diff --check`通过；两份开发指引SHA-256仍相同且未改变（`64ba32d98cdfd4778cef1158f597e2179376c380ee3a816314dd9c31664a757e`）。

### 下一步：特征工程 → 预测建模 → 评价 → 独立预测（规划，未执行）

1. **先完善特征工程。** 以现有冻结快照和初版特征为基准，明确材料物种/角色/比例、载体及工况的表达，处理未见组分与缺失状态，按证据评估通用组成描述符。每套特征保留版本、来源和可获得阶段；不把材料mol%直接当元素原子分数，不补造缺失工艺，不引入性能或制备后表征泄漏。输出可比较的特征方案及覆盖报告，未知转换依据的特征拒绝生成。
2. **完善训练、模型比较和选择。** 在相同目标准入和论文分组下比较特征方案及预测模型，保留Dummy/Ridge/Extra Trees基线。所有词表、填补和缩放在各训练折重新拟合；必要的参数选择只在训练侧分组验证，报告逐论文误差、物种/工况覆盖、稳定性和失败原因。模型由这些证据选择，不能因当前一次Extra Trees得分较好就固定算法。通用/材料家族专用模型和样品分组在覆盖及身份依据允许时评价，不足则明确跳过。仅工况与组成+工况、有/无装填量的对照属于这一建模评价环节。
3. **打通可复用的独立预测入口。** 在现有模型保存、加载和哈希校验基础上，将特征处理与模型绑定；支持输入组成与工况、加载指定模型版本、返回目标/单位/预测及缺失或未见组分提示。明确适用域与经验不确定度；输入非法或关键特征无法表达时拒绝或标记不可用。预测入口独立于候选筛选和实验计划，验证保存/加载后输出一致及训练/预测处理一致。
4. **按覆盖逐步扩展目标。** 保留现有CO₂转化率作为上游开发基准；核查甲醇选择性、收率、STY的定义、单位、缺失和独立论文覆盖，再决定哪些目标可建立独立预测模型。覆盖不足时不训练，不用关系式补标签，也不把转化率模型称作甲醇产率模型。

近期交付目标是“有版本的特征方案 + 可复现的模型比较/评价 + 可加载调用的预测管线和入口”。既有SHAP、距离诊断和树间分散度用于辅助发现模型局限，不能替代预测验证。现有测试集已被查看，保留作历史参照，后续选模用训练侧分组验证；独立确认数据另行规划，不要求当前先开展实验。

本次仅修正状态与近期路线，不执行新训练或开发。后期E/F任务仍保留在总体设计中，本阶段聚焦C及服务于C的D能力，详见[ADR-015](decisions.md#adr-015先完善特征工程与预测能力模型尚未定型2026-11-10)。

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
