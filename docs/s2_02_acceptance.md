# S2-02 集成工程验收（2026-11-18）

S2-02 按[实施计划](s2_implementation_plan.md)完成验收。前置 S2-06 同批核验并先行登记完成，S2-01/04/05 沿用[既有验收](s2_05_acceptance.md)。操作及验收登记：Codex。

本次固定证据位于 [acceptance.json](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/acceptance.json)，包含逐标准映射、运行及文件哈希、原件/快照/领域库/旧运行未变校验。代码、脚本、测试、配置及项目依赖定义保存为 [code.zip](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/code.zip)，对应 [code_hashes.json](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/code_hashes.json)。复放入口为 [accept_s2.py](../scripts/accept_s2.py)。此前未完成的脚本尝试目录不作为验收依据。

| 交付项 | 验收结果与证据 |
|---|---|
| 配置、目录及帮助 | 实际执行 catalog、schema、三脚本帮助及三配置校验；保留有效配置与参数来源；拒绝覆盖旧运行 |
| 默认基准 CLI | R2 三特征组 × 三模型、三折；选中并打包 F_base/extra_trees；见 [baseline-run](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/baseline-run/report.json) |
| 自定义多模型 CLI | F2 的 Ridge(alpha=2) 与 ExtraTrees；OOF 选中 ExtraTrees，显式指定打包 Ridge；见 [custom-run](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/custom-run/report.json) |
| 自定义单模型 Python | F2/Ridge(alpha=3)；校验、训练、保存、重载及 CLI 预测；见 [single-run](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/single-run/report.json) |
| 保存、加载及预测 | 三个独立运行和 model_id；每包单对象、混合批次及 validation 全部47条输入均通过 CLI/Python 核对；重载前后结果一致 |
| 训练与预测转换 | 基准原始预测完全一致；两个 Ridge 运行逐条预测与训练报告的最大绝对差分别为 1.42×10⁻¹⁴、7.11×10⁻¹⁵，满足浮点比较容差 |
| 失败与边界回归 | 非法配置、DOI组数不足、绑定/文件/属性/词表/身份/依赖篡改、未支持正含量物种、零含量未知项、输入和输出越界、非有限输出及混合批次均有验证；F1/F2均覆盖预测边界 |
| R1旧包兼容 | 固定历史包的47条 validation 结果与历史 JSON 全部一致；见 [r1-replay.log](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/r1-replay.log) |
| 工程检查 | [pytest](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/pytest.log)：210 passed，1条既有 Starlette/httpx 弃用提示；[Ruff](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/ruff.log)和[格式](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/format.log)检查通过，范围 src/tests/scripts |

默认包 validation 为26条 ok、2条 caution、19条未支持物种角色。两个 F2/Ridge 包均为25条 ok、2条 caution、1条输出越界、19条未支持物种角色。输出越界保留原始值，正式值为 null；批次不删无效项。未知物化映射返回 invalid_input 并在 validation 中给出 unsupported_species 原因，不切换至 R1。

管理库先备份，再在副本按相同修订号演练，随后应用实际库，完整性和外键检查通过。登记结果见 [registration.json](../artifacts/reports/s2-02-acceptance-20261118-4b556afa/registration.json)：S2-06 为 done（revision 6、criteria_version 1），S2-02 为 done（revision 9、criteria_version 2）。同目录 before.sqlite、rehearsal.sqlite、after.sqlite 保留管理证据。

S2 工程交付清单：S2-01 配置契约、S2-04 特征适配、S2-05 训练评价、S2-06 模型包、S2-02 集成均已完成；S2-03 家族对照资格仍为 ready，未在本次范围内验收。S3-01 正式共同子集配对比较及 S3-02 整体验收仍为 planned。本次不以 MAE 改善为工程门槛，不将烟测记为科研比较完成；已查看 test 仅作历史对照，来源接受不等于逐行原文核验，绝压沿用既有假设。
