# AI辅助CO₂加氢制甲醇催化剂开发平台

当前交付为 **Task A + Task B 最小切片，以及 I1 目标资格视图**：数据契约、CSV/JSON 导入、保守治理、人工核验事件、快照入口、目标准入/排除与覆盖清单。没有训练模型、预测排名或实验结论。

需求与科研边界唯一基准：[开发指引](docs/project_development_guide.md)。原文件 `docs/architecture/AI_CO2_MeOH_Catalyst_Development_Guide_v0.2.md` 完整保留；约定路径是它的逐字节副本。首次审计仅发现该指引，无代码、真实数据或既有测试，见 [来源审计](docs/source_audit.md)。

后续实施使用[论文评审补充的实施与验收清单](docs/implementation_amendment.md)：将有效建议接入原任务B–D。I1已实现并通过模拟数据软件验证；分组切分、设计特征和单目标基线仍为规划。

TheMeCat 专项执行依据见[数据库实施方案](docs/themecat_implementation_plan.md)：补充材料已归档，独立审计已运行；下一项先做数据语义与治理 v2，再做可追溯修订、原文核验与 I2–I4。补充说明中的训练/筛选命令属于规划，不代表已有功能。

## 安装与验收

Python ≥3.11；本机实际验收 Python 3.14.3 / Windows。已有默认 Python 3.8 不适用。PowerShell，在项目根目录运行：

```powershell
uv sync --extra dev
uv run catalyst-ai --help
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run python scripts/smoke_test.py
```

不用 uv 时：用 Python ≥3.11 创建虚拟环境，再运行 `python -m pip install -e ".[dev]"`。核心依赖仅 Pydantic、SQLAlchemy、PyYAML。pandas/pyarrow 是后期可选依赖，本轮不安装、不生成 Parquet。

## 最小可运行流程

```powershell
# dry-run 不建库、不写原始留存、不写报告文件。完整 JSON 在 stdout，可读摘要在 stderr。
uv run catalyst-ai --config configs/project.yaml ingest --source literature --input data/examples/synthetic_demo.csv --dry-run
uv run catalyst-ai --config configs/project.yaml init
uv run catalyst-ai --config configs/project.yaml ingest --source literature --input data/examples/synthetic_demo.csv
uv run catalyst-ai --config configs/project.yaml status
uv run catalyst-ai --config configs/project.yaml validate --report artifacts/reports/quality-review.json
uv run catalyst-ai --config configs/project.yaml batch check --capacity 6 --candidate-id demo-slot-1
```

所有样例为 **synthetic_demo**，是虚构的格式/流程输入；`literature` 只表示适配器的来源类型，样例并非实际文献。CSV 与 JSON 是同一条记录的两种序列化；导入 CSV 后再导入 JSON 会报告重复，而不会新增科学观测。

`--config` 放在子命令之前；配置中的相对路径以**当前工作目录**为准。重复运行使用新报告路径；文件均拒绝覆盖。

退出码：`0` 成功（可能有 warning），`2` 完成治理但包含 staged/duplicate（合格行仍可入库），`1` 操作失败/门禁拒绝；argparse 用法错误也是 `2`，此时没有 JSON 报告。请同时检查退出码和报告 counts。

## 人工核验与快照

导入状态与核验状态彼此独立：`staged → curated` 只表示通过结构/阻断规则；`curated` 默认 `pending`。导入文件自带的 `verified` 会阻断入库，不能绕过核验。

人工检查原文、数值、单位、工况、指标定义及每项 warning 之后，用实际记录 ID 执行：

```powershell
uv run catalyst-ai review --record-id <record-id> --reviewer <复核人> --decision verified --evidence "页/表/图及逐项核对说明" --acknowledge-warnings
uv run catalyst-ai dataset build --target co2_conversion --record-id <record-id>
```

上面的尖括号是占位符，不能原样执行。本轮没有可供研究快照使用的真实数据。研究快照默认拒绝 synthetic_demo；即使演示记录被显式审核也不能进入研究快照。仅为测试快照接口，可显式增加 `dataset build --demo`，它仍要求独立审核事件，产物标记 `synthetic_demo`、`scientific_use=false`，存放在 `snapshots/demo/`。本轮正式工作区没有创建审核批准事件。

快照保存完整冻结记录、样本 ID、原文件/内容哈希、配置/代码哈希、目标口径、审核证据。JSON 是当前最小实现；不派生指标、不生成特征表、不执行训练切分。核验针对整条记录；保留输入层原始 `pending`，有效核验状态以不可覆盖的 review_event 为准。详见 [接口契约](docs/api_contracts.md)。

## 目标资格与覆盖清单（I1）

`dataset qualify` 要求显式记录ID、目标定义和标准单位，输出各条记录/目标观测的纳入或排除原因、内容哈希和来源/配方/批次覆盖。以下为占位语法，需替换定义与ID：

```powershell
uv run catalyst-ai dataset qualify --target co2_conversion --target-definition "<原文指标定义>" --target-unit "%" --record-id "<实际记录ID>" --report artifacts/reports/target-eligibility.json
```

默认只读检查并输出JSON，`--report`仅保存报告；模拟记录需显式增加`--demo`。`--freeze`会重查全部所选记录，再复用现有快照门禁冻结合格记录，并在快照旁的`qualifications/`保存不可覆盖的关联清单。缺标签不造值，同目标多观测不求均值；上下文不明或同记录含不合格目标观测时整条排除。完整性问题阻断整次冻结。

资格命令退出码：`0`全部合格；`2`完成检查但有排除/空集；`1`完整性阻断或冻结空集（仍输出原因），以及参数/IO错误。结果中的数据类别标记不代表科研有效性。当前工作区演示记录因未人工核验被排除，见[实际资格报告](artifacts/reports/i1-20261109/workspace_pending_qualification.json)。

## 数据结构与科研限制

```text
source_document → extraction_record
catalyst_recipe → synthesis_run → test_run → performance_observation
                       └──────── characterization（独立存储）
import_run → staged_record → curated_record → review_event → dataset_snapshot
```

材料体系标签、元素/化合物/载体/助剂开放；同配方支持多个制备批次，同批次支持多个测试工况，每个工况支持多个观测点。数值以 `Measurement` 结构保存原值、单位、语义、标准值、定义、定位、抽取状态、质量标志、误差和 provenance。CSV 的对象/数组单元格使用 JSON；字段详见 [数据字典](docs/data_dictionary.md) 与 [生成式 schema](configs/data_schema.yaml)。

本轮仅进行明确的温度/绝压单位换算和单位识别，不统一不同工况的性能，不计算收率/STY。GHSV 参考状态和体积基准不明时不赋予标准值。表征不能放入配方契约；未来设计模型只允许 A+B 输入。

批次默认 4，`configs/project.yaml` 可设 1–6，命令可覆盖容量但硬上限 6；这是资源约束接口，还没有推荐、真实实验批次状态机或设备控制。

## 项目目录与证据

| 路径 | 当前作用 |
|---|---|
| `src/catalyst_ai/schemas` | Pydantic 契约与一对多关系校验 |
| `src/catalyst_ai/sources` / `governance` | 本地适配器、保守质量规则 |
| `src/catalyst_ai/storage` | SQLite 实体、事务、快照 |
| `src/catalyst_ai/reporting` | JSON/文本报告、代码/配置证据 |
| `src/catalyst_ai/interfaces.py` | 未来特征/预测/推荐 Protocol，无算法实现 |
| `data/raw` / `staged` / `curated` | 哈希原件、待治理档案、待核验治理结果 |
| `data/examples` | 明确为 synthetic_demo 的 CSV/JSON |
| `artifacts/reports/acceptance` | 本次实际验收日志、质量报告和运行清单 |
| `tests/unit` / `tests/integration` | 契约、科学边界、导入、核验、CLI 测试 |

[实际进度与待办](docs/progress.md) · [架构决策](docs/decisions.md) · [完整新增文件清单](docs/change_inventory.md)

SQLite 是事务事实源；raw 文件由应用只追加写入并核对哈希，未设置操作系统只读权限。数据库提交后的 JSON/摘要属于导出物，磁盘故障时可能缺失，可用 `validate --run-id ... --report ...` 恢复质量报告。当前未提供 staged/curated 导出物的自动恢复命令；保留数据库与 raw 的联合备份。运行档案的 raw_path 为绝对路径，跨目录迁移尚需路径映射。未实现多用户权限、加密存储、数据库迁移或审核人身份认证；实际科研使用前仍需来源/许可及核验策略审计。

TheMeCat v1 原始 CSV 导入：`catalyst-ai ingest --adapter themecat-v1 --source literature --input TheMeCat_v1.csv`（可加 `--dry-run` 预检）。来源授权、实际导入统计及待核验限制见 [接入审计](docs/themecat_v1_audit.md)。

TheMeCat 独立原件审计（不写数据库、无需 pandas）：

```powershell
uv run python scripts/validate_themecat.py --input data/raw/46000f00323ac64a79f63777e54c05634e83d1a6476176c8b6569122bd03dfbd.csv --output artifacts/reports/themecat-audit-new --check-relations
```

输出目录必须不存在。省略 `--check-relations` 时只作原始计数、缺失、数值和重复检查；启用后的关系式仅作假设性诊断，不生成训练标签或批准记录。实际[本次审计报告](artifacts/reports/themecat-20261110/profile-final/quality_summary.json)和[补充材料原件索引](docs/references/themecat/README.md)可追溯。
