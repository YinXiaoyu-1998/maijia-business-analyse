---
name: maijia-business-analyse
description: Fetch, profile, analyze, and report on Maijia Xiaoguan / Meituan POS business exports. Use when Codex needs to obtain Meituan 管家 自助营业取数 data, stream-process large 营业分组表 .xlsx files without loading the full workbook, generate reusable fact tables, derive restaurant operating insights, or produce a McKinsey-style HTML经营诊断报告 for store, channel, member, discount, and daypart analysis.
---

# Maijia Business Analyse

Use this skill to run the Maijia Xiaoguan operating-data workflow end to end:

1. Export `营业分组表` data from Meituan 管家.
2. Stream-profile the large `.xlsx` export into compact fact tables.
3. Generate a visual McKinsey-style HTML operating diagnosis report.
4. Summarize findings with clear data boundaries and action priorities.

## First Principles

- Treat source exports as sensitive private business data. Do not paste row-level records into chat.
- Do not load a huge workbook in full if a streaming script can answer the task.
- Recalculate ratios after aggregation. Do not sum or average precomputed rates unless a weighted denominator is known.
- Separate facts from interpretation: scripts create fact tables; the agent writes management conclusions from those tables.
- Avoid profit or root-cause certainty unless cost, labor, rent, commission, menu margin, and qualitative evidence are available.

## Resource Map

- `scripts/profile_business_data.py`: stream-read a Meituan `.xlsx` and create fact tables plus `analysis_summary.json`.
- `scripts/generate_business_report_html.py`: render a self-contained HTML diagnosis report from the fact tables.
- `scripts/run_pipeline.py`: execute profiling and HTML generation in one command.
- `scripts/download_meituan_signed_url.py`: download an export from an already-authorized signed Meituan/Sankuai URL.
- `references/meituan_export_workflow.zh.md`: read when the user asks to fetch or re-fetch data from Meituan 管家.
- `references/report_style.zh.md`: read before drafting narrative conclusions or changing report structure.
- `analysis_blueprint.md`: detailed Chinese blueprint and metric dictionary from the original analysis work.

## Data Acquisition

When the user asks to fetch new data from Meituan, read `references/meituan_export_workflow.zh.md`.

For business operating facts, use `自助营业取数`:

1. Use the user's logged-in browser session.
2. Open Meituan 管家 report center.
3. Navigate to `自助取数 -> 自助营业取数`.
4. Choose `全量数据`, set `营业日期`, expand filters, and select all fields.
5. Query, export, go to `下载清单`, and download the matching completed row.
6. If Chrome blocks the `s3plus.sankuai.com` temporary URL, use `scripts/download_meituan_signed_url.py`.

For relative date ranges, prefer complete business days. If today is `2026-06-14` and the user asks for “过去七天”, use `2026/06/07-2026/06/13` unless they explicitly want partial current-day data.

When the analysis needs dish-level detail, menu penetration, or attribution that cannot be answered by `营业分组表`, fetch a second export with `自助取数 -> 自助菜品取数`. Select all field groups, query, export, and download the matching `菜品主题数据(日期【...】)` row from `下载清单`. Save it with a stable name such as `documents/maijia_dishes.xlsx`. Use the `maijia-menu-analyse` skill for detailed dish-data handling.

Do not substitute `菜品成本毛利统计` for complete dish information. That report is only suitable when the task specifically needs the cost/gross-profit workbook and its required fields.

When the analysis needs stall/档口 attribution, fetch the dish catalog dimension from `运营中心 -> 菜品管理 -> 菜品库`. Select the target brand, usually `麦家小馆`, click `菜品导出`, choose `导出菜品基础信息`, select all fields, confirm, and save the result with a stable name such as `documents/maijia_dish_catalog.xlsx`.

In Maijia operating analysis, `档口 = 基础分类`. Use the `基础分类` column from the catalog sheet `总部菜品` as the management stall grouping. Treat `打印出品档口`, `出品部门`, and `设置出品部门` as production-routing fields unless the user explicitly asks for kitchen routing.

## Dish And Stall Attribution

Use three layers when dish/stall analysis is required:

1. `营业分组表`: store-week operating facts such as revenue, channel, traffic, tables, AOV, discount, and daypart.
2. `自助菜品取数`: dish-level fact table by date/store/channel/daypart, including dish sales quantity, sales amount, income, discount, order counts, returns, and available cost fields.
3. `菜品库` / `总部菜品`: dish dimension table for stable catalog metadata. Use `基础分类` as `档口`.

Preferred joins:

- Use stable dish identifiers such as `菜品编码（SPUID）`, `菜品编码（SKUID）`, or equivalent dish/SKU code fields when both exports contain them.
- If codes are unavailable, join on normalized `菜品名称` plus `规格名称` when possible, and report potential ambiguity.
- Keep `总部套餐` separate unless you explicitly decompose bundle rows into component dishes using the package composition sheet.

With these sources, a weekly meeting report can drill from `门店 -> 周 -> 渠道/餐段 -> 档口(基础分类) -> 菜品/规格`, and can attribute store revenue changes to specific stall categories before drilling into individual dishes.

## Analysis Pipeline

Run the full pipeline:

```bash
python3 maijia-business-analyse/scripts/run_pipeline.py \
  --input documents/business_data.xlsx \
  --output-dir documents/maijia_business_analysis \
  --report documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆
```

Or run individual steps:

```bash
python3 maijia-business-analyse/scripts/profile_business_data.py \
  --input documents/business_data.xlsx \
  --output-dir documents/maijia_business_analysis

python3 maijia-business-analyse/scripts/generate_business_report_html.py \
  --input-dir documents/maijia_business_analysis \
  --output documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆 \
  --source-name business_data.xlsx
```

Expected fact tables:

- `analysis_summary.json`
- `monthly_trend.csv`
- `store_summary.csv`
- `channel_summary.csv`
- `daypart_summary.csv`
- `member_summary.csv`
- `store_daypart_summary.csv`

## Report Drafting

Before writing or revising management conclusions, read `references/report_style.zh.md`.

Use this default structure:

1. Executive summary: 3-5 answer-first judgments.
2. Data and metric basis: scope, period, rows, stores, caveats.
3. Overall operating baseline: revenue, orders, discount, AOV, membership.
4. Store portfolio: ranking, segmentation, outliers, replication opportunities.
5. Channel quality: dine-in, delivery, pickup, platforms, discount intensity.
6. Daypart opportunities: hour/daypart heatmap and peak/off-peak actions.
7. Dish/stall drilldown when `自助菜品取数` and `菜品库` are available: explain which `基础分类` stalls drive revenue gain/loss and list the top dishes behind each movement.
8. Opportunity pool: 30/60/90 day actions with evidence strength.

Use charts and compact UI over long prose. Keep conclusions short and tied to a metric.

## Validation

After generating an `.xlsx` export:

```bash
file path/to/export.xlsx
unzip -t path/to/export.xlsx
```

After generating fact tables and HTML:

```bash
python3 maijia-business-analyse/scripts/run_pipeline.py --help
python3 maijia-business-analyse/scripts/profile_business_data.py --help
python3 maijia-business-analyse/scripts/generate_business_report_html.py --help
```

Open the HTML report in a browser and check:

- It displays the requested company, date period, row count, store count, and source file.
- Heatmaps and bar charts do not overlap.
- Tables are scrollable and sortable.
- The report does not expose raw row-level data unnecessarily.
