# Yan et al. (2026) 论文与 CommsEng 仓库：架构评审及对当前项目的增量建议

> 2026-11-09；类型：研究与公开代码评审；作为本项目开发指引 v0.2 的**增补**，不是已有功能或科研成果证明。
>
> 论文：Yan, M. et al., *Communications Engineering* (2026), DOI https://doi.org/10.1038/s44172-026-00706-4  
> 仓库：https://github.com/MoYan-101/CommsEng  
> 评审依据：用户提供的论文全文，以及 2026-11-09 在线可访问的 README、配置、核心训练/数据加载/切分/推理/评价脚本。未在本地克隆运行仓库，因而以下均非执行成功或性能复现的证明。

> 实施衔接：原任务路线与现有架构继续沿用。下文为评审建议，结合当前实现后的任务映射、适用边界及验收要求见[实施与验收清单](implementation_amendment.md)；目录图不作为重构要求。

## 1. 简要结论

论文的**科学数据治理—特征工程—多模型比较—可解释推断—实验假设检验**值得高度借鉴；仓库的**按功能划分代码、YAML配置驱动、run_id隔离产物、训练与推理分离**值得选择性吸收。但仓库更接近固定Cu/ZnO研究场景的论文复现/分析工作流，不能直接充当本项目面向多材料体系、可溯源数据积累、候选配方推荐与实验闭环的长期平台底座。

建议 **保留当前 v0.2 的模块化单体、实体数据模型与分期建设路线**，并将论文相关思想落入数据质量、独立验证及实验闭环规划；另设 `reproductions/yan2026/` 隔离复现仓库，切忌复制代码后将其当作核心域模型。

## 2. 论文可直接借鉴的研究内容

1. **输入/输出同时建模**：将催化剂性质、合成方法、反应工况作为不同的输入维度；将CO₂转化率、甲醇选择性、CO选择性与STY作为输出。作者使用Cu/ZnO体系的13类输入特征和4个输出，不意味着我们的平台必须固定13+4。
2. **文献数据精细整理**：作者从200篇文献提取2551条初始记录，保留2476条，再处理助剂顺序对称性等问题形成2383条建模记录；数据集还额外衍生940个表观活化能数据点。要把抽取证据、单位规范、冲突处理、缺失状态、派生公式及记录删除原因做成可审计的模块。
3. **材料化学编码**：可以引入 Magpie/matminer/pymatgen 元素统计描述符；应保存特征生成的版本与可用性，支持任意元素/助剂数，而非写死 Promoter 1/2 两列。对于助剂组合，建立排列不变的 `composition_signature`，不依赖字段排列顺序。
4. **模型基线与优化**：RF、CatBoost、XGB等不同家族模型比较，加Optuna可追溯调参；报告误差、残差、泛化能力。先做一项可复现目标，再扩展多输出和多目标推荐。
5. **SHAP驱动科学假设**：SHAP及响应面用于找候选操作窗口、指导有针对性的实验；不能把后验解释当作因果证明。
6. **科研侧辅助分支**：对可形成等条件温度序列的记录，后续可以支持 `kinetics/eapp.py` 拟合表观活化能，明确压力、进料、空速及线性温区；表观活化能不同于单一步骤内禀能垒，先不要纳入第一阶段MVP。

### 论文结论的使用边界

- 论文CatBoost在随机验证集上的R²（CO选择性0.843、甲醇选择性0.864、STY 0.832、CO₂转化率0.737，α=0.01）只应视为该数据与切分方案的结果；不能当成跨论文/跨新材料外推的验收标杆。
- 论文的GHSV–Eapp关系用1 bar下的Cu/ZnO/Al₂O₃独立实验提供了支持，不能推广为所有材料/压力下的必然关系。
- 不要混淆两种贝叶斯优化：**超参数优化**（选择RF/CatBoost等模型的参数）与**候选催化剂贝叶斯优化**（选择下一批实验配方），属于不同研发模块。

## 3. GitHub仓库已核查的结构与优点

根目录可见：`configs/`、`data/`、`data_preprocessing/`、`evaluation/`、`losses/`、`models/`、`trainers/`、`slurm/`，以及 `train.py`、`inference.py`、`visualization.py`、`run.sh`、`requirements.txt`。

- `configs/config.yaml` 是配置中心，指定数据、预处理、六类模型、Optuna、推理与图表。
- `run.sh` 依次执行 `train.py`、`inference.py`、`visualization.py`，支持不同正则/过拟合惩罚系数的批量运行；脚本以Bash/Conda/Linux工具为主，而用户主开发环境是 Windows VS Code。
- `models/` 与 `trainers/` 解耦模型定义和训练器；`evaluation/` 独立评价；`inference.py` 从保存的模型和转换器中执行2D/3D网格推理与分类组合响应矩阵。
- 产物按 `模型/数据名/run_id` 存储，训练侧会保存config snapshot；支持多次实验结果比对。

## 4. 不建议直接沿用的具体实现

| 发现 | 公开代码线索 | 我们的处理 |
|---|---|---|
| 依赖固定的Cu/ZnO字段和助剂槽位 | `config.yaml` 的 `input_len: 13`, `output_len: 4`、`Promoter 1/2`、`Molar ratio (Zn:Cu)` | 使用通用的组分明细表、可变数量的助剂、材料家族插件与任务配置 |
| 随机训练/验证划分、普通KFold交叉验证 | `data_preprocessing/data_split.py` 使用 `train_test_split`；`train.py` 使用 `KFold(...shuffle=True)` | `GroupShuffleSplit`/`GroupKFold` 按论文、配方或合成批次分组；跨材料家族单独报告 |
| 输入缺失处理在划分前完成，有训练-验证信息共享风险 | `train.py` 在 `split_data` 前调用 `load_smart_data_simple`；数据加载器内调用KDE和全表填补 | 先按组划分原始记录，再在训练折上拟合填补、编码、缩放，验证折只transform；最好使用sklearn Pipeline |
| 缺失输出值直接填充为均值 | `data_loader_modified.py` 将每个Y列NaN替换为整列均值 | **禁止把缺失标签当实测值**；逐目标过滤无标签记录，或开发有明确定义的masked multi-task损失和标记 |
| Optuna与KFold基于同一整体数据，CV指标并非完全独立的外部评估 | `train.py` 先使用全体数据调参，再做普通KFold | 采用独立外部组别留出集或嵌套分组CV；留出集不得参与特征拟合或参数搜索 |
| 模型推断主打响应面/热图 | `inference.py` 的 `heatmap_2d_inference`、`heatmap_3d_inference` | 将 `what-if response surface` 与 `candidate screening + constraints + uncertainty` 分成不同模块 |
| 公开数据完整性仍需核实 | README要求联系作者获取 complete dataset；`config.yaml` 指向的 `data/Main_20260128_cleansed.csv` 在线直接访问返回404 | 先获取并检查实际训练CSV、补充数据、字段定义及许可证；未经核查不声称已复现论文 |
| 依赖版本未锁定，缺少明确的项目部署/验收契约 | `requirements.txt` 为无版本号依赖；仓库根目录清单未见测试目录 | `pyproject.toml` + 锁文件、`pytest`、`ruff`、GitHub Actions或本地质量门禁；不照搬 `run.sh` 为Windows主入口 |
| 代码使用许可不明 | 根目录公开清单未看到 LICENSE；论文CC BY 4.0不等于自动授予仓库全部代码的复用许可 | 保留仓库引用；确认代码许可前，以重写功能/学习设计为主，不直接大规模拷贝实现 |

上述为**代码审阅发现与潜在风险**，未进行复现实验，不将其表述为已证实的论文结果失真。

## 5. 建议的项目架构：v0.2基础上增加四个明确边界

```text
ai-methanol-catalyst/
├── src/catalyst_ai/
│   ├── domain/                  # 通用数据实体: source, recipe, synthesis, test, observation
│   ├── ingestion/               # 文献/自有数据导入、证据抽取、人审任务
│   ├── governance/              # 单位、基准、缺失状态、矛盾、重复、质控
│   ├── features/                # 通用 composition / synthesis / conditions 编码
│   │   ├── composition.py       # 可变数量元素/助剂；排列不变
│   │   ├── synthesis.py
│   │   ├── operating.py
│   │   └── characterization.py
│   ├── datasets/                # 不可变快照、分组划分、标签资格规则
│   ├── modeling/
│   │   ├── pipeline.py          # fit-on-train、transform-on-validation
│   │   ├── registry.py          # sklearn/CatBoost/XGB模型适配器
│   │   ├── tuning.py            # Optuna超参数优化，与设计优化分离
│   │   ├── evaluation.py        # 普通/按文献/按配方/跨材料家族验证
│   │   ├── explain.py           # SHAP + 适用性和共线性注记
│   │   └── uncertainty.py
│   ├── design/
│   │   ├── space.py             # 候选结构与工艺搜索空间
│   │   ├── constraints.py       # 可制备性/组成/设备/测试条件约束
│   │   ├── screening.py         # 预测结果+适用域+排序
│   │   └── acquisition.py       # 后续：主动学习、贝叶斯实验设计
│   ├── experiments/             # 4–6并行批次、结果导入、模型回灌
│   └── cli.py                   # Windows可直接使用 python -m catalyst_ai
├── configs/                    # dataset、task、model、screening YAML
├── data/                       # 原始只读 / normalized / snapshots
├── runs/                       # 每次运行的模型、数据哈希、配置、报告
├── tests/                      # 领域、质量、划分、无泄漏、推理、候选约束
├── docs/                       # 研究协议/字段字典/开发进度/变更记录
├── reproductions/yan2026/     # 仅复现实验：配置映射与独立环境（不得耦合主平台）
└── pyproject.toml
```

**四个新增/强化的不可跨越边界：**

1. **`domain` 与 `modeling`**：真实实验记录及来源为数据库事实；模型输入表只是由这些事实推导出的**版本化视图**。不能以建模CSV为唯一主数据。
2. **`datasets` 与 `modeling`**：先冻结数据及划分，再对训练折拟合所有数据依赖的预处理；测试折没有拟合权。
3. **`features` 与 `design`**：推荐新配方只能使用设计时可知的组成、合成计划及指定测试工况；制备后BET等表征只能进入诊断模型。
4. **`inference` 与 `recommendation`**：模型的高分预测不是实验建议；只有满足可合成、安全、测试设备、域内/域外、适用性和多目标条件的候选才能进入实验队列。

## 6. 对 VS Code/Codex 开发的增量任务清单（建议）

**P0：立刻增补到基础能力**

- `Observation`必须能追溯到 `source_id/recipe_id/synthesis_id/test_id`；当前项目通过既有实体关系追溯即可，无需复制所有上游ID字段。不同批次、工况或文献记录不自动视作独立催化剂。
- 每个数值区分原始值、单位、单位基准、计算口径、来源页/表/图、推导/插补/人工核验标记。
- `missing_target` 不转为均值；每个目标单独创建有效样本视图；缺失输入先标注缺失原因，再按数据策略填补。
- 把 `split_strategy` 作为正式配置（paper/recipe/synthesis/random仅用于对照），测试组不得进入训练，所有预处理只在训练折拟合。
- 助剂编码改为任意数量的组成明细，并测试助剂排列对预测特征不应产生人为差异。

**P1：模型阶段吸收仓库思路**

- 通过 `ModelAdapter` 比较Dummy、Ridge、RF、CatBoost、XGB，模型不用一次写完六种。
- 引入Optuna调参，但区分 train/validation/test，限制预算、记录trial与seed。
- 各run保存源数据快照hash、划分ID、features版本、模型配置、模型文件、SHAP图、误差指标与运行日志。
- 分别生成按论文分组、按催化剂分组的报告；补充目标值分布、外推/不确定性和域外提醒。
- 生成工况响应面时，保留其固定催化剂配方与合成路径的上下文；禁止无约束外推。

**P2：未来候选与实验闭环**

- 加入`DesignCandidate`和`ExperimentBatch`，配方、制备步骤、目标测试工况三者作为原子级建议记录；推荐批次不超过核定的4–6个实验槽位。
- 一批建议包括高预测性能、高信息增益、对照/重复样，并保存排序理由、版本、实际测量结果和更新前后性能对照。
- 再评估是否增添`kinetics/eapp.py`扩展，以支持实验假设而非仅追求R²。

## 7. Codex 增量执行指令（可复制）

```text
请以 docs/project_development_guide.md 为需求与科研边界基准，先阅读
docs/progress.md、docs/implementation_amendment.md 和本评审。
延续现有模块化单体和A–F路线，复用已实现的实体、治理、审核、存储与快照。

按实施清单I1→I2→I3→I4逐项推进，每次只选择一个切片；
下一次代码任务建议仅I1：目标资格视图与覆盖清单。
先明确输入、输出、失败行为和验收条件，再实现有针对性的边界测试。
保留既有快照严格语义；不伪造缺失标签，不以模拟数据报告科研效果。

完成后输出变更文件、实际测试结果与限制，并更新docs/progress.md，
区分规划、已实现、软件已验证和真实数据/科研已验证。
暂不开展目录重构、大规模Optuna、复杂前端、设备控制或无约束候选生成。
```

## 8. 来源检查与复现前必须确认

- GitHub README：完整数据需联系作者；不能仅凭论文“数据可用”就推定仓库内含全部CSV及元数据。
- 当前公开`configs/config.yaml`指向`data/Main_20260128_cleansed.csv`；在线读取该路径返回404，不代表仓库内绝无任何数据，应以实际文件清单与获授权数据核对。
- 此次没有执行代码测试、比对2383数据行或复现实验R²；若今后获得原始数据，先在隔离环境复现，再评估能迁移的模块。
- 论文是开放获取CC BY 4.0；代码的独立版权/软件许可应另外确认。
