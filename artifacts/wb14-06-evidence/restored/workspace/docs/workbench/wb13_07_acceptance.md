# WB-13-07 共用查询与兼容接入

2026-11-18（Asia/Shanghai）。完成代码及隔离验证；未写入正式管理库，也不代表 WB-13-08 或父任务验收。

`catalyst_ai.workbench.queries.query(path, project_id, scope)` 是 Web 和 CLI 共用的只读查询。范围为 `all`、`research`、`workbench`、`unclassified`；返回项目和类别、观察时间、schema 版本、分类任务及按状态计数、历史交付、科研节点及关联、分类上下文、各任务主计划检测和缺失主计划清单。任务按 ID 计数；当前 schema 无任务父子关系，不推断父项或累计子项进度。节点统计复用既有按任务 ID 去重的实现。类别变化或终结后保留的焦点和近期安排通过原服务的复核提示返回。

查询使用 SQLite backup 生成临时一致性副本；文件检测仍读取实际工作区，文件可能在查询期间变化，结果并非文件系统快照。来源路径、章节、固定哈希和各对象修订随原记录返回；检测结果与已核对版本区分。未设主计划列入 `missing`，其他来源异常由各自的检测状态说明。旧 `list_tasks` 和原 URL 行为不变。

接入：`GET /api/workbench/v1/query?category=all`；CLI 为 `catalyst-ai workbench query --config configs/workbench.yaml --category all`。非法类别返回 422（CLI 使用参数校验）。无需新写入接口或新页面。

验证：工作台相关单元与集成测试 67 项通过，1 条 Starlette 测试客户端弃用警告；CLI 对现有管理库只读查询返回 schema 8 和 10 条任务。隔离库上使用 Edge 无头浏览器打开旧 `/tasks` 并从页面请求新接口，均返回 200。Ruff 检查与格式检查见本次执行结果。正式部署、完整备份恢复及跨页面验收仍由 WB-13-08 执行。
