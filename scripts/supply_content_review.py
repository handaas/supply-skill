#!/usr/bin/env python3
"""Offline content review for an existing supply-chain prospect report.

Pure ``apply_content_review(report)`` separates industry groups from product
entries, keeps enterprise samples separate from full totals, renders product
tags as text, removes scientific notation, and marks recommendation prose as
upstream marketing copy. It never calls the MCP.
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping

_UNIT_UNDECLARED = "（上游原值，单位未声明）"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_empty(value: Any) -> bool:
    return _text(value) in {"", "-", "—", "None", "null"}


def _join_tags(value: Any) -> str:
    """Render list-like upstream fields as readable text, never JSON syntax."""
    if isinstance(value, (list, tuple)):
        return "、".join(_text(v) for v in value if _text(v))
    text = _text(value)
    if not text or text in {"-", "—"}:
        return "-"
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return "、".join(_text(v) for v in parsed if _text(v)) or "-"
        except (ValueError, TypeError):
            pass
    return text


def _capital_text(raw: Any) -> str:
    text = _text(raw)
    if not text or text in {"-", "—"}:
        return "-"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)[eE]\+?(\d+)(.*)", text)
    if match:
        try:
            number = Decimal(match.group(1)) * (Decimal(10) ** int(match.group(2)))
        except (InvalidOperation, ValueError):
            return text
        suffix = match.group(3)
        return f"{int(number):,}{suffix}"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(.*)", text)
    if match:
        try:
            number = Decimal(match.group(1))
        except InvalidOperation:
            return text
        body = f"{int(number):,}" if number == number.to_integral() else f"{number.normalize():f}"
        return f"{body}{match.group(2)}"
    return text


def _product_entries(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"[、,，;；]", _text(text)) if p.strip() and p.strip() not in {"-", "—"}]


def _fix_caliber(report: Dict[str, Any]) -> None:
    subject = report.get("subject") if isinstance(report.get("subject"), dict) else {}
    caliber = report.get("caliber")
    if not isinstance(caliber, dict):
        return
    parts = [f"按产品关键词“{_text(subject.get('keywords'))}”检索下游产品与企业"]
    labels = (
        ("main_products", "下游企业主营产品过滤"), ("address", "下游企业地区过滤"),
        ("is_high_tech", "高新企业"), ("is_foreign_trade", "外贸企业"), ("is_top_enterprise", "500强企业"),
    )
    for key, label in labels:
        if _text(subject.get(key)):
            parts.append(f"{label}={subject[key]}")
    if _text(subject.get("reg_capital_min")) and _text(subject.get("reg_capital_max")):
        parts.append(f"注册资本={subject['reg_capital_min']}-{subject['reg_capital_max']} 万元")
    elif _text(subject.get("reg_capital_min")):
        parts.append(f"注册资本≥{subject['reg_capital_min']} 万元")
    elif _text(subject.get("reg_capital_max")):
        parts.append(f"注册资本≤{subject['reg_capital_max']} 万元")
    adv = []
    if _text(subject.get("advanced_filter_address")):
        adv.append(f"地区={subject['advanced_filter_address']}")
    if _text(subject.get("advanced_enterprise_type")):
        adv.append(f"企业类型={subject['advanced_enterprise_type']}")
    if adv:
        core = report.get("core_analysis") or {}
        status = (core.get("source_status") or {}).get("advanced_filter_list")
        verification = ("接口受阻，未验证条件生效" if status in {"error", "blocked", "unsupported"}
                        else "仅记录已发送条件，不独立验证生效")
        parts.append("独立高级筛选条件：" + "；".join(adv) + f"（{verification}）")
    caliber["match_type"] = "；".join(parts)
    caliber["limit"] = (
        "高级筛选是独立的全库企业筛选，不与关键词下游产品/企业结果求交集，也不能据此推断采购意向；"
        "清单最多返回 500 条。行业分布按下游产品条目统计，企业地域分布按当前企业样本统计，二者不是同一总体；"
        "注册资本单位未声明，不做规模分桶。"
    )


def _fix_products(core: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[str]]:
    rows = core.get("product_records")
    entries: List[str] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                entries.extend(_product_entries(_text(row.get("下游产品"))))
    industry = Counter()
    labeled_names = set()
    labeled_entries = 0
    unlabeled_records = 0
    unlabeled_entries = 0
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                name = _text(row.get("下游行业"))
                count = len(_product_entries(_text(row.get("下游产品"))))
                if not name or _is_empty(name):
                    unlabeled_records += 1
                    unlabeled_entries += count
                    continue
                labeled_names.add(name)
                labeled_entries += count
                if count:
                    industry[name] += count
    labeled_groups = len(labeled_names)
    core["industry_dist"] = [{"下游行业": k, "下游产品条目数": str(v)}
                              for k, v in industry.most_common()]
    sections = core.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            if section.get("key") == "product_records":
                section["note"] = f"返回 {labeled_groups} 个有下游行业标签的分组，覆盖 {labeled_entries} 个下游产品条目；分组数不等于产品条目数"
                if unlabeled_records:
                    section["note"] += (f"；另有 {unlabeled_records} 条记录（{unlabeled_entries} 个下游产品条目）"
                                        "未返回下游行业，已保留明细但不计入行业分布")
                section["columns"] = [("下游行业", "下游行业"), ("下游产品", "下游产品")]
            elif section.get("key") == "industry_dist":
                section["title"] = "下游行业分布（产品条目）"
                section["note"] = "按下游产品条目（而非企业记录）聚合；记录数不等于企业数"
                section["chart"] = {"name": "下游行业", "value": "下游产品条目数", "orient": "v"}
                section["columns"] = [("下游行业", "下游行业"), ("下游产品条目数", "下游产品条目数")]
    return [r for r in (rows or []) if isinstance(r, dict)], entries


def _fix_enterprises(core: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = core.get("enterprise_records")
    out: List[Dict[str, Any]] = []
    reasons: List[str] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            reviewed = dict(row)
            main = _join_tags(reviewed.get("主营产品"))
            if main.endswith("…") or main.endswith("..."):
                main += "（上游返回文本截断，未补齐）"
            reviewed["主营产品"] = main
            reviewed["注册资本"] = _capital_text(reviewed.get("注册资本"))
            reason = _text(reviewed.get("推荐理由"))
            if reason and reason != "-":
                reasons.append(reason)
                if reason.endswith("…") or reason.endswith("..."):
                    reviewed["推荐理由"] = reason + "（上游文案，原文截断）"
            out.append(reviewed)
    core["enterprise_records"] = out

    relation = core.get("product_relation")
    if isinstance(relation, list):
        for row in relation:
            if isinstance(row, dict):
                reason = _text(row.get("关联理由"))
                if reason.endswith("…") or reason.endswith("..."):
                    row["关联理由"] = reason + "（上游文案，原文截断）"

    sections = core.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            if section.get("key") == "enterprise_records":
                note = _text(section.get("note"))
                note = re.sub(r"上游命中(?:总数)*", "上游命中总数", note)
                note = re.sub(r"(?:当前样本)+", "当前样本", note)
                section["note"] = note
                section["columns"] = [("企业名称", "企业名称"), ("主营产品", "主营产品"), ("城市", "城市"),
                                      ("注册资本", "注册资本"), ("成立时间", "成立时间"), ("推荐理由", "推荐理由")]
            elif section.get("key") == "product_relation":
                section["note"] = "下游产品→关键词→上游关联文案；文案为上游生成，不是采购意向、订单或供应商资格证明"
            elif section.get("key") == "factory_qualification":
                section["note"] = "已验厂/工厂型企业仅为平台字段在当前企业样本中的比例；不认定资质有效性、采购适配或合作风险"
    return out, reasons


def _fix_metrics(report: Dict[str, Any], core: Dict[str, Any], entries: List[str],
                 enterprises: List[Dict[str, Any]]) -> None:
    metrics = [m for m in (report.get("metrics") or []) if isinstance(m, dict)]
    sample_n = len(enterprises)
    total = next((_text(m.get("value")) for m in metrics if m.get("label") == "下游企业数"), "")
    industry_rows = [r for r in (core.get("industry_dist") or []) if isinstance(r, dict)]
    top_industry = ""
    if industry_rows:
        try:
            top_industry = _text(max(industry_rows, key=lambda r: float(str(r.get("下游产品条目数", 0)))).get("下游行业"))
        except (TypeError, ValueError):
            top_industry = ""
    out: List[Dict[str, Any]] = []
    for metric in metrics:
        label = _text(metric.get("label"))
        if label == "下游产品数":
            metric["label"] = "下游产品关联记录"
            metric["hint"] = "按下游行业分组的记录数；非 SKU/产品条目数，展开产品见明细"
        elif label == "下游企业数":
            metric["hint"] = f"检索命中企业总数；明细表仅为当前样本 {sample_n} 家"
        elif label == "下游行业数":
            if not industry_rows:
                continue
            metric["value"] = str(len(industry_rows))
            metric["hint"] = "有下游行业标签的分组数；未返回行业的记录不计入"
        elif label == "主要下游行业":
            if not top_industry:
                continue
            metric["value"] = top_industry
            metric["hint"] = "下游产品条目最多的有标签行业（非企业样本）"
        elif label == "覆盖城市数":
            metric["label"] = "已返回城市数"
            metric["hint"] = f"当前企业样本（{sample_n} 家{('/ 命中 ' + total) if total else ''}）中的城市数，不代表全部命中企业"
        elif label == "城市CR3":
            metric["label"] = "已返回城市CR3"
            metric["hint"] = f"仅在当前企业样本（{sample_n} 家）内计算，不代表全部命中企业"
        elif label == "下游产品类目":
            continue  # duplicate of 下游产品数
        out.append(metric)
    report["metrics"] = out


def _concentration(rows: List[Mapping[str, Any]], name_key: str, value_key: str, top_n: int = 3) -> Dict[str, Any]:
    values = []
    for row in rows:
        try:
            values.append((_text(row.get(name_key)) or "-", float(str(row.get(value_key, 0)).replace(",", ""))))
        except (TypeError, ValueError):
            values.append((_text(row.get(name_key)) or "-", 0.0))
    total = sum(v for _, v in values)
    if not total:
        return {}
    values.sort(key=lambda kv: -kv[1])
    return {
        "top": values[0][0], "top_n": values[0][1], "top_share": values[0][1] / total * 100,
        "cr": sum(v for _, v in values[:top_n]) / total * 100, "total": total, "count": len(values),
    }


def _build_insights(report: Dict[str, Any], core: Dict[str, Any], entries: List[str],
                    enterprises: List[Dict[str, Any]], reasons: List[str]) -> List[Dict[str, Any]]:
    metrics = {m.get("label"): _text(m.get("value")) for m in (report.get("metrics") or []) if isinstance(m, dict)}
    insights: List[Dict[str, Any]] = []
    product_rows = [r for r in (core.get("product_records") or []) if isinstance(r, dict)]
    labeled_rows = [r for r in product_rows if not _is_empty(_text(r.get("下游行业")))]
    unlabeled_rows = [r for r in product_rows if _is_empty(_text(r.get("下游行业")))]
    labeled_entries = sum(len(_product_entries(_text(r.get("下游产品")))) for r in labeled_rows)
    unlabeled_entries = sum(len(_product_entries(_text(r.get("下游产品")))) for r in unlabeled_rows)
    labeled_groups = len({_text(r.get("下游行业")) for r in labeled_rows})
    if product_rows:
        evidence = f"返回 {labeled_groups} 个有下游行业标签的分组，覆盖 {labeled_entries} 个下游产品条目。"
        if unlabeled_rows:
            evidence += (f"另有 {len(unlabeled_rows)} 条记录（{unlabeled_entries} 个下游产品条目）"
                         "未返回下游行业，已保留明细但不计入行业分布。")
        insights.append({
            "feature": "下游产品关联广度",
            "evidence": evidence,
            "interpretation": "行业分组数与产品条目数不同；只表示关键词在平台产品映射中的延伸面，不代表需求量、订单或采购意向。",
        })
    if metrics.get("下游企业数"):
        insights.append({
            "feature": "下游关联企业规模",
            "evidence": f"下游企业检索命中 {metrics['下游企业数']} 家；当前企业明细样本 {len(enterprises)} 家。",
            "interpretation": "命中量只表示产品关联候选范围；样本不等于全量，也不能推断采购意向。",
        })
    industry = [r for r in (core.get("industry_dist") or []) if isinstance(r, dict)]
    if industry:
        conc = _concentration(industry, "下游行业", "下游产品条目数", 3)
        if conc:
            insights.append({
                "feature": "下游行业分布（产品条目口径）",
                "evidence": f"按下游产品条目统计，{conc['count']} 个行业中“{conc['top']}”最多（{conc['top_n']:g} 条，占 {conc['top_share']:.0f}%），前 3 行业合计 {conc['cr']:.0f}%（CR3）。",
                "interpretation": "该分布的分母是下游产品条目，不是企业数；不能据此判断行业需求规模或企业采购意向。",
            })
    region = [r for r in (core.get("region_dist") or []) if isinstance(r, dict)]
    if region:
        conc = _concentration(region, "城市", "企业数", 3)
        if conc:
            insights.append({
                "feature": "企业地域分布（当前样本）",
                "evidence": f"当前样本 {len(enterprises)} 家覆盖 {conc['count']} 个城市；“{conc['top']}”最多（{conc['top_n']:g} 家，占 {conc['top_share']:.0f}%），CR3 {conc['cr']:.0f}%。",
                "interpretation": "仅描述当前企业样本的城市字段，不代表全部命中企业，也不证明产业带或区域采购需求。",
            })
    if reasons:
        counter = Counter(reasons)
        repeated, count = counter.most_common(1)[0]
        if count >= 2:
            insights.append({
                "feature": "上游推荐文案",
                "evidence": f"当前样本 {len(reasons)} 条推荐理由中，有 {count} 条使用同一段模板文案。",
                "interpretation": "推荐理由是上游生成的关联说明，属于营销/解释文案，不是采购需求、订单、供应商资格或合作证据；重复出现不代表更多需求。",
            })
    if metrics.get("高级筛选企业数"):
        insights.append({
            "feature": "高级筛选（独立口径）",
            "evidence": f"独立高级筛选命中 {metrics['高级筛选企业数']} 家。",
            "interpretation": "高级筛选是全库条件筛选，不是下游候选交集；命中数不能推断采购意向或与关键词的匹配度。",
        })
    factory = core.get("factory_qualification") or {}
    if isinstance(factory, dict) and factory.get("样本数"):
        insights.append({
            "feature": "下游候选平台字段（样本）",
            "evidence": f"当前样本 {factory.get('样本数')} 家中，已验厂 {factory.get('已验厂数', '-')} 家（{factory.get('已验厂占比', '-')}）、工厂型企业 {factory.get('工厂型企业数', '-')} 家（{factory.get('工厂型企业占比', '-')}）。",
            "interpretation": "仅为平台字段在样本中的比例；不认定供应商资质、采购适配或合作风险。",
        })
    if not insights:
        insights.append({
            "feature": "数据完整性",
            "evidence": "部分维度未返回有效数据。",
            "interpretation": "不得将缺失解释为零企业或无下游；建议核对关键词与筛选条件。",
        })
    return insights


_FAILED_LABELS = (
    ("downstream_products", "下游产品"),
    ("downstream_enterprises", "下游企业"),
    ("advanced_filter_list", "高级筛选企业清单"),
)


def _failed_dimensions(core: Mapping[str, Any]) -> List[str]:
    statuses = core.get("source_status") if isinstance(core.get("source_status"), Mapping) else {}
    return [label for key, label in _FAILED_LABELS if statuses.get(key) == "error"]


def _empty_dimensions(core: Mapping[str, Any]) -> List[str]:
    statuses = core.get("source_status") if isinstance(core.get("source_status"), Mapping) else {}
    return [label for key, label in _FAILED_LABELS if statuses.get(key) == "empty"]


def _build_abstract(report: Dict[str, Any], entries: List[str]) -> str:
    subject = report.get("subject") if isinstance(report.get("subject"), dict) else {}
    core = report.get("core_analysis") if isinstance(report.get("core_analysis"), dict) else {}
    metrics = [m for m in (report.get("metrics") or []) if isinstance(m, dict)]
    scopes: List[str] = []
    if core.get("product_records") or core.get("industry_dist"):
        scopes.append("下游产品行业分组")
    if core.get("enterprise_records") or core.get("region_dist"):
        scopes.append("当前企业样本")
    parts = [f"本报告以产品关键词“{_text(subject.get('keywords'))}”为检索对象，按实际返回呈现"
             + ("、".join(scopes) if scopes else "查询边界与数据状态") + "。"]
    failed = _failed_dimensions(core)
    if failed:
        parts.append("以下接口受阻，相关字段与数量缺失：" + "、".join(failed) + "；不据此推断为零或无结果。")
    empty = _empty_dimensions(core)
    if empty:
        empty_text = "以下维度查询成功但未返回记录：" + "、".join(empty) + "；成功空结果不等于接口失败"
        if metrics:
            empty_text += "，相关计数按上游原值保留"
        parts.append(empty_text + "，明细不补造。")
    if metrics:
        parts.append("关键指标包括：" + "、".join(f"{m.get('label')} {m.get('value')}" for m in metrics[:5]) + "。")
    has_industry = bool(core.get("industry_dist"))
    has_region = bool(core.get("region_dist"))
    if has_industry and has_region:
        parts.append("行业分布按下游产品条目统计，企业地域分布按当前样本统计；样本、命中总量与产品条目数不可互相补齐，也不据此推断采购意向。")
    elif has_industry:
        parts.append("行业分布按下游产品条目统计；未返回可用于企业地域分布统计的企业记录，不以缺失补齐，也不据此推断采购意向。")
    elif has_region:
        parts.append("企业地域分布按当前样本统计；未返回可用于行业分布统计的产品记录，不以缺失补齐，也不据此推断采购意向。")
    else:
        parts.append("未获得可用于行业分布或企业地域分布统计的记录；报告仅按实际返回描述查询边界，不以缺失补齐，也不据此推断采购意向。")
    return "".join(parts)


def _has_review_body(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, list, dict, tuple)) and len(value) == 0:
        return False
    return True


def _refresh_quality_report(report: Dict[str, Any]) -> None:
    """Recompute section-fill stats from the final sections and bodies.

    0 counts as populated; only None and empty containers/strings are empty.
    coverage_pct is section fill rate, never an accuracy claim.
    """
    core = report.get("core_analysis") if isinstance(report.get("core_analysis"), dict) else {}
    sections = core.get("sections") if isinstance(core.get("sections"), list) else []
    total = len([s for s in sections if isinstance(s, dict)])
    populated = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        key = section.get("key")
        if key and _has_review_body(core.get(key)):
            populated += 1
    data_source = report.get("data_source")
    if not isinstance(data_source, dict):
        data_source = {}
        report["data_source"] = data_source
    quality = data_source.get("quality_report")
    if not isinstance(quality, dict):
        quality = {}
        data_source["quality_report"] = quality
    quality.update({
        "total_sections": total,
        "populated_sections": populated,
        "empty_sections": total - populated,
        "coverage_pct": round(populated / total * 100) if total else 0,
    })


def apply_content_review(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a reviewed deep copy of a frozen supply report."""
    reviewed = copy.deepcopy(dict(report))
    core = reviewed.get("core_analysis") if isinstance(reviewed.get("core_analysis"), dict) else {}
    _fix_caliber(reviewed)
    product_rows, entries = _fix_products(core)
    enterprises, reasons = _fix_enterprises(core)
    _fix_metrics(reviewed, core, entries, enterprises)
    insights = _build_insights(reviewed, core, entries, enterprises, reasons)
    reviewed["insights"] = insights
    seen, summaries = set(), []
    for insight in insights:
        key = _text(insight.get("interpretation"))
        if key and key not in seen:
            seen.add(key)
            summaries.append(key)
    failed = _failed_dimensions(core)
    empty = _empty_dimensions(core)
    prefix = ["数据缺口：" + "、".join(failed) + "未成功返回，本报告仅呈现成功维度。"] if failed else []
    if empty:
        prefix.append("数据状态：" + "、".join(empty) + "查询成功但未返回记录（空结果，非接口失败）。")
    reviewed["executive_summary"] = prefix + summaries[:5]
    reviewed["abstract"] = _build_abstract(reviewed, entries)
    reviewed["summary"] = reviewed["abstract"]
    _refresh_quality_report(reviewed)
    return reviewed


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply offline content review to a supply report.json")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    input_path = pathlib.Path(args.input).expanduser().resolve()
    output_path = pathlib.Path(args.out_dir).expanduser()
    target = (output_path / "report.json").resolve()
    same = target == input_path
    if not same and target.exists():
        try:
            same = target.samefile(input_path)
        except OSError:
            same = False
    if same:
        raise SystemExit("拒绝写入：--out-dir 的 report.json 指向 --input，冻结源报告不可覆盖")
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from render_report import render_html, render_markdown

    source = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    reviewed = apply_content_review(source)
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(reviewed, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(reviewed), encoding="utf-8")
    (out / "report.html").write_text(render_html(reviewed), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
