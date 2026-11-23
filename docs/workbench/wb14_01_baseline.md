# WB-14-01 基线与页面数据契约

2026-11-19（Asia/Shanghai）只读核对 `data/workbench.sqlite`，使用 SQLite backup 生成 [一致性副本](../../artifacts/wb14-01-baseline/management.sqlite)，以现有 `queries.query` 在副本生成 [科研查询快照](../../artifacts/wb14-01-baseline/research-query.json)。来源文件状态是查询时对工作区文件的观察，数据库副本不冻结文件。

- schema 8，`quick_check` 为 ok；任务 ID 前缀 `WB-14` 暂未占用。
- A–F 六个阶段根，C 阶段下八个 S2/S3 分支；八条活动关联均为主归属，未发现引用。具体节点、章节、固定哈希与检测结果见快照。
- 十个科研任务状态均为 done；S1A-01、S1B-01 无主归属。科研焦点未设置。14 个活动节点来源检测均为 valid。证据表按版本计有 59 项 available、9 项 changed；这不是任务有效完成数。
- `research_nodes.list_research_nodes` 的 `done_count` 和 `complete` 仅按状态计算。路线图必须另按最新验收及固定证据判断，不能直接采用该完成数。待归属和 unclassified 须分开。

## 页面字段与验证

当前 `roadmap.snapshot` 为画布、树和详情提供项目及科研分类范围、观察时间、阶段、节点、关联、任务、待归属任务、待分类任务、科研焦点和全图摘要。节点提供 ID、阶段、父节点、来源路径及章节、固定哈希、来源观察状态、直接子节点及任务 ID、子树摘要和空状态；摘要提供去重任务 ID、取消项、状态计数、有效完成和证据待复核 ID、范围与来源复核标记。阶段固定 A–F，子节点按排序和 ID 排序。有效完成采用最新验收及固定证据状态，并非单看 done。

上述契约和空项目、多层、重复引用、取消任务及证据失效场景由 `tests/unit/test_wb14_roadmap.py` 验证。Web 树和直接子分支由 `tests/integration/test_workbench_web.py` 验证。2026-11-20（Asia/Shanghai）正式验收通过，验收编号 42。[正式部署基线](../../artifacts/wb14-closeout-20261120-095250-615160/baseline.json) · [验收记录](wb14_06_acceptance.md)
