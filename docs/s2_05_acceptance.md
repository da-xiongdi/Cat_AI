# S2-01、S2-04、S2-05 工程验收（2026-11-17）

操作及验收登记：Codex。S1B-01 前置任务已完成且验收证据有效；S2-01 配置契约、S2-04 特征适配及 S2-05 配置化训练与评价已依次完成工程验收。管理库任务修订分别为 6、6、7，验收标准版本分别为 2、1、1。每项标准及证据哈希见[验收依据](../artifacts/reports/s2-acceptance-20261117/acceptance.json)，管理库状态与演练记录见[登记结果](../artifacts/reports/s2-acceptance-20261117/registration.json)。

- S2-01：独立配置、参数范围、默认/自定义模式和配置来源已核对；两个配置通过真实加载与训练重放。
- S2-04：复用 [S1-B 验收](s1_b_acceptance.md) 的 553 条增量、公式、缺席角色、换序合并和规范输入证据；增强特征与折内词表、缩放回归通过。
- S2-05：[默认 R2](../artifacts/runs/s2-replay-20261117/baseline/report.json) 和[自定义训练](../artifacts/runs/s2-replay-20261117/custom/report.json)均在新目录运行；逐条记录、状态、折归属、输入及代码哈希核对见[重放检查](../artifacts/runs/s2-replay-20261117/verification.json)。train/validation/历史 test 为 454/47/52 条，三折为 152/151/151 条。默认选中 F_base/extra_trees，自定义选中 F2/extra_trees。OOF 含未支持物种及部分越界诊断，不能将全部诊断结果当作入口可用预测。

[固定代码快照](../artifacts/runs/s2-replay-20261117/code.zip)含当时源码、脚本、测试及项目配置；[哈希清单](../artifacts/runs/s2-replay-20261117/code_hashes.json)在验收时与工作区一致。全量 pytest **202 passed**、1 条 Starlette/httpx 弃用提示；项目规定范围 Ruff 检查和格式检查通过，原始记录分别为 [pytest](../artifacts/reports/s2-acceptance-20261117/pytest.log)、[Ruff](../artifacts/reports/s2-acceptance-20261117/ruff.log)、[格式](../artifacts/reports/s2-acceptance-20261117/format.log)。

管理库先备份并在副本完整演练，再按修订号登记成果、提交并确认验收；备份 `before.sqlite`、演练 `rehearsal.sqlite` 和登记后 `after.sqlite` 位于验收目录。完整性检查通过、外键错误为零；旧运行保留。

这是工程验收，不代表 S3 正式配对比较、增强模型包或独立预测验收。S2-06 和 S2-02 仍为 planned。已查看 test 仅作历史对照；来源接受不等于逐行原文核验，绝压沿用既有假设。
