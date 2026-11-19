# S2-03 家族对照资格检查（2026-11-18）

结论：当前没有可用于逐记录分组的、经核验的标准化家族标签，A/B1 家族对照整体跳过；这不阻断统一模型。这里完成的是资格检查，不是家族模型训练或科研比较。不得将未知家族的覆盖计为某个具体家族的零覆盖。

## 资格判据及时间限制

对将来的家族对照，先固定可追溯的分类定义、逐记录标签、证据位置及冲突/复合/未知处理；不得按样品名或元素机械分类。固定 S1 v4 共同支持子集及原 DOI 分区；某家族必须在原 train、validation、test 各有已核实记录及 DOI，train 至少有 3 个不同 DOI，才能运行既定三折 DOI 分组 CV，且每折非空。比较时 A 和 B1 使用相同特征、算法和参数，在同一该家族留出记录上评估；validation 不用于选模，已查看 test 仅作历史参照。数量满足是必要条件而非充分的统计可靠性保证；记录每折覆盖并报告样本量。无可靠标签或任一条件不足时跳过并说明，不回退随机拆分。

这些判据在本次资格统计之前确定，未依据家族模型分数调整；但历史 R1 成绩及 S2 工程烟测的总体分数在本次之前已经查看（见 S2-02 验收），因此不能声称在查看任何模型分数前预注册。不存在本次家族对照分数。

## 标签来源核查

[TheMeCat 适配器](../src/catalyst_ai/sources/themecat.py)将 `catalyst_name` 原样写入 `recipe.material_family`；它是开放的样品名称，不是标准类别。原始数据曾有 195 个不同名称，S1 v4 保留子集有 181 个；均不能当作家族类别统计。领域 schema 只要求非空字符串，并未规定分类体系或逐条证据。[映射](../configs/s1_species_mapping_v2.json)是名义物种中心计算规则，并非家族标签；其中 LaMn/Cu 论文题名仅提供系列背景，不证明每条记录的家族归属或逐行原文核验。混合体系和角色无法由名称或组分可靠地单义判定。本次检查现有快照、映射和来源处置，未找到覆盖本子集的独立标准化逐记录家族标签及证据；不排除未来经原文审查建立部分标签。

## 分区覆盖及跳过

基于 [S1 v4 selection](../artifacts/reports/s1-b-20261113-v4/selection.json) 保留的记录，与其绑定的[快照](../data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json)按 record_id 关联，DOI 去除首尾空格并转小写去重。分区沿用[原 DOI 分区](../artifacts/reports/themecat-i2-20261110/split-verified.json)。

| 标签状态 | 分区 | 记录数 | 不同 DOI 数 | 资格 |
|---|---|---:|---:|---|
| 家族未核实 | train | 454 | 26 | 不可判定具体家族 |
| 家族未核实 | validation | 47 | 6 | 不可判定具体家族 |
| 家族未核实 | test（历史） | 52 | 4 | 不可判定具体家族 |
| 家族未核实 | 合计 | 553 | 36 | 跳过全部 A/B1 家族对照 |

目前可信家族清单为空，因此不存在可计算的逐家族分区计数；上表是未分类总体覆盖，不是家族覆盖。下一步须先建立有来源定位、覆盖范围和复合/未知处置的逐记录标签，再重算每个已核实家族的各分区记录和 DOI 数并重新判定。不得将标题、样品名、属性映射或来源接受提升为逐记录分类核验；不提前引入 B2 专属特征或专家架构。

## 收尾验收与证据

本次验收范围为“资格检查完成，当前全部 A/B1 家族对照有依据地跳过”。操作及验收登记：Codex；不代表新增人工原文核验、家族模型训练或 S3 科研比较。

| 标准 | 验收依据 |
|---|---|
| C1 标签依据 | 核对适配器、领域 schema、固定快照、v2 物种映射和来源处置；现有样品名称不升级为标准分类，可信逐记录家族清单为空 |
| C2 判据与覆盖 | 本报告固定将来家族比较的资格规则，重算并保留原分区记录/DOI数及553条逐记录状态。没有家族分数；“分数查看前”按本任务的家族对照分数解释，历史 R1/S2 总体分数已查看的限制明确披露，不声称在所有分数前预注册。可信家族为空时逐家族覆盖不可计算，不填造零值 |
| C3 跳过及边界 | 因缺少可信标签跳过全部 A/B1，不强行分类，不阻断统一模型，不引入 B2 或专家架构 |

固定证据目录为 [s2-03-acceptance-20261118](../artifacts/reports/s2-03-acceptance-20261118/)：

- [acceptance.json](../artifacts/reports/s2-03-acceptance-20261118/acceptance.json)：逐标准解释、输入/源码/报告哈希及验收边界。
- [coverage.json](../artifacts/reports/s2-03-acceptance-20261118/coverage.json)：各分区 DOI 清单、553条原始样品名及家族未核实状态；未使用目标值或模型分数作分类。
- [sources.zip](../artifacts/reports/s2-03-acceptance-20261118/sources.zip)：本次审查的快照、分区、selection、适配器、schema、映射、来源处置、本报告和收尾脚本。
- [registration.json](../artifacts/reports/s2-03-acceptance-20261118/registration.json)：副本演练和实际登记结果；同目录 before.sqlite、rehearsal.sqlite、after.sqlite 保留管理库备份和登记快照。
- [verification.json](../artifacts/reports/s2-03-acceptance-20261118/verification.json)：领域库、原件、快照和其他任务未变核对，以及完整性、外键和产物哈希。

重放统计可用 `.venv/Scripts/python.exe scripts/accept_s2_03.py --output artifacts/reports/<新目录>`；登记操作另加 `--register`，仅允许尚为 ready 的 S2-03，拒绝覆盖已有目录或重复验收。登记后任务状态以 registration.json 为准；S3-01/02 保持未执行。
