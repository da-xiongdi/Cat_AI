# AI辅助CO₂加氢制甲醇催化剂开发平台

当前已跑通 **数据接入与治理 → 目标冻结 → 论文分组 → 初版组成/工况特征 → 单目标基线 → 初步诊断**。对照总体A–F路线，当前聚焦 **C特征工程与预测能力完善，D辅助评价**。这是一条最小可运行路径，特征方案与预测模型尚未定型；E筛选和F实验反馈属于后期。

TheMeCat已完成820条v2修订，609条通过治理，冻结593条CO₂转化率记录；按37个论文组划分训练/验证/测试集。已有Dummy/Ridge/Extra Trees模型、诊断及4项固定工况探索性组成输出。数据按用户决定接受公开来源，压力按用户假设视作绝压，尚未逐条原文核验；现有结果不构成正式实验推荐或甲醇性能/合成工艺优化结论。当前证据和下一步研究入口见[进度汇总](docs/progress.md)。

需求与科研边界唯一基准：[开发指引](docs/project_development_guide.md)。原文件 `docs/architecture/AI_CO2_MeOH_Catalyst_Development_Guide_v0.2.md` 完整保留；约定路径是它的逐字节副本。首次审计仅发现该指引，无代码、真实数据或既有测试，见 [来源审计](docs/source_audit.md)。

后续实施使用[论文评审补充的实施与验收清单](docs/implementation_amendment.md)：I1–I4的单目标路径和I5初步诊断已有运行证据；样品/批次独立评价、工艺建模和正式实验闭环仍待完成。

TheMeCat专项执行依据见[数据库实施方案](docs/themecat_implementation_plan.md)。B0–B2及B4/I1已完成首批执行，B3按用户决定暂缓。近期依照“先完善上游”的共识推进 **特征工程 → 模型比较与分组评价 → 独立预测入口**，按覆盖扩展甲醇相关目标。Extra Trees仅是当前一次基线比较选中的工作模型，不能视为最终预测方案；当前不推进实验候选或设备/批次准备。

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

运行模型和解释模块时安装相应可选依赖：`uv sync --extra dev --extra modeling --extra explain`。入口为`catalyst-ai dataset split/features/baseline/diagnose/screen`各子命令（逐个用`--help`查看参数）；完整输入契约见[API契约](docs/api_contracts.md)。

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

上面的尖括号是占位符，不能原样执行。默认人工核验路径要求独立审核；TheMeCat另有显式`--accept-themecat`来源接受策略及593条冻结记录，详见[专项方案](docs/themecat_implementation_plan.md)。这一路径不创建人工审核事件。研究快照拒绝synthetic_demo；仅为测试接口可显式增加`dataset build --demo`，仍要求独立审核，产物标记`synthetic_demo`、`scientific_use=false`并存放在`snapshots/demo/`。

快照保存完整冻结记录、样本ID、原文件/内容哈希、配置/代码哈希、目标口径及审核或来源接受证据。JSON是当前实现；特征、划分、模型和诊断由独立后续命令生成，不改写快照。人工核验针对整条记录；保留输入层原始`pending`，有效人工核验状态以不可覆盖的review_event为准。详见[接口契约](docs/api_contracts.md)。

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

仅进行有依据的单位换算，不统一不同工况的性能，不计算收率/STY标签。TheMeCat质量归一流量与体积GHSV分别建模；未报告基准不猜测。表征不能放入配方契约，现有设计模型使用组成和测试工况，不使用BET等制备后表征；合成参数因缺乏训练数据尚未建模。

批次默认4，`configs/project.yaml`可设1–6，命令可覆盖容量但硬上限6；已有候选筛选接口及探索性清单，尚未完成正式实验推荐、真实批次状态机或设备控制。

## 项目目录与证据

| 路径 | 当前作用 |
|---|---|
| `src/catalyst_ai/schemas` | Pydantic 契约与一对多关系校验 |
| `src/catalyst_ai/sources` / `governance` | 本地适配器、保守质量规则 |
| `src/catalyst_ai/storage` | SQLite 实体、事务、快照 |
| `src/catalyst_ai/datasets` / `features` | 目标准入、论文划分与受限设计特征 |
| `src/catalyst_ai/modeling` | 单目标基线、解释/经验适用域与条件化筛选 |
| `src/catalyst_ai/reporting` | JSON/文本报告、代码/配置证据 |
| `src/catalyst_ai/interfaces.py` | 未来特征/预测/推荐 Protocol，无算法实现 |
| `data/raw` / `staged` / `curated` | 哈希原件、待治理档案、待核验治理结果 |
| `data/examples` | 明确为 synthetic_demo 的 CSV/JSON |
| `artifacts/reports/acceptance` | 初次工程验收日志、质量报告和运行清单 |
| `artifacts/reports/themecat-*` | 分阶段审计、治理、划分、特征、模型、诊断及组成探索证据 |
| `tests/unit` / `tests/integration` | 契约、科学边界、导入、核验、CLI 测试 |

[实际进度与待办](docs/progress.md) · [架构决策](docs/decisions.md) · [完整新增文件清单](docs/change_inventory.md)

SQLite 是事务事实源；raw 文件由应用只追加写入并核对哈希，未设置操作系统只读权限。数据库提交后的 JSON/摘要属于导出物，磁盘故障时可能缺失，可用 `validate --run-id ... --report ...` 恢复质量报告。当前未提供 staged/curated 导出物的自动恢复命令；保留数据库与 raw 的联合备份。运行档案的 raw_path 为绝对路径，跨目录迁移尚需路径映射。未实现多用户权限、加密存储、数据库迁移或审核人身份认证；实际科研使用前仍需来源/许可及核验策略审计。

TheMeCat v1 原始 CSV 导入：`catalyst-ai ingest --adapter themecat-v1 --source literature --input TheMeCat_v1.csv`（可加 `--dry-run` 预检）。来源授权、实际导入统计及待核验限制见 [接入审计](docs/themecat_v1_audit.md)。

TheMeCat 独立原件审计（不写数据库、无需 pandas）：

```powershell
uv run python scripts/validate_themecat.py --input data/raw/46000f00323ac64a79f63777e54c05634e83d1a6476176c8b6569122bd03dfbd.csv --output artifacts/reports/themecat-audit-new --check-relations
```

输出目录必须不存在。省略 `--check-relations` 时只作原始计数、缺失、数值和重复检查；启用后的关系式仅作假设性诊断，不生成训练标签或批准记录。实际[本次审计报告](artifacts/reports/themecat-20261110/profile-final/quality_summary.json)和[补充材料原件索引](docs/references/themecat/README.md)可追溯。
