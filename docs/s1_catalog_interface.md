# S1 属性、物种与记录级资格接口

2026-11-13：S1-A已完成本轮验收，见[收尾说明](s1_a_acceptance.md)。下文原接口契约仍可重放；“尚未实现”段落仅描述初版状态，现有扩展以本节为准。

- `query properties <version> [--identity Cu:covalent_radius]`或`query species <version> [--identity BaCO3]`：按属性/物种单项查询版本、来源、状态、单位及哈希；核对规范化索引与不可变原件，篡改则拒绝。
- `import-evidence <文件.json> [--commit]`：默认dry-run；独立持久化记录/组分级处置，同版本异内容拒绝。`query-evidence <version>`读取并核对原件哈希及内部身份。
- `qualify --snapshot ... --qualification ... --split ... --properties ... --species ... --review ... --output <新文件> [--evidence-root <目录>]`：正式资格检查。验证父快照、原资格/DOI划分、全部记录/组分及来源对应、外部证据原件哈希；输出分层资格，不计算特征。旧`coverage`仅为兼容诊断，不含记录级来源资格。
- 迁移新增`feature_catalog_entry`规范化事实索引及`feature_evidence`独立处置证据；回填旧目录并核对原件哈希/身份，检查SQLite完整性和外键。不提供CSV、自动证明文献语义或事实更正；特征构建及派生值表仍属S1-B。
- v2元素计数须与原物种平面式逐项一致，不得倍乘整数化后沿用旧mol%权重；中心计数不超出完整元素计数。有限语法检查拒绝x/δ、别名、括号等不支持格式；解析不赋予正式资格。
- 记录级资格schema_version=1保存version、rule_version、reviewer、parent_snapshot_id、parent_content_sha256、evidence和components。组分字段见[实际登记](../configs/s1_source_review_v2.json)：record_id、component_index、original_species、role、source_doi、dataset_sample_name、dataset_locator、status、rationale、evidence_location、evidence_sha256及candidate_species。全部父组分必须被唯一处置，pending不算终态。身份、对应关系或哈希不一致阻断整次运行。
- 来源资格允许dataset_accepted、confirmed_original、correction_rejected；evidence_insufficient/source_conflict隔离。候选更正不能授予资格；事实更正仍走修订/治理/新快照链。dataset_accepted只沿用原数据集接受策略，不表示原文逐行核验。
- 分层报告区分解析、来源、映射、两项属性及联合支持，按记录、唯一物种、DOI和原分区保留分母；唯一物种/DOI通过要求其全部出现/记录通过。缺角色为not_applicable；任一必需正含量组分不支持即排除整条记录，不重新归一。

当前绑定版本：`mendeleev-data-665935bc-pauling-cordero-v2`、`themecat-centers-v2`、`s1-source-dispositions-v2`。Python接口为`storage.feature_catalog`的migrate/import_catalog/get_catalog/query_entries/import_evidence/get_evidence，以及`features.qualification.qualify`。正式使用同时绑定三类已入库版本与哈希，不能仅调用旧coverage或读取散落配置。

## 初版接口及历史边界

此接口为 S1-A 的存储和检查基础。JSON 原件保存在 SQLite `feature_catalog.original` 中并以 SHA-256 校验；它是提交给导入器的证据包，不自动替代外部来源原件。外部原件需另行留存并在 evidence 中指明。来源许可及其对数据的适用性须分别核验。

执行入口为 `python scripts/feature_catalog.py --database <已有SQLite> <命令>`，须在已安装项目的环境中运行：

- `migrate`：给旧库新增表并运行 SQLite 完整性检查；重复运行不覆盖目录。
- `import <文件.json>`：默认 dry-run；添加 `--commit` 才入库。相同 kind/version 的原件逐字节相同则幂等，否则拒绝。
- `query properties <version>` 或 `query species <version>`：返回版本、来源、记录和哈希，读取时校验原件哈希。
- `coverage --snapshot <快照.json> --properties <version> --species <version> --output <新文件.json>`：检查快照哈希、R1 输入、正含量物种及两个属性，逐记录输出原因。报告仅表示输入可能被 R2 支持，不表示已计算特征或完成科研验证。

JSON 以 UTF-8 编码，顶层严格使用 `schema_version`（整数 1）、`kind`（`properties` 或 `species`）、`version`、`source` 和非空 `entries`。source 必须有非空 `name`、`reference`、`license`、`evidence`。属性行使用 `element`、`property`、`unit`、`state`、`value`：两种定义分别为 `pauling_electronegativity`/`1` 和 `covalent_radius`/`pm`；状态为 `available` 时值须有限且大于零，`unknown` 或 `not_applicable` 时值必须为 null。物种行使用 `species`、`state`、`centers`、`evidence`；`supported` 的 centers 是元素符号到正整数的显式映射，`unsupported` 必须为空对象。重复身份被拒绝。版本是整个证据包的身份，要改变来源、许可、数值或映射须使用新版本。

当前接口不提供 CSV、外部原件的自动抓取与核验、按元素的 SQL 索引、属性/映射事实的独立查询、特征构建和派生值表。目录版本已经导入项目数据库；见[实际数据和覆盖](s1_feature_inventory.md#实际数据和覆盖)。完整 S1-A 仍需审查映射证据和数据许可、完善持久化及查询，并完成验收。

物种目录的 schema_version=2 支持有限正小数中心计量，新增 `elements`（完整元素计数）和非空 `formula_unit_basis`（材料 mol% 对应的公式单元基准）；中心计数不得超出完整元素计数。导入器只校验结构和数值，不能证明化学式或来源语义正确。schema_version=1 仍按上述正整数契约执行，不用新方案解释旧报告。分层状态/覆盖尚未实现。记录级物种更正证据与中心映射分别管理；组成事实更正通过既有修订和新快照链生效。
