# S3-02 之 02-B 执行记录

02-B 的失败路径及回归检查完成；本记录不代表 02-C、02-D 或 S3-02 整体验收完成。02-A 固定包及真实预测证据见 [02-A 记录](s3_02a_execution.md)。

| 用例与预期 | 实际及证据 |
|---|---|
| 未知字段或模型、非法参数、重复配置：拒绝 | 通过；`test_unknown_and_duplicate_configuration`、`test_parameter_validation`、`test_duplicate_yaml_and_missing_dependencies` |
| DOI 组不足：拒绝，不回退行拆分 | 通过；`test_fold_limit_and_tampered_build`、`test_insufficient_training_groups` |
| 运行或包目录已存在：拒绝覆盖，原文件哈希不变 | 通过；`test_existing_outputs_are_not_overwritten`，临时目录逐文件 SHA-256 核对 |
| 属性绑定、属性目录、物种映射、词表、模型身份、依赖或模型文件篡改：加载失败 | 通过；`test_s2_rejects_rebound_package` 各参数及 `test_s2_package_roundtrip_and_tampering`。词表篡改由模型文件哈希拒绝；目录内容篡改测试重算文件哈希后仍被内容绑定拒绝。均使用临时包 |
| 未知正含量物种：正式值不可用并给出原因 | 通过；`test_enhanced_prediction_boundaries`、`test_package_roundtrip_and_failures` |
| 未知物种零含量：结果与原输入一致 | F1、F2 均通过；`test_enhanced_prediction_boundaries` |
| 越界工况给 caution；非法或非有限输入给 invalid_input | 通过；`test_enhanced_prediction_boundaries`，包括负温度、NaN 和 Infinity |
| 输出大于 100、NaN 或 Infinity：正式值为空，有限越界原始值保留，JSON 无非有限数 | 通过；`test_enhanced_prediction_boundaries`、`test_package_roundtrip_and_failures`。使用隔离常量模型注入 |
| 合法、空对象、未知物种、零项、越界及非对象混合批次：保留条数、顺序及逐项结果 | F1、F2 均通过；`test_enhanced_prediction_boundaries` |
| 历史 R1 包及固定 47 条输入重放 | 新进程重放结果与历史 JSON 全部相等；[重放结果](../artifacts/reports/s3-02-20261118-02b/historical-replay.json)，原包未修改 |

[pytest 原始日志](../artifacts/reports/s3-02-20261118-02b/pytest.log)及 [JUnit 结果](../artifacts/reports/s3-02-20261118-02b/pytest.xml)：31 项通过。失败路径测试使用合成训练数据和临时包，异常输出使用注入模型；这些证据与 02-A 的真实训练和预测分开。全量 pytest、Ruff 及受保护产物完整性核对属于后续 02-C。
