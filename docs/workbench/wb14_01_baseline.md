# WB-14-01 基线核对（进行中）

2026-11-19（Asia/Shanghai）只读核对 `data/workbench.sqlite`，使用 SQLite backup 生成 [一致性副本](../../artifacts/wb14-01-baseline/management.sqlite)，以现有 `queries.query` 在副本生成 [科研查询快照](../../artifacts/wb14-01-baseline/research-query.json)。来源文件状态是查询时对工作区文件的观察，数据库副本不冻结文件。

- schema 8，`quick_check` 为 ok；任务 ID 前缀 `WB-14` 暂未占用。
- A–F 六个阶段根，C 阶段下八个 S2/S3 分支；八条活动关联均为主归属，未发现引用。具体节点、章节、固定哈希与检测结果见快照。
- 十个科研任务状态均为 done；S1A-01、S1B-01 无主归属。科研焦点未设置。14 个活动节点来源检测均为 valid。证据表按版本计有 59 项 available、9 项 changed；这不是任务有效完成数。
- `research_nodes.list_research_nodes` 的 `done_count` 和 `complete` 仅按状态计算。路线图必须另按最新验收及固定证据判断，不能直接采用该完成数。待归属和 unclassified 须分开。

本记录仅完成基线采集，尚未实现共享统计、页面字段契约及空分支、多层、重复引用、取消任务和证据失效的隔离场景验证；WB-14-01 尚未完成。
