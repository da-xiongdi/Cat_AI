# WB-16-02、03、04 验收复核

2026-11-23（Asia/Shanghai）。针对已完成的三个子任务重新执行验收验证。

- WB-16-02：`scripts/verify_wb16_02_browser.py` 在 Edge 三种视口验证总览、科研任务导航、筛选、返回和刷新。
- WB-16-03：`scripts/verify_wb16_03_browser.py` 验证分类列表、固定版本和返回路径；正式库一致性副本浏览前后不变。明细见 [原验证记录](wb16_03_verification.md)。
- WB-16-04：`scripts/verify_wb16_04_browser.py` 验证维护页、固定证据、历史交付双向链接、备份恢复入口和三种视口，正式库副本浏览前后不变。明细见 [验证记录](wb16_04_verification.md)与[历史复核](wb16_04_history_review.md)。
- Edge 158.0.4370.33，视口为 1366×768、1920×1080 和 390×844。上述三个脚本均通过。
- 验收范围是三个子任务的实现和验证。WB-16-05 的跨页面联调及 WB-16-06 的专项验收、发布和恢复演练仍按后续任务执行。
- 全量 `.venv/Scripts/python.exe -m pytest -q`：266 项通过，1 项依赖弃用警告。
