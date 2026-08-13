#!/usr/bin/env python3
"""Compose a supply-chain prospect (潜客推荐) report by orchestrating the supply MCP.

Calls the upstream supply-mcp-server tools and assembles a structured JSON
payload rendered into a professional HTML / Markdown report. Supports
``--dry-run`` which returns a well-formed skeleton from the bundled sample data
WITHOUT contacting the MCP.

This report is **keyword-driven** by product names (``--keywords``,
comma-separated). Workflow:
  1. ``supply_get_down_stream_products`` → downstream product catalog by industry.
  2. ``supply_get_down_stream_enterprises`` → downstream enterprises (with filters).
  3. ``advanced_filter_get_enterprise_count`` / ``advanced_filter_get_enterprise_list``
     → refined prospect list via advanced filters (``!`` prefix = negation).

This file never prints secrets; MCP credentials live in the server's own .env.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Mapping, Optional

from common import REPORT_BANNER, REPORT_TYPE, json_dumps, load_json_file, print_json
import mcp_client
from render_report import render_html, render_markdown, html_to_pdf

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "report.example.json"

# Supply MCP tools.
T_PRODUCTS = "supply_get_down_stream_products"
T_ENTERPRISES = "supply_get_down_stream_enterprises"
T_FILTER_COUNT = "advanced_filter_get_enterprise_count"
T_FILTER_LIST = "advanced_filter_get_enterprise_list"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_api_error(value: Any) -> bool:
    """Detect MCP API error responses (not empty data, but actual failures like 405)."""
    if value is None:
        return False
    if isinstance(value, str):
        return any(s in value for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5"))
    if isinstance(value, dict):
        for v in value.values():
            if isinstance(v, str) and any(s in v for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5")):
                return True
    return False

def _first_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if _is_api_error(value):
            return []
        for key in ("resultList", "list", "items", "data"):
            if isinstance(value.get(key), list):
                return value[key]
    if value in (None, "", {}):
        return []
    return [value]


def _first_record(value: Any) -> Dict[str, Any]:
    for record in _first_list(value):
        if isinstance(record, dict):
            return record
    if isinstance(value, dict):
        return value
    return {}


def _text(value: Any, limit: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        t = json.dumps(value, ensure_ascii=False)
    else:
        t = str(value)
    t = " ".join(t.split())
    if limit and len(t) > limit:
        return t[: limit - 1].rstrip() + "…"
    return t


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_call(tool: str, arguments: Dict[str, Any]) -> Any:
    try:
        result = mcp_client.call_tool(tool, arguments)
        # Detect API error responses (405, etc.) and return error marker
        if _is_api_error(result):
            return {"_error": "API错误", "_raw": result}
        return result
    except Exception as exc:
        return {"_error": str(exc)}


def _safe_total(payload: Any) -> Any:
    if isinstance(payload, dict):
        if _is_api_error(payload):
            return None
        return payload.get("total")
    return None


# --------------------------------------------------------------------------- #
# Subject
# --------------------------------------------------------------------------- #

def build_subject(keywords: str, filters: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "keywords": keywords,
        "matchKeyword": keywords,
        "main_products": filters.get("main_products") or "",
        "address": filters.get("address") or "",
        "is_high_tech": filters.get("is_high_tech") or "",
        "is_top_enterprise": filters.get("is_top_enterprise") or "",
        "is_foreign_trade": filters.get("is_foreign_trade") or "",
        "reg_capital_min": filters.get("reg_capital_min") if filters.get("reg_capital_min") is not None else "",
        "reg_capital_max": filters.get("reg_capital_max") if filters.get("reg_capital_max") is not None else "",
        "advanced_filter_address": filters.get("advanced_address") or "",
        "advanced_enterprise_type": filters.get("enterprise_type") or "",
    }


def build_metrics(products: Any, enterprises: Any, filter_count: Any) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    prod_total = _safe_total(products)
    if prod_total is not None:
        metrics.append({"label": "下游产品数", "value": _text(prod_total), "hint": "下游产品检索命中条数"})
    ent_total = _safe_total(enterprises)
    if ent_total is not None:
        metrics.append({"label": "下游企业数", "value": _text(ent_total), "hint": "下游企业检索命中条数"})
    fc = filter_count if isinstance(filter_count, dict) else {}
    fc_total = fc.get("total")
    if fc_total is not None:
        metrics.append({"label": "高级筛选企业数", "value": _text(fc_total), "hint": "高级筛选条件下符合企业数"})
    return [m for m in metrics if m.get("value") not in ("", None, "-")]


def build_caliber(subject: Mapping[str, Any]) -> Dict[str, Any]:
    parts = [f"按产品关键词“{subject.get('keywords')}”检索下游产品与企业"]
    if subject.get("main_products"):
        parts.append(f"；下游企业主营产品过滤={subject.get('main_products')}")
    if subject.get("address") or subject.get("advanced_filter_address"):
        parts.append(f"；地区过滤={subject.get('address') or subject.get('advanced_filter_address')}")
    if subject.get("is_high_tech"):
        parts.append(f"；高新企业={subject.get('is_high_tech')}")
    if subject.get("reg_capital_min") or subject.get("reg_capital_max"):
        parts.append(f"；注册资本区间={subject.get('reg_capital_min')}-{subject.get('reg_capital_max')} 万")
    return {
        "match_target": f"产品关键词“{subject.get('keywords')}”",
        "match_type": "".join(parts),
        "data_scope": "下游产品、下游企业明细、高级筛选企业清单",
        "products": ["下游产品", "下游企业", "高级筛选企业数量", "高级筛选企业清单"],
        "limit": "数据来自企业公开数据库；高级筛选清单最多返回 500 条。",
    }


def build_core_analysis(products: Any, enterprises: Any, filter_list: Any, subject: Mapping[str, Any]) -> Dict[str, Any]:
    # 下游产品表
    product_rows = []
    for item in _first_list(products):
        if not isinstance(item, dict):
            continue
        prod_list = item.get("products")
        prod_text = "、".join(_text(p) for p in prod_list) if isinstance(prod_list, list) else _text(prod_list)
        product_rows.append({
            "下游行业": _text(item.get("industry")) or "-",
            "下游产品": prod_text or "-",
        })

    # 下游企业明细表
    enterprise_rows = []
    recommend_rows: List[Dict[str, Any]] = []
    factory_inspected = 0
    factory_enterprise = 0
    ent_total_with_flags = 0
    reg_capital_rmb_values: List[float] = []
    for item in _first_list(enterprises):
        if not isinstance(item, dict):
            continue
        # 注册资本：优先使用 regCapitalRmb (float, 单位元)，回退到 regCapital 结构
        reg_rmb = item.get("regCapitalRmb")
        reg_text = ""
        if isinstance(reg_rmb, (int, float)) and reg_rmb > 0:
            # regCapitalRmb 单位为元，转换为万人民币显示
            reg_text = f"{reg_rmb / 10000:.2f}万人民币"
            reg_capital_rmb_values.append(float(reg_rmb) / 10000.0)  # store as 万
        else:
            reg = item.get("regCapital") if isinstance(item.get("regCapital"), dict) else {}
            if reg:
                reg_text = f"{reg.get('value', '')}{reg.get('coinType', '')}".strip() or _text(reg.get("origin"))
        # 推荐理由：可能是 list[{headWord,tailWord,reason}] 或 dict
        reason_field = item.get("factoryRecommendReason")
        reason_list = reason_field if isinstance(reason_field, list) else ([reason_field] if isinstance(reason_field, dict) else [])
        first_reason = ""
        if reason_list and isinstance(reason_list[0], dict):
            first_reason = _text(reason_list[0].get("reason"), limit=80)
        elif reason_list:
            first_reason = _text(reason_list[0], limit=80)
        enterprise_rows.append({
            "企业名称": _text(item.get("name")) or "-",
            "主营产品": _text(item.get("mainProducts")) or "-",
            "城市": _text(item.get("city")) or "-",
            "注册资本": reg_text or "-",
            "成立时间": _text(item.get("foundTime")) or "-",
            "推荐理由": first_reason or "-",
        })
        # 产品关联表（来源：factoryRecommendReason[].headWord/tailWord/reason）
        for r in reason_list:
            if isinstance(r, dict):
                recommend_rows.append({
                    "企业名称": _text(item.get("name")) or "-",
                    "下游产品": _text(r.get("headWord")) or "-",
                    "关键词": _text(r.get("tailWord")) or "-",
                    "关联理由": _text(r.get("reason"), limit=120) or "-",
                })
        # 验厂 / 工厂型资质统计
        ent_total_with_flags += 1
        if _text(item.get("factoryInspectionType")) == "已验厂":
            factory_inspected += 1
        if _text(item.get("isFactoryEnterprise")) == "是":
            factory_enterprise += 1

    # 高级筛选企业清单表
    filter_rows = []
    for item in _first_list(filter_list):
        if not isinstance(item, dict):
            continue
        reg = item.get("regCapital") if isinstance(item.get("regCapital"), dict) else {}
        reg_text = ""
        if reg:
            reg_text = f"{reg.get('value', '')}{reg.get('coinType', '')}".strip() or _text(reg.get("origin"))
        flags = []
        if item.get("isHighTechEnterprise"):
            flags.append("高新")
        if item.get("isTopEnterprise"):
            flags.append("500强")
        if item.get("isUnicornEnterprise"):
            flags.append("独角兽")
        if item.get("isSpecializedAndNew"):
            flags.append("专精特新")
        filter_rows.append({
            "企业名称": _text(item.get("name")) or "-",
            "法定代表人": _text(item.get("legalRepresentative")) or "-",
            "注册资本": reg_text or "-",
            "成立时间": _text(item.get("foundTime")) or "-",
            "企业标签": "、".join(flags) or "-",
        })

    # Derive downstream industry distribution (aggregate product_rows by 下游行业).
    industry_counts: Dict[str, int] = {}
    for r in product_rows:
        ind = r.get("下游行业")
        if ind and ind != "-":
            industry_counts[ind] = industry_counts.get(ind, 0) + 1
    industry_dist_rows = [{"下游行业": k, "记录数": str(n)} for k, n in sorted(industry_counts.items(), key=lambda kv: kv[1], reverse=True)]

    # Derive regional distribution (aggregate enterprise_rows by 城市).
    region_counts: Dict[str, int] = {}
    for r in enterprise_rows:
        c = r.get("城市")
        if c and c != "-":
            region_counts[c] = region_counts.get(c, 0) + 1
    region_dist_rows = [{"城市": k, "企业数": str(n)} for k, n in sorted(region_counts.items(), key=lambda kv: kv[1], reverse=True)]

    # 验厂 / 工厂型企业资质统计
    factory_stats = {
        "样本数": ent_total_with_flags,
        "已验厂数": factory_inspected,
        "工厂型企业数": factory_enterprise,
        "已验厂占比": f"{factory_inspected / ent_total_with_flags * 100:.1f}%" if ent_total_with_flags else "-",
        "工厂型企业占比": f"{factory_enterprise / ent_total_with_flags * 100:.1f}%" if ent_total_with_flags else "-",
    } if ent_total_with_flags else {}

    sections = [
        {"key": "product_records", "title": "下游产品", "kind": "table",
         "note": f"按产品关键词“{subject.get('keywords')}”检索，共 {_safe_total(products) or len(product_rows)} 个行业/记录",
         "columns": [("下游行业", "下游行业"), ("下游产品", "下游产品")]},
        {"key": "industry_dist", "title": "下游行业分布", "kind": "bar",
         "note": "按下游行业聚合检索命中记录数（覆盖广度）",
         "chart": {"name": "下游行业", "value": "记录数", "orient": "v"},
         "columns": [("下游行业", "下游行业"), ("记录数", "记录数")]},
        {"key": "enterprise_records", "title": "下游企业明细", "kind": "table",
         "note": f"共 {_safe_total(enterprises) or len(enterprise_rows)} 家，展示前 N 家",
         "columns": [("企业名称", "企业名称"), ("主营产品", "主营产品"), ("城市", "城市"), ("注册资本", "注册资本"), ("成立时间", "成立时间"), ("推荐理由", "推荐理由")]},
        {"key": "product_relation", "title": "产品关联", "kind": "table",
         "note": "下游产品(headWord)→关键词(tailWord)→关联理由（来源：factoryRecommendReason）",
         "columns": [("企业名称", "企业名称"), ("下游产品", "下游产品"), ("关键词", "关键词"), ("关联理由", "关联理由")]},
        {"key": "factory_qualification", "title": "验厂/工厂型资质", "kind": "kv",
         "note": "已验厂(factoryInspectionType)与工厂型企业(isFactoryEnterprise)占比（基于当前样本）"},
        {"key": "region_dist", "title": "下游企业地域分布", "kind": "bar",
         "note": "按城市聚合下游企业样本数（产业集群定位）",
         "chart": {"name": "城市", "value": "企业数", "orient": "h"},
         "columns": [("城市", "城市"), ("企业数", "企业数")]},
    ]
    if filter_rows or subject.get("advanced_filter_address") or subject.get("advanced_enterprise_type") or subject.get("is_high_tech") or subject.get("is_top_enterprise"):
        sections.append({"key": "filter_records", "title": "高级筛选企业清单", "kind": "table",
                         "note": "通过高级筛选条件（地区 / 企业类型 / 高新等）筛选；清单最多 500 家",
                         "columns": [("企业名称", "企业名称"), ("法定代表人", "法定代表人"), ("注册资本", "注册资本"), ("成立时间", "成立时间"), ("企业标签", "企业标签")]})

    return {
        "sections": sections,
        "product_records": product_rows,
        "industry_dist": industry_dist_rows,
        "enterprise_records": enterprise_rows,
        "product_relation": recommend_rows,
        "factory_qualification": factory_stats,
        "region_dist": region_dist_rows,
        "filter_records": filter_rows,
        "reg_capital_rmb": reg_capital_rmb_values,
    }


def build_records(core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for item in core.get("enterprise_records") or []:
        out.append({
            "企业名称": item.get("企业名称") or "-",
            "主营产品": item.get("主营产品") or "-",
            "城市": item.get("城市") or "-",
        })
    return out[:20]


def _concentration_rows(rows: List[Mapping[str, Any]], name_key: str, value_key: str, top_n: int = 3) -> Dict[str, Any]:
    """CRn concentration from aggregated rows."""
    items = []
    for r in rows:
        try:
            items.append((r.get(name_key, "-"), float(str(r.get(value_key, 0)).replace(",", ""))))
        except (TypeError, ValueError):
            items.append((r.get(name_key, "-"), 0.0))
    total = sum(v for _, v in items)
    if not total:
        return {}
    items.sort(key=lambda x: x[1], reverse=True)
    cr = sum(v for _, v in items[:top_n]) / total * 100
    return {"top": items[0][0], "top_share": items[0][1] / total * 100, "cr": cr, "total": total, "count": len(items)}


def _reg_capital_stats(rows: List[Mapping[str, Any]], rmb_values: Optional[List[float]] = None) -> Dict[str, Any]:
    """Aggregate 注册资本 (万人民币) into scale buckets + avg.

    Prefers the raw ``regCapitalRmb`` floats (already converted to 万) when
    available; otherwise falls back to regex-parsing the 注册资本 string.
    """
    nums: List[float] = []
    if rmb_values:
        nums = [float(n) for n in rmb_values if isinstance(n, (int, float)) and n > 0]
    if not nums:
        for r in rows:
            raw = str(r.get("注册资本") or "")
            # Extract leading number (handles "50000万人民币").
            import re as _re
            m = _re.search(r"(\d+(?:\.\d+)?)", raw)
            if m:
                try:
                    nums.append(float(m.group(1)))
                except (TypeError, ValueError):
                    pass
    if not nums:
        return {}
    buckets = {"微型(<500万)": 0, "小型(500-2000万)": 0, "中型(2000-10000万)": 0, "大型(>10000万)": 0}
    for n in nums:
        if n < 500:
            buckets["微型(<500万)"] += 1
        elif n < 2000:
            buckets["小型(500-2000万)"] += 1
        elif n < 10000:
            buckets["中型(2000-10000万)"] += 1
        else:
            buckets["大型(>10000万)"] += 1
    return {"avg": sum(nums) / len(nums), "count": len(nums), "buckets": buckets}


def build_insights(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    metric_map = {m["label"]: str(m["value"]) for m in metrics}
    prod_n = metric_map.get("下游产品数")
    ent_n = metric_map.get("下游企业数")
    fc_n = metric_map.get("高级筛选企业数")

    # 1. 下游产品广度
    if prod_n:
        insights.append({
            "feature": "下游产品广度",
            "evidence": f"按关键词“{subject.get('keywords')}”检索到下游产品记录 {prod_n} 条。",
            "interpretation": "下游产品广度反映关键词在供应链中的延伸面；覆盖行业越多，潜在客户领域越宽。",
        })

    # 2. 潜在客户规模
    if ent_n:
        insights.append({
            "feature": "潜在客户规模",
            "evidence": f"下游企业检索命中 {ent_n} 家。",
            "interpretation": "下游企业命中量是潜客池规模的直接信号；结合主营产品与地区可进一步聚焦高价值客户。",
        })

    # 3. 下游行业集中度（CR3）
    industry_dist = core.get("industry_dist") or []
    if industry_dist:
        conc = _concentration_rows(industry_dist, "下游行业", "记录数", 3)
        if conc:
            diversity = "多元" if conc["count"] >= 5 else ("较集中" if conc["top_share"] >= 50 else "较多元")
            insights.append({
                "feature": "下游行业集中度",
                "evidence": f"覆盖下游行业 {conc['count']} 个，“{conc['top']}”记录占比约 {conc['top_share']:.0f}%，前 3 行业合计 {conc['cr']:.0f}%（CR3）。",
                "interpretation": f"下游应用{diversity}；集中度高说明需求集中在少数行业（可深耕），多元分布则抗周期能力强。",
            })

    # 4. 地域集中度（CR3 + 覆盖城市数）
    region_dist = core.get("region_dist") or []
    if region_dist:
        conc = _concentration_rows(region_dist, "城市", "企业数", 3)
        if conc:
            cluster = "高度集群化" if conc["top_share"] >= 40 else "分散布局"
            insights.append({
                "feature": "地域集中度",
                "evidence": f"覆盖城市 {conc['count']} 个，“{conc['top']}”企业占比约 {conc['top_share']:.0f}%，前 3 城市合计 {conc['cr']:.0f}%（CR3）。",
                "interpretation": f"地域{cluster}；高集中度区域通常是产业带，便于线下拜访与物流优化，分散布局则需分区域拓展。",
            })

    # 5. 企业规模结构（注册资本分桶）—— 优先使用 regCapitalRmb 原始值
    enterprise_rows = core.get("enterprise_records") or []
    rmb_values = core.get("reg_capital_rmb") or []
    cs = _reg_capital_stats(enterprise_rows, rmb_values=rmb_values)
    if cs:
        b = cs["buckets"]
        # 找最大桶
        top_bucket = max(b.items(), key=lambda kv: kv[1])
        insights.append({
            "feature": "企业规模结构",
            "evidence": f"样本 {cs['count']} 家，平均注册资本 {cs['avg']:.0f} 万；规模分布：大 {b['大型(>10000万)']}、中 {b['中型(2000-10000万)']}、小 {b['小型(500-2000万)']}、微 {b['微型(<500万)']}（最多为“{top_bucket[0]}”，{top_bucket[1]} 家）。",
            "interpretation": "规模结构反映潜客质量；大中型企业订单稳定但决策链长，小微客户决策快但单量小，需匹配销售策略。",
        })

    # 6. 高级筛选聚焦
    if fc_n:
        insights.append({
            "feature": "高级筛选聚焦",
            "evidence": f"高级筛选条件下符合企业 {fc_n} 家。",
            "interpretation": "高级筛选用于在潜客池中进一步聚焦（地区 / 企业类型 / 资质等），提升线索质量与转化效率。",
        })

    # 验厂 / 工厂型资质洞察
    fq = core.get("factory_qualification") or {}
    if fq and fq.get("样本数"):
        sample_n = int(fq.get("样本数"))
        inspected_pct = fq.get("已验厂占比", "-")
        factory_pct = fq.get("工厂型企业占比", "-")
        inspected_n = fq.get("已验厂数", 0)
        factory_n = fq.get("工厂型企业数", 0)
        insights.append({
            "feature": "验厂/工厂型资质",
            "evidence": f"样本 {sample_n} 家中，已验厂 {inspected_n} 家（{inspected_pct}）、工厂型企业 {factory_n} 家（{factory_pct}）。",
            "interpretation": "已验厂比例高意味着供应商资质可查、合作风险较低；工厂型企业占比高通常具备自有产能与定制能力，适合需要深度协同的采购场景。",
        })

    if not insights:
        insights.append({
            "feature": "数据完整性",
            "evidence": "部分维度未返回有效数据。",
            "interpretation": "建议核对产品关键词或筛选条件，或检查 MCP 连接与上游数据产品覆盖范围。",
        })
    return insights


def build_abstract(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> str:
    kw = subject.get("keywords") or "目标产品"
    parts = [f"本报告以产品关键词“{kw}”为检索对象，基于供应链潜客推荐数据，系统呈现下游产品、下游企业明细与高级筛选企业清单。"]
    if metrics:
        kv = "、".join(f"{m['label']} {m['value']}" for m in metrics[:5])
        parts.append(f"关键指标包括：{kv}。")
    parts.append("报告同时给出下游产品广度、潜在客户规模与地域集中度的结构化解读，便于销售线索挖掘与供应链拓展参考。")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Dry-run sample
# --------------------------------------------------------------------------- #

def build_dry_run_payload(keywords: str, filters: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        sample = load_json_file(SAMPLE_PATH)
    except Exception:
        sample = {}
    sample = sample if isinstance(sample, dict) else {}
    subject = sample.get("subject") or build_subject(keywords, filters)
    subject = {**subject, "keywords": keywords, **{k: v for k, v in filters.items() if v}}
    core = sample.get("core_analysis") or {}
    metrics = sample.get("metrics") or []
    return _assemble(subject, core, metrics, dry_run=True)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _assemble(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]], *, dry_run: bool) -> Dict[str, Any]:
    abstract = build_abstract(subject, core, metrics)
    records = build_records(core)
    insights = build_insights(subject, core, metrics)
    # Quality gate: count populated core-analysis sections.
    ca = core if isinstance(core, dict) else {}
    secs = ca.get("sections", [])
    if secs:
        total_secs = len(secs)
        populated = sum(1 for s in secs if isinstance(s, dict) and ca.get(s.get("key")) not in (None, "", [], {}))
    else:
        total_secs = max(1, len([k for k in ca if k != "sections"]))
        populated = sum(1 for k in ca if k != "sections" and ca.get(k) not in (None, "", [], {}))
    quality_report = {
        "total_sections": total_secs,
        "populated_sections": populated,
        "empty_sections": total_secs - populated,
        "coverage_pct": round(populated / max(1, total_secs) * 100),
    }
    if populated == 0:
        import sys
        print("⚠️ 质量门禁警告: 所有核心分析维度均无数据", file=sys.stderr)
    title = f"“{subject.get('keywords') or '目标产品'}” 供应链潜客推荐报告"
    return {
        "report_type": REPORT_TYPE,
        "title": title,
        "banner": REPORT_BANNER,
        "subject": dict(subject),
        "abstract": abstract,
        "summary": abstract,
        "executive_summary": [item["interpretation"] for item in insights][:5] or [abstract[:120]],
        "metrics": list(metrics),
        "caliber": build_caliber(subject),
        "core_analysis": dict(core),
        "representative_records": records,
        "insights": insights,
        "data_source": {
            "mcp_server": "supply-mcp-server",
            "products": [
                {"name": "下游产品", "product_id": "68c02b268cc760ff46ee93c3"},
                {"name": "下游企业", "product_id": "68c02fb58cc760ff46ee948e"},
                {"name": "高级筛选企业数量", "product_id": "690342962e32082a0cfd003a"},
                {"name": "高级筛选企业清单", "product_id": "690367b52e32082a0cfd00ba"},
            ],
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "quality_report": quality_report,
        },
    }


def _enterprise_filters(filters: Mapping[str, Any]) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    if filters.get("main_products"):
        args["mainProducts"] = filters["main_products"]
    if filters.get("address"):
        args["address"] = filters["address"]
    if filters.get("is_foreign_trade"):
        args["isForeignTrade"] = filters["is_foreign_trade"]
    if filters.get("is_high_tech"):
        args["isHighTechEnterprise"] = filters["is_high_tech"]
    if filters.get("is_top_enterprise"):
        args["isTopEnterprise"] = filters["is_top_enterprise"]
    if filters.get("reg_capital_min") is not None:
        args["regCapitalMin"] = filters["reg_capital_min"]
    if filters.get("reg_capital_max") is not None:
        args["regCapitalMax"] = filters["reg_capital_max"]
    return args


def _advanced_filter_args(filters: Mapping[str, Any]) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    if filters.get("advanced_address"):
        args["address"] = filters["advanced_address"]
    if filters.get("enterprise_type"):
        args["enterpriseType"] = filters["enterprise_type"]
    if filters.get("reg_capital_min") is not None:
        args["regCapitalRmbGte"] = filters["reg_capital_min"]
    if filters.get("reg_capital_max") is not None:
        args["regCapitalRmbLte"] = filters["reg_capital_max"]
    if filters.get("is_high_tech"):
        # advanced_filter 没有 isHighTech 字段，但可用 enterpriseType 表达；此处保留供未来扩展。
        pass
    return args


def build_payload(keywords: str, filters: Mapping[str, Any], page_size: int) -> Dict[str, Any]:
    # 1. 下游产品
    products = _safe_call(T_PRODUCTS, {"keywords": keywords})

    # 2. 下游企业（带过滤）
    ent_args: Dict[str, Any] = {"keywords": keywords, "pageIndex": 1, "pageSize": page_size}
    ent_args.update(_enterprise_filters(filters))
    enterprises = _safe_call(T_ENTERPRISES, ent_args)

    # 3. 高级筛选（仅在提供高级筛选条件时调用）
    filter_count: Any = {}
    filter_list: Any = {}
    adv_args = _advanced_filter_args(filters)
    if adv_args:
        list_args = {**adv_args, "pageIndex": 1, "pageSize": 10}
        filter_count = _safe_call(T_FILTER_COUNT, {**adv_args, "pageIndex": 1, "pageSize": 10})
        filter_list = _safe_call(T_FILTER_LIST, list_args)

    subject = build_subject(keywords, filters)
    core = build_core_analysis(products, enterprises, filter_list, subject)
    metrics = build_metrics(products, enterprises, filter_count)
    _derive_core_metrics(metrics, core if isinstance(core, dict) else {})
    return _assemble(subject, core, metrics, dry_run=False)


def _derive_core_metrics(metrics: List[Dict[str, Any]], core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Derive additional metrics from core analysis sections."""
    industry = core.get("industry_dist", []) if isinstance(core, dict) else []
    region = core.get("region_dist", []) if isinstance(core, dict) else []
    products = core.get("product_records", []) if isinstance(core, dict) else []
    if isinstance(industry, list) and industry:
        metrics.append({"label": "下游行业数", "value": str(len(industry)), "hint": "覆盖的下游行业数量"})
        try:
            def _cnt(r):
                v = str(r.get("记录数", "0"))
                return int(v) if v.isdigit() else 0
            top = max(industry, key=_cnt)
            if top.get("下游行业"):
                metrics.append({"label": "主要下游行业", "value": str(top["下游行业"]), "hint": "企业最多的下游行业"})
        except (ValueError, TypeError):
            pass
    if isinstance(region, list) and region:
        metrics.append({"label": "覆盖城市数", "value": str(len(region)), "hint": "下游企业所在城市数"})
        try:
            nums = [int(r.get("企业数", 0)) for r in region if r.get("企业数") and str(r.get("企业数")).isdigit()]
            total = sum(nums)
            if total > 0:
                top3 = sum(sorted(nums, reverse=True)[:3])
                metrics.append({"label": "城市CR3", "value": f"{top3/total*100:.1f}%", "hint": "前3大城市企业集中度"})
        except (ValueError, TypeError):
            pass
    if isinstance(products, list) and products:
        metrics.append({"label": "下游产品类目", "value": str(len(products)), "hint": "关联的下游产品类别数"})
    return metrics


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Compose a supply-chain prospect report via the supply MCP.")
    parser.add_argument("--keywords", required=True, help="产品关键词，多个产品名用英文逗号分隔（如 钢材,铝材）")
    parser.add_argument("--main-products", default=None, help="下游企业主营产品过滤（多个用英文逗号分隔）")
    parser.add_argument("--address", default=None, help="下游企业地区过滤，如 广东省,深圳市（或 广东省）")
    parser.add_argument("--is-foreign-trade", default=None, choices=["是", "否"], help="是否外贸企业")
    parser.add_argument("--is-high-tech", default=None, choices=["是", "否"], help="是否高新技术企业（下游企业过滤）")
    parser.add_argument("--is-top-enterprise", default=None, choices=["是", "否"], help="是否500强企业（下游企业过滤）")
    parser.add_argument("--reg-capital-min", type=int, default=None, help="注册资本最小值（万人民币）")
    parser.add_argument("--reg-capital-max", type=int, default=None, help="注册资本最大值（万人民币）")
    parser.add_argument("--advanced-address", default=None, help="高级筛选地区，支持 ! 前缀表示非，如 !北京,!广州市")
    parser.add_argument("--enterprise-type", default=None, help="高级筛选企业类型，如 个体户,!国有")
    parser.add_argument("--page-size", type=int, default=50, help="下游企业检索分页大小（最多 100）")
    parser.add_argument("--dry-run", action="store_true", help="不调用真实 MCP，使用样例数据组装报告骨架")
    parser.add_argument("--output", help="输出 JSON 路径；省略则打印到 stdout")
    parser.add_argument("--report-output", help="同时输出 HTML 报告（.html）与 Markdown 报告（.md）")
    parser.add_argument("--pdf-output", help="额外输出 PDF 报告（.pdf）；需要 Playwright + Chromium")
    args = parser.parse_args()

    filters = {
        "main_products": args.main_products,
        "address": args.address,
        "is_foreign_trade": args.is_foreign_trade,
        "is_high_tech": args.is_high_tech,
        "is_top_enterprise": args.is_top_enterprise,
        "reg_capital_min": args.reg_capital_min,
        "reg_capital_max": args.reg_capital_max,
        "advanced_address": args.advanced_address,
        "enterprise_type": args.enterprise_type,
    }

    if args.dry_run:
        payload = build_dry_run_payload(args.keywords, filters)
    else:
        payload = build_payload(args.keywords, filters, args.page_size)

    if args.output:
        out = pathlib.Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_dumps(payload, pretty=True), encoding="utf-8")
        print_json({"ok": True, "json": str(out), "dry_run": args.dry_run})
    else:
        print_json(payload)

    if args.report_output:
        base_out = pathlib.Path(args.report_output).expanduser()
        base_out.parent.mkdir(parents=True, exist_ok=True)
        html_path = base_out.with_suffix(".html") if base_out.suffix.lower() not in (".html", ".htm") else base_out
        md_path = html_path.with_suffix(".md")
        html_path.write_text(render_html(payload), encoding="utf-8")
        md_path.write_text(render_markdown(payload), encoding="utf-8")
        if args.pdf_output:
            pdf_path = pathlib.Path(args.pdf_output).expanduser()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            html_to_pdf(render_html(payload), str(pdf_path))
        print_json({"ok": True, "html": str(html_path), "markdown": str(md_path), "pdf": str(pdf_path) if args.pdf_output else None, "dry_run": args.dry_run})


if __name__ == "__main__":
    main()
