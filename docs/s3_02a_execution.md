# S3-02 之 02-A 执行记录

02-A 的默认包、自定义训练、增强特征与历史包重放已完成；本记录不代表 02-B/C/D 或 S3-02 整体验收完成。自定义运行仅验证功能，不参与 S3-01 默认候选比较。

| 场景 | 运行 | 包与结果 |
|---|---|---|
| 正式 R2 | `artifacts/runs/s3-20261118-01/r2` | `artifacts/models/s3-20261118-01/r2`，F_base/extra_trees |
| 正式 R1 对照 | `artifacts/runs/s3-20261118-01/r1` | `artifacts/models/s3-20261118-01/r1`，F_base/extra_trees |
| F1 增强 | 正式 R2 运行 | `artifacts/models/s3-20261118-01/r2-f1-ridge`，F1/ridge |
| 多模型 CLI | `artifacts/runs/s3-20261118-02a/multi` | `artifacts/models/s3-20261118-02a/multi`，自动选择 F2/extra_trees，显式打包 F2/ridge（alpha=2） |
| 单模型 Python | `artifacts/runs/s3-20261118-02a/single` | `artifacts/models/s3-20261118-02a/single`，F2/ridge（alpha=3） |
| 保存/重载对照 | `artifacts/runs/s3-20261118-02a/single-reload` | `artifacts/models/s3-20261118-02a/single-reload`，独立训练 F2/ridge（alpha=3） |
| 历史 R1 | 既有固定运行 | `artifacts/models/themecat-r1-prediction-20261112-final`，原 47 条 JSON 重放完全一致 |

[场景矩阵](../artifacts/reports/s3-02-20261118-02a/scenarios.json)保存模型身份、选择、实际参数及路径。各场景包的 report 哈希与对应训练报告匹配；五组各 47 条 validation 记录的输入和报告行、包预测保存在同目录的 `*-input.json` 和 `*-checks.json`。单条及批量 Python 预测一致，CLI 新进程单条和批量结果与 Python 一致；可用的报告原始值与包结果按相对和绝对容差 1e-12 比较。

[逐条状态核对](../artifacts/reports/s3-02-20261118-02a/supplement-checks.json)检查状态、正式值、原始值、未见物种、越界工况和不可用原因。报告对不支持物种仍计算诊断值，可能额外标记诊断输出越界；入口在转换不支持时停止，返回 `unsupported_species_role`，正式值和原始值均为空。报告中的诊断原始值不被误认为入口预测。

[重载前后逐条证据](../artifacts/reports/s3-02-20261118-02a/single-reload-checks.json)比较独立 Python 训练的内存拟合对象与保存后重新加载的包，47 条结果完全相同。[增强边界和拟合参数](../artifacts/reports/s3-02-20261118-02a/boundary-and-parameters.json)记录 F1/F2 的未知物种、零含量项及越界工况；另一次独立多模型运行检查两个拟合对象的实际参数（Ridge alpha=2，ExtraTrees 80 棵、n_jobs=1）。该复跑用于参数核实，不替代原 CLI 运行。

本步脚本的 Ruff 检查及格式检查通过。02-B 的完整失败路径与 02-C 的全量测试、受保护文件哈希核对仍待后续执行。
