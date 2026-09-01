"""Query Rewrite + HyDE planning for ERP/WMS product knowledge retrieval."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.business.erp_wms import BUSINESS_DOMAINS, detect_domains


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    original: str
    rewritten: str
    hyde_document: str
    keyword_terms: tuple[str, ...]


_STOP_FRAGMENTS = (
    "请问",
    "帮我",
    "一下",
    "怎么",
    "如何",
    "为什么",
    "是什么",
    "怎么办",
    "有没有",
    "能不能",
)


def _clean_query(text: str) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    for fragment in _STOP_FRAGMENTS:
        value = value.replace(fragment, "")
    return value.strip(" ，。！？?；;：:") or text.strip()


def _business_terms(question: str, rewritten: str) -> tuple[str, ...]:
    """抽取适合 MySQL LIKE 召回的高价值业务词，避免对整句中文做精确匹配。"""
    combined = f"{question} {rewritten}"
    terms: list[str] = []

    for config in BUSINESS_DOMAINS.values():
        for keyword in config["keywords"]:
            keyword = str(keyword)
            if keyword in combined and keyword not in terms:
                terms.append(keyword)

    # 订单号/SKU/英文缩写/数字等结构化 token 对产品文档检索很有价值。
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,31}|\d{3,}", combined):
        if token not in terms:
            terms.append(token)

    # 没命中业务词时，用清理后的短句兜底；最多保留 8 个 term 控制 SQL 条件规模。
    if not terms:
        cleaned = _clean_query(rewritten)
        if cleaned:
            terms.append(cleaned[:64])
    return tuple(terms[:8])


def _fallback_hyde(question: str, rewritten: str) -> str:
    domains = detect_domains(question)
    domain_text = "、".join(domains) if domains else "ERP/WMS 产品"
    return (
        f"这是一个关于{domain_text}的产品知识说明。用户问题是：{rewritten}。"
        "应说明适用场景、前置条件、操作或状态规则、异常排查步骤、权限边界和注意事项，"
        "并结合产品版本、店铺/仓库、业务单据和异常时间定位问题。"
    )


def _parse_json_object(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


async def build_retrieval_plan(question: str, llm: object | None = None) -> RetrievalPlan:
    """优先用 LLM 一次生成 Rewrite + HyDE；失败时使用确定性业务兜底。"""
    rewritten = _clean_query(question)
    hyde_document = _fallback_hyde(question, rewritten)

    if llm is not None and hasattr(llm, "stream"):
        prompt = f"""你是电商 ERP/WMS 产品知识库的检索规划器。
只返回 JSON，不要 Markdown：
{{"rewrite":"适合检索产品文档的简洁问题","hyde":"假设知识库中存在的标准答案式短文，80~160字"}}
要求：保留产品名、业务对象、状态、异常现象、平台/仓库/SKU 等关键约束，不编造具体产品规则。
用户问题：{question}
"""
        try:
            answer, _usage = await llm.stream(prompt)  # type: ignore[attr-defined]
            data = _parse_json_object(answer)
            if data:
                llm_rewrite = str(data.get("rewrite") or "").strip()
                llm_hyde = str(data.get("hyde") or "").strip()
                if llm_rewrite:
                    rewritten = llm_rewrite[:256]
                if llm_hyde:
                    hyde_document = llm_hyde[:1000]
        except Exception:
            # 检索规划失败不应阻断主问答链路。
            pass

    return RetrievalPlan(
        original=question,
        rewritten=rewritten,
        hyde_document=hyde_document,
        keyword_terms=_business_terms(question, rewritten),
    )


__all__ = ["RetrievalPlan", "build_retrieval_plan"]
