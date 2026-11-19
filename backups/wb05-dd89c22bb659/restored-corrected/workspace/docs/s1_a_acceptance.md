# S1-A 收尾验收（2026-11-13）

S1-A数据准备与资格检查完成，可进入S1-B计算。工程验收使用既有公开数据集来源接受边界，不代表原文逐行核验、F1/F2已经计算或模型效果改善。

## 交付与证据

| 验收项 | 结果及证据 |
|---|---|
| 初始需求分类 | [需求清单](s1_feature_inventory.md)保留已有、导入、计算职责 |
| 属性来源和许可适用性 | [数据许可核查](s1_license_review.md)；固定数据仓库提交、原件和MIT声明，236项值/状态与v1逐项一致 |
| 多中心与小数计量 | [v2物种目录](../configs/s1_species_mapping_v2.json)登记La/Mn/Cu名义中心；完整元素计数与中心计数分开，公式单元不缩放；碳酸盐排除C/O中心，SiO2保留Si |
| 39条来源歧义 | [逐组分处置](../configs/s1_source_review_v2.json)全部为evidence_insufficient；保留候选InNi3C0.5，不生效更正；附父快照、记录/组分定位、角色、DOI、样品名、依据与原件哈希 |
| 额外保守隔离 | CoGaAlO4的1条记录可解析，但现有来源证据不足以确认对应样品；保持unsupported，未判定来源错误 |
| 迁移与持久化 | 原目录表追加规范化feature_catalog_entry及独立feature_evidence；原件与索引交叉核对，支持版本化属性/物种单项查询；审核证据与映射分开存储 |
| 幂等、冲突和回放 | dry-run→入库→重复导入；重复迁移；同版本异内容拒绝；索引篡改拒绝；旧v1覆盖重放一致；详见[首次验收](../artifacts/reports/s1-a-acceptance-20261113/acceptance.json)和[最终验收](../artifacts/reports/s1-a-acceptance-20261113-final/acceptance.json) |
| 分层覆盖 | [最终资格报告](../artifacts/reports/s1-a-acceptance-20261113-final/qualification.json)含逐记录/组分、唯一物种、DOI及原分区汇总，分母、角色缺席及排除原因分别记录 |
| 历史保护 | 验收中留存升级前SQLite备份；全部非feature事实表内容哈希、原件、目标/资格快照、原DOI划分、旧配置和v1覆盖报告均保持一致；SQLite完整性ok、外键错误0 |

## 实际覆盖

属性版本为`mendeleev-data-665935bc-pauling-cordero-v2`，映射版本为`themecat-centers-v2`，记录级处置版本为`s1-source-dispositions-v2`，资格规则为`s1-qualification-v2`。正式使用需同时绑定三类版本及哈希；仅调用旧coverage不能替代正式资格检查。

| 原分区 | 父记录数 | 联合支持 | 排除 | 父DOI数 | 全部记录支持的DOI数 |
|---|---:|---:|---:|---:|---:|
| train | 493 | 454 | 39 | 26 | 25 |
| validation | 47 | 47 | 0 | 6 | 6 |
| 历史test | 53 | 52 | 1 | 5 | 4 |
| 总计 | 593 | 553 | 40 | 37 | 35 |

593/593条、31/31种物种均可按当前有限平面式语法解析；正式来源/映射/两项属性的联合支持为553/593条（93.25%），29/31种物种。DOI“全部支持”的分子要求该论文全部记录均支持，不混用“至少一条支持”的分母。逐物种统计按其自身组分出现计数，某条记录其他物种不支持不会抹去该物种自身的支持状态。

与[v1](../artifacts/reports/s1-a-coverage-v1.json)相比新增5条LaMn/Cu系列记录，未移除原548条支持记录，见[差异清单](../artifacts/reports/s1-a-acceptance-20261113-final/v1-diff.json)。该变化来自明确的小数/多中心名义描述符约定及数据集来源接受；论文题名只支持组成家族背景，未提升为样品或测试的逐行原文核验。39条InNi3O0.5及1条CoGaAlO4保留证据不足状态，任何必需正含量组分不支持均排除整条记录。

## 调用与验证

```powershell
.venv/Scripts/python.exe scripts/close_s1_a.py --output artifacts/reports/<新的验收目录>
.venv/Scripts/python.exe scripts/feature_catalog.py --database data/catalog.sqlite query species themecat-centers-v2 --identity LaMn0.1Cu0.9O3
```

收尾脚本从固定证据离线重放；需已有真实SQLite及原件，输出目录必须不存在。它只追加属性/映射与资格证据，不修订催化剂事实。通用正式资格命令、Python接口及失败行为见[接口说明](s1_catalog_interface.md)。

本轮全量pytest、Ruff检查/格式检查及CLI正式资格重放结果见[验证记录](../artifacts/reports/s1-a-closeout-20261113/verification.json)。测试覆盖小数/多中心/碳酸盐、未定参数拒绝、元素计数与公式单元一致性、单组分不支持排除整行、候选更正不可生效、证据/父快照/组分关联、幂等/冲突、索引篡改及旧版本兼容。

S1-B仍需实现角色属性加权聚合、实际特征快照与selection、换序/合并不变性，并复用到新预测输入；S2再接入F1/F2、训练配置及模型包绑定。后续比较须使用同一事实快照、共同支持子集和原DOI分区。
