# S1-B 特征构建（2026-11-13）

使用已入库的属性、物种映射及记录级来源证据重新核验冻结快照，按原 DOI 分区筛选；正含量组分须全部支持。输出 [selection.json](../artifacts/reports/s1-b-20261113-v4/selection.json) 与 [features.json](../artifacts/reports/s1-b-20261113-v4/features.json)，分别记录逐条筛选、分区覆盖及完整组成、四项工况和派生值。训练、验证、历史测试分别保留 454、47、52 条，排除 39、0、1 条。未改变源事实或父快照。

`features.physchem.calculate(payload, properties, species)` 同样适用于新的规范化预测输入；历史记录必须先经 `qualification.qualify` 验证来源。角色均值以材料 mol% 乘目录中心计数为权重；缺席角色的均值及差值为 `not_applicable`/null。`model_values` 生成 F1/F2 增量，并仅在模型数组中将无定义值置零。目录及记录级审核版本和哈希、计算代码哈希均记录在产物中。`storage.feature_build.get_build` 核对快照哈希及逐值索引；重复写入幂等，篡改或冲突拒绝。

命令：

```powershell
.venv/Scripts/python.exe scripts/build_s1_b.py --database data/catalog.sqlite --snapshot data/snapshots/snapshot-76c42099edd134fca92e0ade54a919995e541b947e0bb0b264de67791a4d61da.json --qualification data/snapshots/qualifications/qualification-b450e999aca00cd7e035b5bb1006a48d3fbd171520391710eb05a2490aa85967.json --split artifacts/reports/themecat-i2-20261110/split-verified.json --properties mendeleev-data-665935bc-pauling-cordero-v2 --species themecat-centers-v2 --review s1-source-dispositions-v2 --output artifacts/reports/<新目录>
```

此构建不执行模型训练或声明性能增益；F1/F2 与训练、模型包及预测入口的集成属于后续 S2。来源接受不表示逐行原文核验。

