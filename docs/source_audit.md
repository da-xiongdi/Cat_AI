# 工作区与证据审计

审计日期：2026-11-09（Asia/Shanghai）。在创建代码前实际读取工作区文件清单。

| 项目 | 初始事实 |
|---|---|
| 指定 `docs/project_development_guide.md` | 初始不存在；读取失败后查找实际指引 |
| 实际文件 | `docs/architecture/AI_CO2_MeOH_Catalyst_Development_Guide_v0.2.md`，已完整阅读 |
| 原有代码、测试、配置、数据库、模型、实验附件 | 均未发现 |
| Git | 初始不是 Git 仓库；本轮未擅自创建提交/远端 |
| Python | 默认 Anaconda Python 3.8.8；不满足 ≥3.11 |
| 可用环境 | uv 0.10.12；已安装 CPython 3.14.3，实际用于 `.venv` |

基准原件与约定路径副本 SHA256 相同：

`64ba32d98cdfd4778cef1158f597e2179376c380ee3a816314dd9c31664a757e`

原件没有修改。规范路径仅补齐原文副本；没有新增或扩大原指引的科研结论。

## 数据来源边界

未发现真实文献、自有实验原始数据或可导入的“200+催化剂”逐条证据。未接入 TheMeCat、其他公开数据集或仪器。未检查/推断任何外部数据集的授权、覆盖或质量。

`data/examples/synthetic_demo.csv` 与 `.json` 为 `scripts/generate_demo.py` 明确生成的同一条虚构记录；dataset_kind、来源标题、来源定位、抽取方法和制备说明都标记演示含义，无伪造 DOI。数值只用于检查结构、单位与治理，不代表该材料体系的真实表现。

自动测试使用演示记录的副本，修改数值来触发缺失/冲突/边界条件。快照成功路径只测试显式 demo 模式，产物仍为 synthetic_demo、scientific_use=false；没有把测试数据伪装成核验后的真实研究数据。

## 真实数据接入前待办

取得原始文献/补充信息或内部实验文件；核实来源及使用授权；建立稳定 source/recipe/synthesis/test/observation ID；逐项确认组成基准、合成步骤、压力类型、GHSV参考温压及体积基准、指标定义与定位；由实际复核人记录证据。当前软件不自动判定授权有效性，也不替代科学复核。
