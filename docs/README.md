# Joybuy 复刻项目文档索引

版本：`v0.1`  
基线日期：`2026-11-02`  
状态：需求讨论完成，尚未开始业务编码

本项目在已获得 Joybuy 品牌素材、页面复刻、数据抓取及公开部署授权的前提下，用于内部研究与演示，并可在验收完成后部署到公开服务器。

## 文档

1. [产品与需求规格](./01-requirements.md)
2. [页面清单与视觉验收](./02-pages-and-visual-acceptance.md)
3. [系统架构](./03-architecture.md)
4. [数据模型与文件存储](./04-data-model-and-storage.md)
5. [爬虫与数据导入](./05-crawler-and-ingestion.md)
6. [API 与业务流程](./06-api-and-workflows.md)
7. [部署、测试与路线图](./07-deployment-testing-roadmap.md)
8. [按 Codex 会话拆分的实施工作包](./08-implementation-work-packages.md)
9. [爬虫任务品类与配额页面改造方案](./09-crawler-category-task-redesign.md)
10. [多语言商品内容与国家市场设计](./10-multilingual-content-and-market-design.md)
11. [真实 Joybuy 站点产品功能分析](./11-joybuy-co-uk-product-features.md)
12. [真实 Joybuy 站点界面还原规格](./12-joybuy-co-uk-ui-spec.md)
13. [数据库表结构与字段说明](./13-database-schema.md)

## 决策优先级

若文档间出现冲突，按以下顺序处理：

1. `01-requirements.md` 中的“范围”和“明确不做”；
2. `06-api-and-workflows.md` 中的业务状态机；
3. `04-data-model-and-storage.md` 中的数据约束；
4. 其他技术实现说明。

任何范围变更必须先更新文档，再开始编码。

