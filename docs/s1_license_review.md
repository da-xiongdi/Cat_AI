# S1 属性来源与许可适用性核查（2026-11-13）

本次核查对象为元素属性数值的导入来源及其上游分发声明，作为S1-A来源治理证据，不对原始论文全文或其他材料作权利认定。

初版从mendeleev程序包内elements.db提取Pauling电负性与Cordero共价半径，仅有程序包MIT声明，保留为历史版本。收尾改为直接核对上游作者的专用[data assets仓库](https://github.com/lmmentel/mendeleev-data/tree/665935bc115d1aaed8a8264ce4cb54c9be8b75f7)：其[README](https://github.com/lmmentel/mendeleev-data/blob/665935bc115d1aaed8a8264ce4cb54c9be8b75f7/README.md)明确数据是mendeleev数据库表导出，根目录提供[MIT许可](https://github.com/lmmentel/mendeleev-data/blob/665935bc115d1aaed8a8264ce4cb54c9be8b75f7/LICENSE)。固定提交为`665935bc115d1aaed8a8264ce4cb54c9be8b75f7`，因此本次依据覆盖具体数据分发仓库，而非仅凭程序包许可证推及所有资料。

| 原件 | 本地证据 | SHA-256 |
|---|---|---|
| 数据仓库MIT声明 | [data_license.raw](../artifacts/reports/s1-a-closeout-20261113/data_license.raw) | bcbc87d5f4ce66074a3a51d84a44df0de94d0f1a4cc794e4c17bc497b226e5eb |
| 数据范围README | [data_readme.raw](../artifacts/reports/s1-a-closeout-20261113/data_readme.raw) | 5ee139181aa96e16225c5d1426da1a433c93cec41d8015452c526a77d14f86ce |
| elements表JSON导出 | [data_elements.raw](../artifacts/reports/s1-a-closeout-20261113/data_elements.raw) | 8ea60a0afe8ba3a0d23af9220968e3d08c988d3d6d773cf032fe6a34c125ee95 |

核对118个元素×两项属性，共236个数值/未知状态，与初版逐项一致。属性定义保留Pauling无量纲、Cordero半径pm，不混用其他半径体系。[属性文档](https://mendeleev.readthedocs.io/en/stable/data.html)说明字段定义和来源；Cordero文献为[10.1039/B801115J](https://doi.org/10.1039/B801115J)。

本轮按上游作者对该数据资产仓库的MIT分发声明接受数值导入，新的属性版本为`mendeleev-data-665935bc-pauling-cordero-v2`。再分发此属性目录时须随附保留的MIT版权和许可通知，并保留数据来源、提交与原始文献引用。上游分发声明不等于已独立审查其每一原始文献的权利链；不据此再分发原文全文、表格排版或图片。本次未复制论文全文或发表数据库。

物种映射为项目中明确登记的名义描述符约定，引用已接受TheMeCat快照和方案，不把规则推导标记成化合物实测属性。TheMeCat原数据保留既有CC-BY-4.0来源及引用链；记录级来源接受和逐行核验状态不因属性许可核查而改变。
