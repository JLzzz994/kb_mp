from app.business.erp_wms import build_business_system_prompt, demo_citations, detect_domains


def test_detect_domains_for_inventory_and_wms() -> None:
    domains = detect_domains("WMS 库存同步异常，仓库可用库存为什么没有变化？")
    assert "库存" in domains
    assert "仓储/WMS" in domains


def test_high_risk_guardrail_is_in_prompt() -> None:
    prompt = build_business_system_prompt("退款后如何调整库存？")
    assert "售后" in prompt
    assert "库存" in prompt
    assert "不代替业务系统直接执行" in prompt
    assert "权限过滤" in prompt


def test_demo_citations_are_business_specific() -> None:
    citations = demo_citations("订单审核失败怎么排查？")
    assert len(citations) == 2
    assert citations[0]["unit_id"] == 1
    assert "订单履约" in citations[0]["title"]
    assert citations[0]["score"] > citations[1]["score"]
