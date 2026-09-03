# 慧策 ERP/WMS 产品知识运营业务设计

## 1. 服务对象

- 产品经理 / 产品运营：维护产品手册、版本说明、功能规则与 FAQ。
- 实施顾问：查询配置前置条件、实施规范、异常排查和升级路径。
- 客服团队：处理订单、库存、仓储、售后等高频咨询。
- 客户成功：面向商家提供产品使用指导，并将高频问题回流为知识缺口。

## 2. 核心知识域

| 知识域 | 示例知识 |
|---|---|
| 订单履约 | 审单、拆合单、缺货、拦截、发货、状态流转 |
| 商品/SKU | 商品映射、规格、条码、组合装、上下架 |
| 库存 | 可用/占用/锁定库存、调拨、盘点、库存同步 |
| 仓储/WMS | 入库、出库、波次、拣货、复核、打包 |
| 采购 | 采购单、供应商、到货、补货、采购入库 |
| 售后 | 退款、退货、换货、补发、逆向流程 |
| 财务/结算 | 对账、账单、回款、应收应付、金额差异 |

## 3. RAG 业务边界

问答链路必须遵循：

1. 先检索候选知识；
2. 对候选知识执行权限过滤；
3. 只有授权知识可以进入 Prompt；
4. 回答必须携带知识单元引用；
5. 无授权知识或证据不足时中断，不靠模型补全内部规则；
6. 退款、资金、库存调整、订单状态变更等高风险动作不由模型直接执行。

## 4. 知识运营闭环

```text
产品文档 / 实施规范 / 客服 FAQ
        ↓
解析、切片、去重、版本元数据
        ↓
向量化 + Milvus
        ↓
检索 -> 重排 -> 权限过滤 -> RAG 回答
        ↓
高频问题 / 低召回 / 无答案
        ↓
知识缺口
        ↓
知识管理员补充、审核 FAQ、重新入库
```

## 5. 面试时应明确的实现事实

当前分支已经做实：

- ERP/WMS 业务域识别和系统 Prompt；
- 权限过滤后入 Prompt；
- 业务化 fallback 检索；
- 产品/实施/客服/客户成功组织模型；
- FAQ、知识缺口、SSE 引用等原能力的业务映射。

当前分支已经补齐混合检索增强：

- Query Rewrite + HyDE 检索规划；
- MySQL 关键词召回 + Milvus rewrite/HyDE 双向量召回；
- RRF 跨通道排名融合；
- BGE-Reranker 可配置精排与动态断崖截断；
- reranker 不可用时自动回退 RRF 排名。

结构化入库也已补齐：

- PDF/DOCX 在 auto/mineru 模式下调用 MinerU；
- 读取 *_content_list.json，保留 page_idx、标题层级、block type；
- StructuredSplitter 生成 section_path、page_start/page_end；
- BGE-M3 对 chunk 批量 embedding；
- Milvus 改为 chunk_id 主键，同一个知识单元可保存多个 chunk；
- 引用通过 SSE 返回页码、章节和来源文件；
- MinerU 不可用时 auto 模式回退原生 parser。

评测与知识维护闭环也已补齐：

- 固定 ERP/WMS 评测集；
- Hit@K / Recall@K / MRR；
- no_recall / source_miss / low_rank / low_confidence bad-case 分类；
- 可选 RAGAS runner：Context Precision / Recall、Faithfulness、Factual Correctness；
- 真实评测语料准备脚本：固定 expected_sources，真实 BGE-M3 建索引，Milvus/BGE 不可用时 fail-fast；
- RRF-only 与 BGE-Reranker 使用同一候选集做 A/B，对比 Hit@K / Recall@K / MRR 与 rerank 延迟；
- baseline 只有显式 --write-baseline 才写入，后续可按 dataset SHA 和 regression tolerance 做回归门禁；
- 真实 LLM trace 采集已打通 retrieve -> rerank -> permission -> prompt -> generate -> RAGAS 输入；
- unit 级增量重建，不全量刷新 Milvus collection；
- PATCH content 触发重新切片 + Embedding + 旧 chunk 清理；
- PATCH title/category 仅同步 Milvus 元数据，不重复 Embedding；
- vector_pending / 已删除 unit 在权限过滤前被剔除；
- index-status、单 unit reindex、批量 consistency audit/repair；
- SourceStorage 支持 local / MinIO 双后端；
- 源文件按 `sources/{unit_code}/{content_hash}.{ext}` 版本化归档；
- reindex 时只物化与 DB `content_hash` 对应的源文件版本，hash 一致才恢复原页码/章节；
- MinIO 网络 I/O 从 async 主线程卸载到线程池，下载临时文件解析后立即清理；

这里的“增量重建”明确是 **知识单元级增量**，不是 chunk-diff 算法，不在面试中扩大描述。

前端技术栈也已与简历对齐：

- React/TSX 已迁移为 Vue 3 + TypeScript；
- Vue Router 负责路由与登录守卫；
- Pinia 管理用户会话和权限码；
- 产品文档导入、知识资产、ERP/WMS 问答已迁移为 Vue SFC；
- Dashboard 使用 ECharts 展示 Token 与响应时间趋势；
- React、react-router-dom、lucide-react 和 TSX 残留扫描为 0。
- 用户管理接入创建、更新、启停用和重置密码；后端没有用户删除接口，因此不描述成完整 CRUD。
- 角色管理接入角色列表与权限全量替换；后端没有角色创建/删除接口。
- 部门管理接入树形 CRUD，并增加 parent 自身/后代循环校验。
- FAQ 管理接入创建、人工审核、发布缓存与下线；后端没有 FAQ PATCH 接口。
- 知识缺口接入一键建档，新 unit 默认仅创建者可见，完成索引后才将 gap 标记 resolved。
- CI 启动真实 MinIO 容器执行源文件上传、下载物化与删除网络 smoke；fake client 单测仍保留用于确定性覆盖。
- 知识资产 Vue 页已接入四维权限编辑器：global 与 scoped 权限互斥；department / role / user 按 OR 组合。
- 后端权限配置拒绝重复项、global 混配、空 target_id 和不存在的部门/角色/用户 ID。
- 产品知识管理员仅额外获得 user:read / role:read / dept:read，用于选择授权目标，不获得组织写权限。

当前仍未完整做实：

- 第一份真实 BGE-M3/BGE-Reranker/Milvus A/B 数值和真实 LLM/RAGAS 数值尚未执行并提交；工具链已具备，但不能伪造结果；
- 四维权限目标用户目前按前端单页列表加载，超大组织目录仍建议改成服务端搜索/分页；
- MinIO 的真实 CI smoke 只验证单节点网络读写，不等同于生产多副本、备份恢复和 bucket lifecycle 容灾验证。

面试时不要把“规划中的增强项”说成这个分支已经存在的代码。
