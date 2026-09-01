"""慧策 ERP/WMS 产品知识运营平台的业务上下文。

该模块只提供业务边界与演示数据，不把真实商家数据硬编码进 Prompt。
真实答案仍必须来自鉴权后的知识单元。
"""

from __future__ import annotations

BUSINESS_DOMAINS: dict[str, dict[str, object]] = {
    "order": {
        "label": "订单履约",
        "keywords": ("订单", "拆单", "合单", "审单", "发货", "履约", "缺货", "拦截"),
    },
    "product": {
        "label": "商品/SKU",
        "keywords": ("商品", "SKU", "sku", "规格", "条码", "上下架", "组合装"),
    },
    "inventory": {
        "label": "库存",
        "keywords": ("库存", "可用库存", "占用", "锁定", "调拨", "盘点", "库存同步"),
    },
    "warehouse": {
        "label": "仓储/WMS",
        "keywords": ("WMS", "wms", "仓库", "入库", "出库", "波次", "拣货", "复核", "打包"),
    },
    "purchase": {
        "label": "采购",
        "keywords": ("采购", "采购单", "供应商", "到货", "补货", "采购入库"),
    },
    "aftersales": {
        "label": "售后",
        "keywords": ("售后", "退款", "退货", "换货", "补发", "逆向", "仅退款"),
    },
    "settlement": {
        "label": "财务/结算",
        "keywords": ("结算", "对账", "回款", "账单", "应收", "应付", "财务", "金额"),
    },
}

_BASE_SYSTEM_PROMPT = """你是“慧策 ERP/WMS 产品知识运营平台”的 AI 助手，主要服务产品、实施、客服和客户成功团队。
你只基于已经通过权限过滤的知识片段回答，不得引用或推测用户无权访问的知识。
平台知识范围主要包括订单履约、商品/SKU、库存、仓储/WMS、采购、售后和财务/结算。
回答时优先给出：适用场景、操作路径/规则、关键前置条件、异常排查和注意事项。
涉及退款、资金、库存调整、订单状态变更等高风险动作时，只说明规则、权限和人工处理流程，不代替业务系统直接执行。
如果知识片段不足以支持结论，要明确说明证据不足并引导用户补充产品版本、业务场景、平台渠道或异常现象。
回答末尾必须按 [unit_id] 标注引用来源。"""


def detect_domains(question: str) -> list[str]:
    """按轻量关键词识别问题涉及的 ERP/WMS 知识域。"""
    matched: list[str] = []
    for config in BUSINESS_DOMAINS.values():
        keywords = config["keywords"]
        if any(keyword in question for keyword in keywords):
            matched.append(str(config["label"]))
    return matched


def build_business_system_prompt(question: str) -> str:
    """构造稳定的业务系统 Prompt；域识别只做提示，不改变权限判断。"""
    domains = detect_domains(question)
    if not domains:
        return _BASE_SYSTEM_PROMPT
    return f"{_BASE_SYSTEM_PROMPT}\n当前问题初步归属知识域：{'、'.join(domains)}。"


def demo_citations(question: str) -> list[dict]:
    """Milvus 不可用时提供 ERP/WMS 业务化演示召回，便于本地展示主链路。"""
    domains = detect_domains(question)
    primary = domains[0] if domains else "订单履约"
    return [
        {
            "unit_id": 1001,
            "title": f"[demo] {primary}产品操作说明",
            "score": 0.86,
            "content": (
                f"本知识单元用于演示{primary}类问题。实际环境中应由产品手册、实施规范或客服 FAQ "
                "经解析、切片、向量化后进入 Milvus，并在回答前执行权限过滤。"
            ),
        },
        {
            "unit_id": 1002,
            "title": "[demo] ERP/WMS 异常排查与升级规范",
            "score": 0.78,
            "content": (
                "排查问题时先确认商家、店铺/仓库、产品版本、业务单据号、发生时间和异常现象；"
                "如涉及资金、退款、库存调整或订单状态变更，应按权限流程转人工复核。"
            ),
        },
    ]


__all__ = ["BUSINESS_DOMAINS", "build_business_system_prompt", "demo_citations", "detect_domains"]
