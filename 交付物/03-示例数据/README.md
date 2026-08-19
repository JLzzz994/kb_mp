# 示例数据说明

## 目录结构

```
03-示例数据/
├── 01-kb_mp-平台介绍.md        # 平台概述（KU-001）
├── 02-kb_mp-部署指南.md        # 部署文档（KU-002）
├── 03-研发中心技术规范.md      # 技术规范（KU-003，限研发中心）
├── 04-FAQ清单.md               # 5 条 FAQ 演示（KU-004）
├── seed-dataset.json           # 种子数据集元数据
└── README.md                   # 本文件
```

## 使用方法

### 方案 A：通过 `knowledge/import` 接口上传

```bash
# 1. 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}' | jq -r .access_token)

# 2. 上传单个 Markdown 文件
curl -X POST http://localhost:8000/api/v1/knowledge/import \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@01-kb_mp-平台介绍.md"

# 3. 批量上传
curl -X POST http://localhost:8000/api/v1/knowledge/import \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@01-kb_mp-平台介绍.md" \
  -F "files=@02-kb_mp-部署指南.md" \
  -F "files=@03-研发中心技术规范.md" \
  -F "files=@04-FAQ清单.md"
```

后台会自动：
1. 解析文件（按扩展名选择 parser）
2. 切片（chunk_size=512 + overlap=64）
3. SHA-256 去重
4. 落库 knowledge_units
5. 异步向量化 → Milvus upsert

### 方案 B：通过 SQL 直接插入（推荐演示期）

```sql
INSERT INTO knowledge_units (unit_code, title, content, category, summary, status, creator_id)
VALUES
    ('KU-001', 'kb_mp 平台介绍', '<文件内容>', '产品', '...', 'active', 1),
    ...
```

权限配置：

```sql
-- 全局可见
INSERT INTO unit_permissions (unit_id, target_type, target_id) VALUES (1, 'global', NULL);

-- 部门可见
INSERT INTO unit_permissions (unit_id, target_type, target_id) VALUES (3, 'department', 1);
```

## 演示问题

打开 AI 对话工作台，问以下 6 个问题可完整演示流程：

1. **"kb_mp 平台是什么？"** → 命中 KU-001，正常问答
2. **"如何部署 kb_mp？"** → 命中 KU-002，正常问答
3. **"技术规范有哪些内容？"** → 命中 KU-003（限研发中心）
4. **"如何重置密码？"** → 命中 KU-004 FAQ 缓存（faq_cache_lookup 优先）
5. **"AI 召回不到的常见原因？"** → 命中 KU-001 + KU-004
6. **"完全不相关的问题"** → 触发 interrupt（召回为空）

## 演示账号 → 可见范围

| 账号 | 部门 | 可见单元 |
|------|------|---------|
| admin | 研发中心 | KU-001/002/003/004/005 |
| kadmin | 研发中心 | KU-001/002/003/004/005 |
| alice | 运营部 | KU-001/002/004/005（无 KU-003） |