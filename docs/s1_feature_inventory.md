# S1 特征数据需求清单

本清单依据 `feature_engineering_plan_v0.1.md` 第 2、4 节整理；它是需求清点，不表示外部数据已核实或导入。原催化剂事实仍由治理、资格和快照链提供，属性导入不改变其证据状态。

| 项目 | 类型 | 定义及单位 | 关联键、来源或版本 | 阶段与缺失策略 |
|---|---|---|---|---|
| 完整组成 | existing_field | 来源角色、物种及全催化剂材料 mol%；总和容差 0.5 个百分点 | 父 snapshot_id、record_id；保留来源角色 | R1/R2；身份、角色、含量、范围或闭合不合法时排除，不归一化 |
| temperature_k | existing_field | 温度，K | 父快照及记录 | R1/R2；须有限且大于零，否则排除 |
| pressure_bar_abs | existing_field | 绝压，bar(abs) | 父快照及记录；保留来源压力假设 | R1/R2；须有限且大于零，否则排除 |
| h2_co2_ratio | existing_field | H₂/CO₂ 摩尔比，无量纲 | 父快照及记录 | R1/R2；须有限且大于零，否则排除 |
| reactants_flow_nl_g_h | existing_field | 催化剂质量归一反应物体积流量，NL/(g·h)，293.15 K、1.01325 bar(abs) | 父快照及记录；reactants_only、催化剂质量基准 | R1/R2；基准不明或值无效时排除，不猜测 |
| Pauling 电负性 | imported_property | 元素的 Pauling 电负性，无量纲 | 元素、属性定义、来源及版本；需原件哈希、许可和证据 | R2；缺失或未核实则不支持，禁止补造 |
| 共价半径 | imported_property | 同一来源体系的元素共价半径，pm | 元素、属性定义、来源及版本；需原件哈希、许可和证据 | R2；缺失或未核实则不支持，禁止混用体系 |
| 物种中心计数 | imported_property | 显式物种到中心元素及计数的白名单映射 | 物种、映射版本及证据 | R2；不定比、别名或语义未确认标为 unsupported，不靠通用解析器推断 |
| 角色属性均值、含量和差值 | computed_feature | 按方案第 4 节以材料 mol% 和中心元素数计权 | 父快照、记录、属性及映射版本、计算版本和输入哈希 | S1-B/R2；缺角色为 not_applicable，缺必需属性或映射则排除 |
| 特征构建和筛选 | computed_feature | 固定规则生成特征与保留/排除清单 | 父快照、资格、划分、属性及映射版本、规则和实现身份 | S1-B；不修改原快照，筛选继承 DOI 分区 |

属性和映射必须先核实来源、许可、单位、版本及原件哈希，经 dry-run 和冲突检查后入库；未知和不适用状态不能写成物性事实零值。已有 R1 输入完整性检查位于 `src/catalyst_ai/features/pipeline.py`，其存在不代表 R2 物化数据或 S1-A 已交付。

## 当前快照物种清点

对 `snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da` 的 593 条记录运行现有 R1 `project` 输入检查，593 条通过，存在 31 种正含量物种：Al2O3、Au、BaCO3、Ca、CeO2、Co3O4、CoGaAlO4、Cr2O3、Cu、Fe3O4、Ga2O3、In2O3、InNi3O0.5、Ir、K、K2CO3、La2O3、LaMn0.1Cu0.9O3、LaMn0.3Cu0.7O3、LaMn0.5Cu0.5O3、LaMn0.7Cu0.3O3、LaMnO3、MgO、Pd、Pt、SiO2、TiO2、Y2O3、Zn、ZnO、ZrO2。此清点并非中心计数审核，也不表明属性覆盖或 R2 支持率；实际构建时须重新校验快照身份和输入。

## 实际数据和覆盖

2026-11-13 将固定提交 `bd4716bff94c7acf22210d6ffb75dbd1fcc4f9bc` 的 [mendeleev](https://github.com/lmmentel/mendeleev) 元素库原件按 SHA-256 `8a6312b57603e22c58ab28005bb8cacfbff721bc859eea8ddc2b784c17ffd717` 留存在 `data/raw/`，提取 `en_pauling` 和 `covalent_radius_cordero`（pm）至 `configs/s1_element_properties.json`。共价半径体系参见 [Cordero 等](https://doi.org/10.1039/B801115J)。上游代码为 MIT 许可（Copyright 2015 Lukasz Mentel），不据此断言各原始数据的再分发许可；证据包保留来源链接，进一步发布前需核查。属性目录 SHA-256 为 `3eb444053285eaffab371d9df2e289cce54562edc95d291bad62d26a8c7b3f8f`。

`configs/s1_species_mapping.json` 对单元素及简单定比氧化物、碳酸盐按方案显式登记中心计数；复合和非整数计量式保守标为 unsupported。该映射是规则性初始登记，不等同逐条核实原始文献语义，SHA-256 为 `b52593f00277489f6289562dfa71ed973746573c728fe30310bb51bed40e3784`。两个目录 dry-run 后已入库，旧库 `integrity_check` 返回 ok。

`artifacts/reports/s1-a-coverage-v1.json` 对上述快照逐记录检查：593 条中 548 条可被当前属性及映射覆盖，45 条不支持；其中 `InNi3O0.5` 39 条，其余六种复合式各 1 条。此数值是当前规则下的输入覆盖，不代表模型结果、已完成的 S1-B 特征计算或材料科学验证。

后续范围（2026-11-13确认，尚未实施）：按[特征方案第2.5节](feature_engineering_plan_v0.1.md#25-s1-a补充复合物种解析与来源歧义核查)优先核查上述39条记录，再登记有证据支持的多中心和小数计量映射。当前v1的保守拒绝记录不追溯改写，`InNi3C0.5`仅是待核查更正线索；新版本分开报告解析、来源语义和正式资格，不能将覆盖改善表述为已完成原文核验或特征计算。

来源核查进展：39 条记录均关联 DOI `10.1016/j.fuel.2024.131111`，数据集样品名含 `InNi3C0.5`；[论文出版方页面](https://www.sciencedirect.com/science/article/abs/pii/S0016236124002576)的标题和摘要也使用该式。已固定[逐记录候选清单](../artifacts/reports/s1-a-source-candidates-v1.json)，并留存 Crossref 书目元数据原件及哈希。书目标题不等于论文全文，也不足以确认每条样品的组成比例、角色和测试对应关系；39 条仍全部为 pending，未更正事实或创建新快照。生成脚本为 `scripts/s1_a_source_candidates.py`。多中心物种审核、分层覆盖和正式资格仍未完成。


## S1-A收尾状态（2026-11-13）

本轮收尾已完成，[验收说明](s1_a_acceptance.md)为当前状态依据，以上v1及pending描述保留历史语境。新属性版本来自专用mendeleev-data仓库的固定提交与MIT分发证据，236项值/状态与v1一致，详见[许可核查](s1_license_review.md)。多中心/小数计量v2登记5种LaMn/Cu明确名义配方；来源按数据集接受，不称为逐行原文核验。

39条InNi3O0.5已全部登记evidence_insufficient终态处置，保留InNi3C0.5候选，不自动更正；CoGaAlO4另1条证据不足。正式资格553/593条、29/31种物种，较v1新增5条。逐记录处置、分层覆盖、分母、差异和保护检查已保存；S1-B实际特征计算仍待实施。
