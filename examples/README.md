# supply-skill：已验收示例

本目录只展示 **4 个完全通过的真实正向场景**（最低要求4例）。

每例均为真实、非空、非缓存调用；技术检查、独立业务检查和离线浏览器检查全部通过。报告保持原实测字节，不把空数据、报错处理或仅生成页面计作通过。

| 场景 | 真实使用需求 | 报告 |
|---|---|---|
| [半导体高新企业潜客](02-chip-high-tech/README.md) | 寻找芯片封装材料的高新技术下游企业，重点关注长三角地区。 | [HTML](02-chip-high-tech/report.html) / [MD](02-chip-high-tech/report.md) / [JSON](02-chip-high-tech/report.json) |
| [光伏组件下游市场扫描](07-solar-components/README.md) | 扫描光伏玻璃和铝边框的下游产品及企业，了解潜在客户行业分布。 | [HTML](07-solar-components/report.html) / [MD](07-solar-components/report.md) / [JSON](07-solar-components/report.json) |
| [钢铝下游行业—产品映射](09-steel-aluminum-product-map/README.md) | 请查询钢材和铝材对应的下游行业与具体产品，用于整理应用场景词表；不要承诺返回企业名单或采购线索。 | [HTML](09-steel-aluminum-product-map/report.html) / [MD](09-steel-aluminum-product-map/report.md) / [JSON](09-steel-aluminum-product-map/report.json) |
| [工业机器人下游应用与关系样本](10-industrial-robot-downstream-relations/README.md) | 请查询工业机器人的下游应用行业、当前页候选企业和产品关联理由；不要启用高级筛选，也不要认定采购意向或合格供应商。 | [HTML](10-industrial-robot-downstream-relations/report.html) / [MD](10-industrial-robot-downstream-relations/report.md) / [JSON](10-industrial-robot-downstream-relations/report.json) |

- [逐例验收结果](results.json) · [业务复核](review.json) · [证据摘要](evidence-index.json)
- [完整测试记录](../test-records/live-replaced-20261027/README.md)仅用于审计，不属于可展示示例。
- 当前数据与结论限于原查询时点及公开样本；覆盖率不代表准确率或低风险。
