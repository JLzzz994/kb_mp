#!/usr/bin/env bash
# kb_mp 业务演示脚本（curl 版）
# 用法：先启动后端，然后 bash demo_curl.sh
set -e

API_BASE=${API_BASE:-http://localhost:8000/api/v1}

echo "════════════════════════════════════════"
echo "  kb_mp 业务演示（curl）"
echo "  API: $API_BASE"
echo "════════════════════════════════════════"

# ── 0. 健康检查 ─────────────────────────────
echo ""
echo "[0] 健康检查"
HEALTH=$(curl -s "$API_BASE/health")
echo "    $HEALTH"

# ── 1. 登录 ─────────────────────────────
echo ""
echo "[1] 登录（admin）"
LOGIN=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
echo "    token (前 30 字符): ${TOKEN:0:30}..."

# ── 2. 当前用户信息 ─────────────────────────────
echo ""
echo "[2] 当前用户"
ME=$(curl -s "$API_BASE/auth/me" \
  -H "Authorization: Bearer $TOKEN")
echo "$ME" | python3 -m json.tool | head -20

# ── 3. 部门树 ─────────────────────────────
echo ""
echo "[3] 部门树"
DEPT=$(curl -s "$API_BASE/org/departments" \
  -H "Authorization: Bearer $TOKEN")
echo "$DEPT" | python3 -m json.tool

# ── 4. 知识单元列表 ─────────────────────────────
echo ""
echo "[4] 知识单元列表"
UNITS=$(curl -s "$API_BASE/knowledge-units" \
  -H "Authorization: Bearer $TOKEN")
echo "$UNITS" | python3 -m json.tool

# ── 5. 知识导入（示例文件） ─────────────────────────────
echo ""
echo "[5] 上传示例文档（03-示例数据/*.md）"
for f in ../03-示例数据/0*.md; do
    if [ -f "$f" ]; then
        RESP=$(curl -s -X POST "$API_BASE/knowledge/import" \
            -H "Authorization: Bearer $TOKEN" \
            -F "files=@$f")
        echo "    上传 $(basename $f): $RESP"
    fi
done

# ── 6. AI 问答（SSE 流式） ─────────────────────────────
echo ""
echo "[6] AI 问答：'kb_mp 平台是什么？'"
SESSION_ID="demo-$(date +%s)"
curl -N -s -X POST "$API_BASE/ai/chat/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\", \"question\": \"kb_mp 平台是什么？\"}"

# ── 7. FAQ 列表 ─────────────────────────────
echo ""
echo "[7] FAQ 列表"
FAQ=$(curl -s "$API_BASE/faqs" \
  -H "Authorization: Bearer $TOKEN")
echo "$FAQ" | python3 -m json.tool | head -30

# ── 8. 数据看板 ─────────────────────────────
echo ""
echo "[8] 数据看板（30 天）"
DASH=$(curl -s "$API_BASE/dashboard/metrics?range=30" \
  -H "Authorization: Bearer $TOKEN")
echo "$DASH" | python3 -m json.tool

echo ""
echo "════════════════════════════════════════"
echo "  演示完成"
echo "════════════════════════════════════════"