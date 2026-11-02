---
name: supply-report
description: Use for generating a professional supply-chain prospect report (供应链潜客推荐报告) from the HandaaS supply MCP — covering 下游产品、下游企业明细、高级筛选企业清单. Driven by a product keyword (--keywords, comma-separated product names). Trigger when users ask for “供应链潜客推荐报告”, “潜客推荐报告”, “找下游客户”, “下游产品分析”, “下游企业清单”, “高级筛选企业”, or “按产品找客户”. Infer intent, pick the right MCP tools, and produce HTML + Markdown + JSON reports automatically. MCP 服务名称触发词：供应链潜客推荐服务。
---

# 供应链潜客推荐报告

## 用户契约

把“供应链潜客推荐报告”作为面向用户的调用短语。`supply-report` 仅为内部包名。

当本 skill 处于激活状态：

1. 不要向用户索要 product_id、MCP 工具名、API 字段、内部参数或凭证信息；只接受产品关键词、（可选）主营产品 / 地区 / 资质 / 注册资本 / 高级筛选条件。
2. 接受自然目标，例如“帮我找钢材的下游客户”“给我一份铝材的供应链潜客报告”“找上海的高新下游企业”“按产品找下游清单”。
3. 供应链报告以**产品关键词**为主输入（`--keywords`，多个产品名用英文逗号分隔），先查下游产品目录，再查下游企业清单。
4. `factoryInspectionType` / `isFactoryEnterprise` 仅作为归纳样本的平台字段统计，不称为供应商资质，也不推断采购适配、产能或合作风险。
5. 下游企业章节同时保留上游 total 与实际纳入明细条数；明细按 `--max-pages`（默认 1）预算内翻页，未取全时如实披露剩余条数，不用 `N` 占位，也不把部分样本写成全量清单。
6. 全部真实调用受「付费调用与预算约束」约束：先推演所需结论、维度与页数预算，优先聚合接口，同一 tool+相同参数只调用一次。
7. 优先使用 MCP 连接（`SUPPLY_MCP_URL` Remote MCP 或本地 `handaas-mcp-server/supply-mcp-server`）；不要让用户处理签名或凭证。
8. 同时产出 HTML（可分享交付）、Markdown（知识库 / wiki）、JSON（系统集成）三类产物。
9. 报告正文必须是专业研究报告风格：只见供应链事实与结构化数据，绝不出现工具名、入参、product_id、内部字段或空表。
10. 绝不打印 `secret_id`、`secret_key`、签名、token 或原始签名请求。
11. 默认 dry-run；真实付费 / 凭证调用需用户明确要求且 MCP 连接配置完整。
12. 数据为空时明确说明数据范围 / 口径，不渲染空表、不臆造事实。


- MCP 返回的嵌套 JSON 字符串（如金额 `{"coinType":"人民币","value":430000000.0}`、地址 `{"city":"杭州市",...}`）必须解析为可读文本（如"4.30 亿 人民币"、"浙江省杭州市"），绝不在报告正文、表格或指标中输出原始 JSON 字符串。
- 报告所有章节标题、指标卡标签必须用中文；`core_analysis.sections` 的 `title` 字段必须中文，不可显示英文 key（如 `holders`、`investments`）。
- 指标值必须可读化：金额格式为"X 亿/万 + 币种"，地址拼接省市区，比率显示百分号。详见 `references/report-output.md` 的「数据格式约束」。

## MCP 服务入口

- MCP 服务当前名称：供应链潜客推荐服务（连接仍使用原服务目录标识）。

- 上游 MCP 项目：`handaas-mcp-server/supply-mcp-server`（位于 `HANDAAS_MCP_SERVER_ROOT` 或本仓库同级目录）。
- Remote MCP：设置环境变量 `SUPPLY_MCP_URL`（streamable-http），可选 `SUPPLY_MCP_TOKEN`。
- 本地 MCP：设置 `HANDAAS_MCP_SERVER_ROOT` 指向 `handaas-mcp-server` 仓库根目录；该 server 自己的 `.env` 提供 `INTEGRATOR_ID` / `SECRET_ID` / `SECRET_KEY`。
- 首次真实查询前，运行 `scripts/mcp_client.py ping` 与 `scripts/mcp_client.py list-tools` 验证连通。

## 按需加载 references

- 不清楚该 MCP 有哪些工具、参数、返回字段、何时调用：`references/mcp-tools-reference.md`。
- 报告结构、章节、质量底线、渲染工作流：`references/report-output.md`。

## 付费调用与预算约束（必读）

1. 每次业务工具调用与每次明细翻页都可能计费；想要 total/页数只是为了精确规划，不构成默认全量拉取的授权。
2. 调用前先推演所需结论与数据维度，确定工具/参数计划、必要页数与最大调用预算。total 未知时，第一个必要明细页既是数据又是 total 探测，绝不为此重复付费。
3. 优先用统计/聚合接口回答问题；只在结论、图表、代表记录或明确全量/计数需求确实需要时才取企业清单明细。高级筛选企业数量直接取自清单接口返回的 total（参数一致、口径相同），不单独购买 `advanced_filter_get_enterprise_count`。
4. 用 schema 允许的最大合理 pageSize 取所需行数，证据/样本目标满足即停，且不超过明确预算。更多调用必须有具体缺失结论支撑，不因为"补齐所有章节"而追加；不得用样本分布冒充全量结论。预算不足以支撑关键结论时，先说明证据缺口与预计额外调用数，等明确授权后再扩大——不得静默降级结论，也不得静默扩大计费范围。
5. 当前任务/报告内复用相同请求（含第一页规划数据）：同一 tool+相同参数只调用一次；不要为渲染重跑 compose/MCP——用已保存 JSON 本地重渲染；不得自动重试、重复取统计/明细或并行获取相同数据；补充查询先列明缺口并复用已返回记录。
6. `total_pages`/`remaining_pages` 是按请求 pageSize 的估算；短但非空的页仍有剩余记录时在预算内继续。只有稳定有效 total 与实际扫描数一致才算完整采集；报错、提前空页、重复页、total 变更/缺失、数量溢出均为不完整。显式预算或样本目标停止即部分采集，绝不宣称全量。不调用无关或不必要维度的工具。

本 skill 分页明细接口：`supply_get_down_stream_enterprises`（pageSize≤100）与 `advanced_filter_get_enterprise_list`（pageSize≤10、pageIndex≤50），预算经 `--max-pages`（默认 1）传递；`supply_get_down_stream_products` 为单次调用；`advanced_filter_get_enterprise_count` 不调用（企业数量直接取自清单接口 total，参数一致、口径相同）。

## 意图路由

| 用户意图 | 内部工作流 |
| --- | --- |
| 按产品关键词找下游产品 + 下游企业 | `compose_report.py --keywords ...` |
| 下游企业 + 过滤（主营产品 / 地区 / 资质 / 注册资本） | `compose_report.py --keywords ... --main-products/--address/--is-high-tech/--reg-capital-min/--max ...` |
| 高级筛选聚焦（地区 / 企业类型，支持 `!` 前缀） | `compose_report.py --keywords ... --advanced-address/--enterprise-type ...` |
| 只看下游产品 / 只看下游企业 | 仅调对应工具，按统一骨架组装 |
| 只要 JSON / 只要 HTML / 只要 Markdown | 用 `--output`（JSON）或 `--report-output`（HTML+MD），或 `render_report.py` 重渲染 |
| 连接 / 工具不存在 / 传参错误 | `mcp_client.py ping` / `list-tools` 排查；报脱敏后的缺失项 |

## Golden path for 供应链潜客推荐报告

1. **解析产品关键词**：`--keywords` 必填，多个产品名用英文逗号分隔（如 `钢材,铝材`）。
2. **调用供应链工具**：`supply_get_down_stream_products`（下游产品目录）、`supply_get_down_stream_enterprises`（下游企业清单，可加过滤）、（可选）`advanced_filter_get_enterprise_count` + `advanced_filter_get_enterprise_list`（高级筛选聚焦，仅在提供高级筛选条件时）。
3. **组装统一报告**：核心分析含下游产品（表）、下游企业明细（表）、高级筛选企业清单（表，可选）。
4. **渲染三件套**：`compose_report.py --keywords ... [filters] --output ... --report-output ...` 直接产出 JSON + HTML + Markdown。
5. **返回路径**：返回 JSON、HTML、Markdown 文件路径，以及产品关键词映射与数据口径。

## 脚本速查

```bash
# 校验连接配置（脱敏）
python scripts/validate_config.py --allow-placeholders

# 连通性自测
python scripts/mcp_client.py ping
python scripts/mcp_client.py list-tools

# 干跑（不调真实 API，用样例数据组装报告骨架）
python scripts/compose_report.py \
  --keywords "钢材,铝材" \
  --dry-run \
  --output output/supply.json \
  --report-output output/supply.html

# 真实查询 + 渲染（需 MCP 连接就绪）
python scripts/compose_report.py \
  --keywords "钢材,铝材" \
  --max-pages 1 \
  --output output/supply.json \
  --report-output output/supply.html

# 下游企业 + 过滤（主营产品 / 地区 / 资质 / 注册资本）
python scripts/compose_report.py \
  --keywords "钢材,铝材" --main-products "汽车车身" --address "上海" \
  --is-high-tech 是 --reg-capital-min 5000 \
  --report-output output/supply_filtered.html

# 高级筛选聚焦（地区/企业类型，支持 ! 前缀）
python scripts/compose_report.py \
  --keywords "钢材,铝材" --advanced-address "!北京,!广州市" --enterprise-type "个体户,!国有" \
  --report-output output/supply_advanced.html

# 手动调单个工具
python scripts/mcp_client.py call-tool \
  --tool supply_get_down_stream_products \
  --arguments-json '{"keywords": "钢材,铝材"}'

# 重渲染已有 JSON
python scripts/render_report.py --input output/supply.json --output output/supply.html
python scripts/render_report.py --input output/supply.json --output output/supply.md
```

## 输出字段

- `subject`：产品关键词、过滤条件（主营产品 / 地区 / 资质 / 注册资本 / 高级筛选）。
- `abstract` / `summary`：封面摘要与详细摘要。
- `metrics`：下游产品数、下游企业数、高级筛选企业数。
- `caliber`：匹配对象、匹配方式、数据范围、产品、局限。
- `core_analysis`：下游产品（表）、下游企业明细（表）、高级筛选企业清单（表，可选）。
- `representative_records`：代表性下游企业记录（企业名称 / 主营产品 / 城市）。
- `insights`：结构化解读（下游产品广度 / 潜在客户规模 / 下游行业分布 / 地域集中度 / 高级筛选聚焦）。
- `data_source`：MCP server、数据产品、生成时间、是否 dry-run。

若 API 调用失败，明确报出缺失的配置 / 缺失的工具 / MCP 错误 / 参数校验错误 / 上游网络错误，给出 dry-run 命令或配置步骤，绝不暴露密钥。
