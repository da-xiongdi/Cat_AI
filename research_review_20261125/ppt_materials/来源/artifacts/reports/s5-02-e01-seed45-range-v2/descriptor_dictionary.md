# F3 中心统计描述符字典 v2

计算版本 `f3-center-v2`。输入为设计时工况与材料 mol% 配方，元素性质来自 S1 属性目录 `mendeleev-data-665935bc-pauling-cordero-v2`（SHA-256 `054671ae81226b32cd727041a33b52bce8afe4076ac89ae82dc03f33ce86676f`）；中心数来自物种目录 `themecat-centers-v2`（SHA-256 `b663ca79807cb135436525ebeb6ba0d1450a620844cb6a15b6d6509226b8eef8`）。前者包括 Pauling 电负性和 Cordero 共价半径；后者是名义公式单位上的经项目证据支持的中心数，不是实测活性位。

| 字段 | 公式及单位 | 条件与状态 |
|---|---|---|
| `role_material_mol_pct` | 同角色物种材料 mol% 之和，% | 缺角色为合法零 |
| `role_species_count` | 合并同名物种后的正量物种数，1 | 缺角色为零 |
| `role_present` | 存在正量物种为 1，否则 0 | 合法零或一 |
| `role_mean_property` | Σ(a×n×p)/Σ(a×n)，电负性无量纲、半径 pm | 无角色为 not_applicable；映射或属性不可用则拒绝 |
| `role_variance_property` | Σ(a×n×(p−均值)²)/Σ(a×n)，单位分别为 1 和 pm² | 同均值；零方差是合法零 |
| `active_minus_support_property` | active 均值减 support 均值，单位同均值 | 两角色均存在；否则 not_applicable |
| `active_support_ratio` | active 材料 mol% 之和除 support 材料 mol% 之和，无量纲 | 两个总量均正；否则 not_applicable |

这里 a 是物种材料 mol%，n 是目录中该元素中心数，p 是对应属性。例：两个物种的量分别 25 和 75、各中心数为 1、属性为 2 和 4，则均值 3.5、方差 0.75。`compound` 和 `support` 分别对应 reported_active 和 reported_support；其他正量角色拒绝。组成必须是材料 mol% 且闭合于 100±0.5，四项工况必须为正值。缺角色的描述符保留 null，模型使用零占位及存在标志。派生值在每个训练折单独拟合范围，超范围或该折无参考值时发出警示。

P 为四工况及角色统计块，H 为 F_base 加相同材料块，I 为 P 加角色差及比例。H 的材料量与 F_base 中物种量存在重复，F1/F2 与部分中心均值也有重叠。特征仅使用设计前可获得信息，不纳入目标或实验后表征；未引入名义元素计量统计。
