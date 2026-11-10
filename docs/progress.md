# 实施进度（截至2026-11-10，Asia/Shanghai）

科研需求基准：[项目开发指引](project_development_guide.md)。下表为Task A和Task B最小切片的初次交付；后续I1实现及验证单独记于文末，均不代表研究效果。

后续补充的实施顺序与验收依据见[实施与验收清单](implementation_amendment.md)。下表仍记录A+B已有实现；新增规划不计入已实现/已验证。

本页按日期追加历史验收记录；早期“仅有模拟数据/下一项I2”等描述是当时状态。最新状态：TheMeCat 经用户指定绝压假设完成 820 条修订，609 条 curated、211 条 staged，按公开数据集来源接受策略冻结 593 条 CO₂ 转化率记录；B3 暂缓，人工审核事件为 0，详见[专项实施方案](themecat_implementation_plan.md)及本页末节。

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


## 2026-11-10?I3 ??????

????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????

?? I2 ??????? [???](../artifacts/reports/themecat-i3-20261110/features.json)?593 ???? 493??? 47??? 53?????? 32 ????? 18 ????? 21 ???????????????????`uv run python -m pytest -q` 99 ????`uv run ruff check src tests scripts` ? `uv run ruff format --check src tests scripts` ???

???????????????????????????????????????????????????????????????????????????????????/??????? [I3??](api_contracts.md)?
