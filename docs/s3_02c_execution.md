# S3-02 之 02-C 执行记录

五个 02-A 固定包在恢复到临时隔离目录的本轮代码快照中，以独立 Python 进程各重放 47 条固定输入，输出与 02-A 逐项完全相等；历史 R1 的独立重放见 [02-B 记录](s3_02b_execution.md)。[重放结果](../artifacts/reports/s3-02-20261118-02c/replay-checks.json)和[可重放脚本](../artifacts/reports/s3-02-20261118-02c/verify.py)记录路径和结果。隔离目录使用快照中的 src 和预测脚本，包和输入使用工作区绝对路径，Python 环境及安装依赖仍为外部依赖；不声称环境或模型包完全自包含。属性及映射绑定随包加载校验，具体版本和哈希见 [01 输入清单](../artifacts/reports/s3-01-20261118-01/inputs.json)。

[受保护清单核对](../artifacts/reports/s3-02-20261118-02c/protected-verification.json)中 01 阶段登记的 478 个文件全部匹配，无缺失。此结论限于该清单，不代表未列入清单的所有文件均有历史基准。[本轮证据哈希](../artifacts/reports/s3-02-20261118-02c/evidence_hashes.json)固定正式运行、包、报告及 02-A/B 证据当前状态；这是本轮基准，不是对这些文件此前状态的独立证明。新运行和管理库登记属于计划允许的新增或修改范围，受保护清单不替代对管理库变更的审计。

全量 [pytest 日志](../artifacts/reports/s3-02-20261118-02c/pytest.log)：222 项通过，1 项依赖弃用警告，退出码 0。[Ruff](../artifacts/reports/s3-02-20261118-02c/ruff.log)和[格式检查](../artifacts/reports/s3-02-20261118-02c/format.log)退出码均为 0。首次检查发现 S3-01 登记脚本格式及长行问题，原始日志保留为 `ruff-initial.log` 和 `format-initial.log`；仅调整该脚本排版和等价字符串拼接，未重跑或更改正式比较结果。

[代码快照](../artifacts/reports/s3-02-20261118-02c/code.zip)、[代码哈希](../artifacts/reports/s3-02-20261118-02c/code_hashes.json)、[环境](../artifacts/reports/s3-02-20261118-02c/environment.json)及[依赖版本](../artifacts/reports/s3-02-20261118-02c/dependencies.txt)固定本次检查状态。与 01 冻结清单相比，workbench 的两个源码文件和四个测试文件已变化；本轮未建立这些变化的完整来源与对正式比较的独立影响分析，不能将当前代码快照视为原正式运行代码，原始快照仍保留在 01 证据中。

审阅 [比较说明](s3_01_comparison.md) 与 [02-A 记录](s3_02a_execution.md)：主指标使用全部 OOF 诊断记录，入口可用子集另报；历史 test 标为历史参照，家族对照标为跳过。R2 分母及 OOF 选择结论在这些记录中一致。本记录不代表 02-D 或 S3-02 整体验收完成；代码差异影响分析及未列入受保护基准的范围须在整体验收时处理。
