# MCP 工具参考 — supply-mcp-server

本 skill 连接的 MCP server：`handaas-mcp-server/supply-mcp-server`（“HANDAAS供应链潜客推荐服务”）。

> **重要**：本 skill 是**关键词驱动**的，主输入为 ``--keywords``（**产品名称**，多个用英文逗号分隔）。
> 工作流：先用产品关键词查下游产品目录，再结合下游产品关键词查下游企业清单；
> 高级筛选（`advanced_filter_*`）用更通用的企业条件进一步聚焦，支持 ``!`` 前缀表示“不等于/不包含”。

## 通用约定

- `keywords`：供应链系统中具体的产品名称；多个产品名用**英文逗号**分隔（如 `钢材,铝材`）。
- 高级筛选 `address` / `industries` / `enterpriseType` / `name` 支持 `!` 前缀表示非；拆开后向上映射省份/行业。
  - 例：`!北京,!广州市` = 不在北京且不在广州市；`杭州市,南京市` = 等于杭州或等于南京。
- 分页：`pageIndex` 从 1 开始；`supply_get_down_stream_enterprises` 的 `pageSize` 最大 100，`advanced_filter_*` 的 `pageSize` 最大 10、`pageIndex` 最大 50（最多返回 500 条）。

---

## 工具清单

### 1. `supply_get_down_stream_products` — 下游产品

用途：根据产品名称查询下游产品列表（按行业分组）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `keywords` | string | 是 | 产品名称，多个用英文逗号分隔（如 `钢材,铝材`） |

返回（`total` + `resultList`）：每个元素含 `industry`（下游行业）、`products`（该行业下的下游产品 list）。

product_id：`68c02b268cc760ff46ee93c3`。

---

### 2. `supply_get_down_stream_enterprises` — 下游企业

用途：根据产品名称查询下游企业清单，支持主营产品 / 外贸 / 验厂 / 成立时间 / 地区 / 资质 / 注册资本等多维过滤。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `keywords` | string | 是 | 产品名称，多个用英文逗号分隔 |
| `mainProducts` | string | 否 | 下游产品过滤（多个用英文逗号分隔） |
| `isForeignTrade` | string | 否 | 是否外贸企业：是 / 否 |
| `factoryInspectionType` | string | 否 | 是否验厂：是 / 否 |
| `foundTimeStart` / `foundTimeEnd` | string | 否 | 成立时间区间（格式 `yyyy-mm-dd`） |
| `address` | string | 否 | 地区，如 `广东省,深圳市` 或 `广东省` |
| `isTopEnterprise` | string | 否 | 是否500强：是 / 否 |
| `isHighTechEnterprise` | string | 否 | 是否高新企业：是 / 否 |
| `isGazelleEnterprise` | string | 否 | 是否瞪羚企业：是 / 否 |
| `isUnicornEnterprise` | string | 否 | 是否独角兽企业：是 / 否 |
| `hasStock` | string | 否 | 是否上市企业：是 / 否 |
| `hasDevice` | string | 否 | 是否机械设备企业：是 / 否 |
| `hasPack` | string | 否 | 是否包装包材企业：是 / 否 |
| `regCapitalMin` / `regCapitalMax` | int | 否 | 注册资本区间（万人民币） |
| `pageIndex` | int | 否 | 从 1 开始（默认 1） |
| `pageSize` | int | 否 | 单页最多 100（默认 50） |

返回（`total` + `resultList`）：每个企业含 `name`（企业名称）、`mainProducts`（主营产品）、`city` / `province` / `addressValue`（地址）、`foundTime`（成立时间）、`regCapital` / `regCapitalRmb`（注册资本）、`factoryRecommendReason`（推荐理由：headWord 主营、reason 关联原因、tailWord 上游产品）等。

product_id：`68c02fb58cc760ff46ee948e`。

---

### 3. `advanced_filter_get_enterprise_count` — 高级筛选企业数量

用途：通过高级筛选条件查询全国符合要求的企业**数量**（不返回清单）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `operStatus` | string | 否 | 营业状态，如 `营业,吊销` |
| `address` | string | 否 | 地区，支持 `!` 前缀，如 `!北京,!广州市` |
| `industries` | string | 否 | 行业，支持 `!` 前缀，拆开后向上映射行业 |
| `enterpriseType` | string | 否 | 企业类型，如 `个体户,!国有` |
| `name` | string | 否 | 企业名称，如 `汽车,!专卖店` |
| `foundTimeGte` / `foundTimeLte` | string | 否 | 成立时间区间（`2025-01-01`） |
| `regCapitalRmbGte` / `regCapitalRmbLte` | float | 否 | 注册资本区间 |
| `totalPayAmountGte` / `totalPayAmountLte` | float | 否 | 实缴资本区间 |
| `pageIndex` | int | 否 | 最大 50（默认 1） |
| `pageSize` | int | 否 | 最大 10（默认 10） |

返回：`total`（符合条件企业数）、`code`、`msgCN`、`reqInfo`。

product_id：`690342962e32082a0cfd003a`。

---

### 4. `advanced_filter_get_enterprise_list` — 高级筛选企业清单

用途：通过高级筛选条件查询符合要求的企业**清单**（最多返回 500 条）。参数同 `advanced_filter_get_enterprise_count`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| （同 `advanced_filter_get_enterprise_count`） | | | 营业状态 / 地区 / 行业 / 企业类型 / 名称 / 成立时间 / 注册资本 / 实缴资本 / 分页 |

返回（`total` + `resultList`）：每个企业含 `name`、`legalRepresentative`（法定代表人）、`regCapital`（注册资本 dict）、`foundTime`（成立时间）、`isHighTechEnterprise` / `isTopEnterprise` / `isUnicornEnterprise` / `isSpecializedAndNew`（资质标记 0/1）、`homepage`、`socialCreditCode` 等。

product_id：`690367b52e32082a0cfd00ba`。

> 高级筛选的 `!` 前缀表示“不等于/不包含”。

---

## 推荐调用顺序（报告编排）

1. `supply_get_down_stream_products` → 下游产品目录（按行业）。
2. `supply_get_down_stream_enterprises` → 下游企业清单（可加主营产品 / 地区 / 资质 / 注册资本过滤）。
3. （可选）`advanced_filter_get_enterprise_count` + `advanced_filter_get_enterprise_list` → 高级筛选聚焦清单（仅在提供高级筛选条件时调用）。

> 单次报告通常调用 2-4 个工具；主输入始终为产品关键词 `keywords`。
