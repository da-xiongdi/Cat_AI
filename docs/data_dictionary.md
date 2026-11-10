# 数据字典（schema_version=1）

可执行契约：`src/catalyst_ai/schemas/domain.py`；机器可读导出：`configs/data_schema.yaml`，通过 `python scripts/generate_schema.py` 重建。额外未知字段一律拒绝，防止拼写错误静默丢弃。ID 为非空、不含空白的字符串，应包含来源命名空间；不会从名称推断 ID。

## 导入粒度与 CSV 列

JSON 顶层为记录数组。每个记录包含一个配方、一个合成批次、一个测试工况以及一个或多个观测。

CSV 为 UTF-8（允许 BOM），首行为以下九个**唯一**列名，顺序不限：

```text
schema_version,dataset_kind,source,extraction,recipe,synthesis,test,observations,characterizations
```

前两列为普通字符串，其余七列为合法 JSON 对象/数组/null 文本，CSV 双引号按标准转义。每个物理行范围记录为 `lines:start-end`，JSON 项记录为 `$[index]`；它们与文献内的页表定位分别保存。示例见 `data/examples/synthetic_demo.csv` 和同名 JSON。JSON 重复键、非有限常量、CSV 重复/缺失/多余列均拒绝；局部单元格解析失败可保留原行到 staged。

| 顶层字段 | 类型/默认 | 含义 |
|---|---|---|
| schema_version | `"1"` | 当前唯一支持版本，CSV 必填列 |
| dataset_kind | `synthetic_demo / research`，必填 | 演示与研究身份标记，research 不代表已经核验 |
| source | SourceDocument 或 null | 缺失保留并产生 block |
| extraction | ExtractionRecord 或 null | 来源内定位与抽取证据；缺失产生 block |
| recipe / synthesis / test | 对象，必填 | 关系 ID 必须一致 |
| observations | Observation[]，至少1项 | ID 不得重复；多个时间点使用独立 observation_id |
| characterizations | Characterization[]，默认空 | 独立的制备后表征，无设计输入混用 |

## 通用数值 Measurement

| 字段 | 类型/默认 | 规则 |
|---|---|---|
| raw_value | string/null，默认null | 保留原文文本与小数位；JSON 数字不自动转字符串 |
| raw_unit | string/null | `%`、`degC`、`°C`、`K`、`MPa` 等；无量纲显式写 `1` |
| state | ValueState，默认not_reported | 见下表，不从空值或 NA 自动猜测 |
| normalized_value / normalized_unit | float/string 或null | 治理服务生成；导入文件里的标准值会被清除并按原值重新检查 |
| definition | string/null | 指标计量口径；如碳基选择性、进出口转化率定义、STY分母 |
| source_locator | extraction_id/null | 已报告原值必须指向本条 extraction_record |
| extraction_status | pending/verified/rejected，默认pending | 输入不能自授核验；有效人工状态在 review_event 中 |
| quality_flags | string[]，默认空 | 由治理重建的字段级质量代码；记录级问题另在 staged.issues |
| uncertainty | string/null | 原文误差/区间说明，不自动解释成标准差 |
| provenance | string→string，默认空 | 额外抽取背景、转换/原文细分定位等；不替代强制来源关联 |

| state | 原值要求 | 语义 |
|---|---|---|
| reported | 非null有限数值文本 | 明确报告的非零值 |
| zero | 非null且数值确为0 | 真零，可写 `0.00`，不是缺失 |
| unknown | null | 未知 |
| not_reported | null | 未报告 |
| not_applicable | null | 不适用 |
| not_measured | null | 未测 |
| invalid | 可为原文或null | 无效原文保留，block，不赋标准值 |

`reported/zero` 的非数值、NaN、Infinity、约数或范围文本触发 block；不会选中点、填零或推测单位。可选字段缺失产生 warning；关键工况/百分比闭合所需数据缺失产生 block。

## 来源与抽取

| 实体 | 字段 | 语义 |
|---|---|---|
| SourceDocument | source_id | 文档/内部资料唯一 ID |
| | kind | literature/internal；与演示标记独立 |
| | title | 原始标题或内部记录名称，必填 |
| | doi / year / internal_reference | DOI、1800–2200年份、内部实验/资料编号，可缺；内部来源必须有编号才可治理通过 |
| | license / access | 默认unknown/unspecified；保留授权与访问范围，软件不代替法律或机构审批 |
| | file_sha256 | 可选64位小写 SHA256，指源文献附件；与导入 CSV/JSON 文件哈希不同 |
| ExtractionRecord | extraction_id / source_id | 抽取 ID、来源外键 |
| | locator | 原文页/表/图/附件/内部记录定位，必填；不是导入文件行号 |
| | method / method_version | 人工/PDF/OCR/LLM等抽取方式及版本，必填 |
| | original_excerpt | 可选原文片段，遵循原文件权限 |
| | status | pending 默认；有效审核另记事件，不覆写原抽取 |

## 配方与合成（A层）

| 实体 | 字段 | 语义 |
|---|---|---|
| Recipe | recipe_id / material_family | 唯一名义配方 ID、开放体系标签；非固定CZA枚举 |
| | composition_basis | wt_pct/mol_pct/atomic_pct/ratio/unknown |
| | composition_scope | 百分数所覆盖对象，如全部金属/全部氧化物；百分数须明确范围 |
| | components | Component[]，非空；species开放字符串，role为element/compound/support/promoter/gas，amount为Measurement |
| | supports / promoters | string[]，默认空；名称标签，定量含量仍在components |
| SynthesisRun | synthesis_id / recipe_id | 实际制备批次 ID、配方外键 |
| | route / precursors / batch_label | 制备路线、前驱体列表、批号；缺失不补齐 |
| | steps | 按原文顺序的 SynthesisStep[] |
| SynthesisStep | name / parameters / atmosphere | 步骤名称；参数名→Measurement（pH、温度、时间、升温速率等）；可选气氛说明 |

表征字段不能塞进 recipe/synthesis 作为任意额外字段。未知工艺步骤参数保留原值，当前仅识别部分基础单位，不自动建立可合成性结论。

## 测试工况（B层）

| 字段 | 类型/规则 |
|---|---|
| test_id / synthesis_id | 测试唯一 ID / 实际制备批次外键 |
| reactor | 可选反应器说明 |
| temperature | Measurement；支持 degC、°C、K → K，必须大于0 K |
| pressure / pressure_type | Measurement；absolute/gauge/unknown；仅明确absolute支持 Pa/kPa/MPa/bar → bar(abs)，须大于0 |
| ghsv | Measurement；h^-1 或1/h，只识别单位，不跨参考状态/体积基准换算 |
| ghsv_basis | GHSVBasis/null；须结构完整才赋GHSV标准值 |
| ghsv_basis.reference_temperature | Measurement，支持T单位规范，须大于0 K |
| ghsv_basis.reference_pressure / reference_pressure_type | Measurement；须为明确绝压且单位支持，须大于0 |
| ghsv_basis.catalyst_volume_basis | packed_bed/catalyst_solid/unknown；unknown阻断 |
| ghsv_basis.description | 可选原文对体积/流量基准的补充说明 |
| feed_basis / feed | mol_pct/vol_pct/ratio/unknown；Component[]，role必须gas，按对应基准检查 |
| catalyst_mass | Measurement，默认not_reported |
| dilution | 可选原文稀释信息 |
| stabilization_time / time_on_stream | Measurement，默认not_reported |

不把不同测试点转换到统一温压，不进行参考状态重算。工况 ID 不随配方合并。比例基准必须使用无量纲数且非负、总量大于0，仅 warning 提示无法执行百分数闭合；unknown基准为block。

## 性能与表征（目标/C层）

| 实体 | 字段 | 语义 |
|---|---|---|
| Observation | observation_id / test_id | 指标观测 ID、测试外键 |
| | metric | 开放字符串；首批约定co2_conversion、methanol_selectivity、methanol_yield、methanol_sty |
| | value | Measurement；必须记录指标定义，前三个指标单位要求%；任何百分数均检查[0,100] |
| | time_on_stream / carbon_balance | Measurement，默认not_reported；不把缺失碳平衡当作100% |
| Characterization | characterization_id / synthesis_id | 表征唯一 ID、制备批次外键 |
| | technique / properties / conditions | 技术名称；性质名→Measurement；可选测量条件 |

STY仅识别明确的 `g_MeOH/g_cat/h`，其他STY单位/基准产生block并保留原文。输入已有收率/STY可以保存，但不会从其他观测推算。通用已识别原单位还包括 `1`、`g`、`h`、`min`、`nm`、`m2/g`，不代表这些单位在任意字段均有物理合理性；细分合成/表征维度校验仍待扩展。

## 存储、质量、核验与批次

| 表/对象 | 字段/用途 |
|---|---|
| import_run | id、created_at、input_name/sha256、metadata_json、report；一次导入事件 |
| staged_record | id、run_id、input_locator、fingerprint、dataset_kind、status、raw_payload、payload、issues；所有行的原始/治理档案 |
| curated_record | id（关联staged）、source/extraction/recipe/synthesis/test外键、dataset_kind、review_status |
| Issue | code、severity（warning/block）、path、message；字段与整记录问题 |
| review_event | id、record_id、reviewer、decision、evidence、created_at、payload_sha256、metadata_json；追加审核历史，整条记录范围 |
| dataset_snapshot | id、created_at、content_sha256、manifest；内容哈希命名、不可覆盖的冻结证据 |
| ExperimentBatch | capacity默认4、整数范围1–6；candidate_ids唯一且数量不得超容量；仅契约，未建真实批次状态机 |

记录 status 为 staged/curated/duplicate；核验为 pending/verified/rejected，两者不能混同。所有正常/违规记录均可追溯 run_id + 行范围/JSON索引 + 输入文件哈希；正常实体另有外键。精确重复依据原始结构化输入指纹；相同实体ID不同内容为conflict；已有观测ID相同内容也不得通过变更包装重复计数。

## 主要规则代码

| 代码 | 级别与处理 |
|---|---|
| schema_invalid | block，保留坏行；不能创建领域实体 |
| source_missing / locator_missing / value_locator_missing / value_locator_mismatch | block，缺证据不可准入 |
| source_identifier_incomplete | 文献缺DOI为warning；内部缺编号为block |
| license_unknown | warning，需人工审计权限 |
| untrusted_review | block，输入不能自授核验 |
| invalid_number / zero_state_mismatch / value_invalid | block，保留原值 |
| value_unknown / value_not_reported / value_not_applicable / value_not_measured | warning，关键字段另有block |
| critical_value_missing / unit_unknown / physical_range / numeric_overflow | block，不赋错误标准值 |
| pressure_basis_unknown / ghsv_basis_unknown | block，禁止猜测 |
| percentage_range / closure_failed / closure_incomplete | block，不自动归一化 |
| composition_missing / composition_scope_missing / duplicate_component / feed_role_invalid | block，须核查组成定义 |
| negative_composition / ratio_incomplete / ratio_zero_total | block，比例也须合法 |
| closure_not_assessable | 未知基准block；合法比例warning |
| metric_definition_missing / metric_unit_unknown / sty_basis_unknown / negative_performance | block，口径待确认 |
| duplicate_record / duplicate_observation / entity_conflict | block，保留事件，不覆盖或重复计数 |
| source_kind_mismatch | block，与CLI来源类型不符 |
| imported_normalization_ignored / unit_not_normalized | warning，重算受支持值/保留未支持原值 |

规则阈值在 Settings 和 `configs/project.yaml` 中；其他规则固定于治理版本1。没有宣称自动检测所有极端值、同源复制、机理合理性或全部材料化学约束。

## TheMeCat 补充语义（2026-11-10，未变更 schema_version=1）

25 列的完整映射、数据集级定义证据及拟升级字段见 [TheMeCat 实施方案](themecat_implementation_plan.md)。当前契约仍只支持体积 GHSV；材料 mol%/质量归一流量/反应物比值的 v2 支持尚未实现。特别注意：`starting_material_*` 是来源给出的活性组分初始/还原前材料，不当然是实际合成投料前驱体；历史适配器保留原值但其 synthesis.precursors 映射待版本化修正。本文其余表格描述当前可执行契约，不因补充资料而静默改变。
