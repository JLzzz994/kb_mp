# ADR-0001: 部署架构（MySQL + Milvus + Redis 单机一体化）

## 状态
已决定 (2026-08-19)

## 背景
需求文档描述了"MySQL 环境受限可降级为全文索引 + 关键词"等风险。kb_mp 项目定位为单机演示版，需要在 Docker Compose 一体化启动，避免本地复杂依赖。

## 决策
- **MySQL 8.0**：主数据库，承载 11 张表（users / departments / roles / user_roles / role_permissions / knowledge_units / unit_permissions / qa_access_logs / chat_sessions / faqs / knowledge_gaps）
- **Milvus 2.4 单机版**：向量检索（standalone + etcd + MinIO 三件套）
- **Redis 7**：缓存（鉴权位图 + FAQ 缓存）
- **演示启动方式**：`docker-compose up` 一键拉起 mysql + milvus + redis + app
- **不启用**：Prometheus / Grafana / Jaeger（按概要设计 Q10 决议）
- **Attu**：仅开发环境的 Milvus 可视化（zilliz/attu:latest）

## 影响
- 概要设计 §4.1 中间件层
- 概要设计 §11 风险（Milvus 重启数据丢失已识别）
- 演示环境 docker-compose.yml 拓扑

## 备选方案
- pgvector：被拒（PRD §11 仅在演示环境作为 fallback 保留）
- Chroma / Faiss：被拒，无集群能力
- OpenAI 官方向量库：被拒，依赖外部 SaaS

## 关联
- 概要设计 §4.1（中间件）、§4.2（拓扑）、§10 P5
- 4A 架构图（技术架构层 / 中间件层）
