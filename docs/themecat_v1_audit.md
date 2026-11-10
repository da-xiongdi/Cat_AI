# TheMeCat v1 接入审计（2026-11-10）

来源：[Zenodo 17085762](https://zenodo.org/records/17085762)，TheMeCat v1.0，2025-09-23，数据集 DOI `10.5281/zenodo.17085762`；说明论文 DOI `10.1038/s41597-025-06482-8`。Zenodo API 元数据声明 `cc-by-4.0`、开放访问；使用时须署名并遵守 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 条款。此许可针对该数据集；各原始论文及附录的许可未逐一核查。Zenodo 将 active/support 的区别归于原文标注，不保证这是一致的科学分类。

下载原文件 `TheMeCat_v1.csv`，MD5 `a0328d6773e0750ff8096a7c4e4e723e` 与 Zenodo 一致；SHA-256 `46000f00323ac64a79f63777e54c05634e83d1a6476176c8b6569122bd03dfbd`。原件以 SHA-256 命名保存在 `data/raw/`。原始文件 25 列；821 条非空行、303 条全空行（跳过并报告）；按全部原始字段比较发现 1 条完全重复（第 144 行），其余潜在同源重复和冲突没有完成判定。非空行涵盖 52 个不同 DOI 链接；按行计数而非独立催化剂/论文/实验数。

覆盖（按非空行，包含重复）：温度/压力/H₂:CO₂ 比各 821；质量空速 712；CO₂ 转化率 805、甲醇选择性 779、收率 819、STY 712。该统计仅检查非空及非 NA，不表示定义一致或数值有效。

## 映射与限制

- 每条非空行保留全部原始字段、物理行号与文件哈希；配方、合成、测试和观测使用由文件哈希与行号生成的暂定 ID。它们**不表示**已识别真实独立配方或合成批次，不能用于安全的配方分组切分。
- 原始 DOI/引用、催化剂名、已列组分、前驱体、温度、压力、装样量、性能及表征值做保守映射；`NA` 映射为 unknown，保留原始字符串。H₂:CO₂ 比和组成可用性字段等保留于原始行，未假设其他气体或组成基准。
- CSV 的 `GHSV_nlph_gcat` 是按催化剂质量的流量（NL/g_cat/h），不是现有契约要求的体积空速 h⁻¹；原值保留但不换算。压力绝压/表压、组分百分比基准、原文图表位置、指标计算定义和部分合成工艺未确定；不推算性能或补造缺失信息。
- 导入 `run_id=d8af6b7a2bf0427cb4594546875c03bf`：820 staged、1 duplicate、0 curated；人工审核 0。详见 `artifacts/reports/themecat-v1-import.json`。治理 block 保持生效，不能进入已核验快照；现有审核命令只处理 curated 记录，尚需补充可追溯的修订/重新治理流程和逐条原文复核，才能形成科研训练集。
- 校验命令 `catalyst-ai validate --run-id d8af6b7a2bf0427cb4594546875c03bf` 完成 SQLite 完整性、外键和原件哈希检查；退出码 2 表示报告中存在待处理/重复记录，并非校验异常。

复现：下载上述原始 CSV 后执行 `catalyst-ai ingest --adapter themecat-v1 --source literature --input TheMeCat_v1.csv`。先用 `--dry-run` 可只读预检。重复导入会记录重复事件，不会自动合并或覆盖原始记录。公开数据集不等于已验证实验或可直接用于模型训练的数据。

## 2026-11-10 补充材料复核（不修改历史导入）

新增[数据库实施方案](themecat_implementation_plan.md)及[参考原件](references/themecat/README.md)。官方说明论文提供了数据集级的材料组分 mol%/整个材料范围、质量归一反应物流量及 293.15 K/101325 Pa 参考状态等定义依据；上文“未确定”描述对应历史适配器与行级核验状态，现尚未回写或升级。压力类型、逐行证据及真实配方/批次身份仍需处理。

独立[仓库版脚本](../scripts/validate_themecat.py)复现 821 非空行、303 全空行、52 原始 DOI 链接、1 完全重复。论文报告 822/44 与文件计数差异尚未解释，不以论文数字替代原件计数。本次从 Zenodo API 再次读取到 `cc-by-4.0`，保存了[元数据原件](../artifacts/reports/themecat-20261110/zenodo_record_17085762.json)。

[新审计报告](../artifacts/reports/themecat-20261110/profile-final/quality_summary.json)中的公式诊断仅作待复核提示，不覆盖原始值、不补标签、不改变 820 staged/1 duplicate/0 curated 或人工审核状态。原有 import_run、报告及 raw 不变。下一步按专项方案实施 B1，再开展修订重治理。
