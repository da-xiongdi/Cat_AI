# S4-03 划分协议与训练接入验收

2026-11-20（Asia/Shanghai）。本任务固定划分与实验入口；未开展 S4-04 正式模型对照。所有划分均为既有 TheMeCat 数据上的内部评估，不能解释为外部验证。

## 固定划分与铜基门槛

全体系共同资格 542 条、铜基共同资格 211 条。以种子 42、43、44 固定九份清单：[清单、覆盖及配置](../artifacts/reports/s4-03-frozen-20261120-v2/coverage.json)。测试比例目标为 20%，按不可拆分组尽量接近记录数，DOI 大组使实际比例不同。五折只在训练集内生成。

| 种子 | EXP-01 DOI 训练／测试 | EXP-02 随机训练／测试 | EXP-03 铜基训练／测试 | 铜基训练／测试 DOI |
|---|---|---|---|---|
| 42 | 432／110 | 434／108 | 181／30 | 15／12 |
| 43 | 438／104 | 434／108 | 170／41 | 16／11 |
| 44 | 434／108 | 434／108 | 166／45 | 16／13 |

三个种子铜基训练及测试的独立分配单元数分别等于对应记录数，均达到训练至少 100 条、5 个单元及测试至少 20 条、20 个单元的探索性门槛。EXP-03 的训练、测试及各内折是 EXP-02 的铜基投影；测试成员一致。完整 DOI、组成及四项工况范围见覆盖文件。来源仍较集中，组成签名不代表合成批次；S4-01 未排尽潜在未知重复。无已确认保留的重复组，合成测试验证重复组跨 DOI 连通与分区隔离。阈值不是统计功效保证。

## 配置和执行

配置 [计划示例](../configs/research_plan_example.json) 的种子、比例、折数、候选特征与模型、超参数、指标及输出；`dataset` 和 `strategy` 可指定遵循现有版本化视图／台账／快照契约的数据及随机或 DOI 策略。当前实际验证使用 S4-02 CO₂ 转化率和现有 F_cond、F_base、F1、F2、Dummy、Ridge、Extra Trees。其他目标及数据版本需有兼容的资格、特征目录和目标定义，不能由本验收推断其已验证。

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python.exe scripts/configure_research_experiments.py configs/research_plan_example.json --output NEW_PLAN_DIR
.venv/Scripts/python.exe scripts/run_research_experiment.py preflight CONFIG --output NEW_RUN_DIR
.venv/Scripts/python.exe scripts/run_research_experiment.py train CONFIG --output NEW_RUN_DIR
.venv/Scripts/python.exe scripts/run_research_experiment.py train-batch CONFIG_DIR --output NEW_BATCH_DIR
.venv/Scripts/python.exe scripts/run_research_experiment.py score RUN_DIR
```

预检检查源和视图哈希、特征目录、划分及分组隔离；训练在折内拟合预处理，以训练 OOF MAE 选模型并在训练集重拟合，不评分测试集。评分单独调用并核验锁定的代码、环境、输入与模型；失败保留日志，可显式 `score RUN_DIR --retry`，成功后禁止同一运行再次评分。训练保存配置、清单、逐条及逐折交叉验证、模型、日志及依赖版本；评分按配置输出逐条预测、MAE/RMSE/R²、可用率及实测预测、残差和误差分布图，附产物哈希。`predict_payloads` 可对现有领域 payload 使用可信研究包，状态为 `ok` 或 `caution` 的诊断预测才计为可用。Python pickle 仅允许来自可信来源的包。

## 验证和边界

[验证报告](../artifacts/reports/s4-03-verification-20261120-v5/verification.json)及 [测试日志](../artifacts/reports/s4-03-verification-20261120-v5/pytest.log)记录 26 项测试通过、九份固定配置预检、覆盖内容重放和历史 R1/R2 模型加载预测。隔离小视图实际走完随机与 DOI 的预检、训练、模型重载、评分，以及重放与失败重试；使用 Dummy 算法，属于功能测试。历史划分及初稿未覆盖。

运行由本地脚本和模块提供，后续 WB-07 应直接复用这些接口。模型选择以记录等权 OOF MAE 为固定口径；用户可选择输出指标，尚不支持更换选择指标或自动超参数搜索。新来源和其他目标需要各自的治理、特征资格与端到端验证。图表为基础 SVG；不构成模型解释或可靠性校准。
