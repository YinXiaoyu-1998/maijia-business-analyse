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
- For weekly/monthly meeting reports, `业务收入` / `收入` must use `营业分组表.订单营业收入` (`net_revenue`), not `营业额(元)` (`gross_sales`). Keep `gross_sales` only as a separately labeled source/diagnostic field when explicitly needed.
- Separate facts from interpretation: scripts create fact tables; the agent writes management conclusions from those tables.
- Avoid profit or root-cause certainty unless cost, labor, rent, commission, menu margin, and qualitative evidence are available.

## Store Size Buckets

麦家小馆门店必须按经营容量分为大店和小店。凡是做门店横向比较、门店分型、收入中位数、折扣率中位数、客单价中位数、明星/问题门店识别、问题门店归因 Top 列表、经营动作提示时，都必须在同一个 bucket 内比较；不要把大店和小店混在一个中位数或平均值样本池里。

- 小店：龙玥城店、文化园店、苏州街店、常营店、通州保利店
- 大店：荣京道店、经海路店、国粹苑店、上海沙龙店

不需要额外拆分大小店的内容：全体 KPI 总览、单店自身同比/环比、最近 16 周趋势、24 小时时段收入、堂食/外卖结构、时段归因本身。若这些模块引用“明星/问题门店”，则其分型来源必须使用大小店 bucket 内的结果。

## Resource Map

- `scripts/profile_business_data.py`: stream-read a Meituan `.xlsx` and create fact tables plus `analysis_summary.json`.
- `scripts/generate_business_report_html.py`: render a self-contained HTML diagnosis report from the fact tables.
- `scripts/run_pipeline.py`: execute profiling and HTML generation in one command.
- `scripts/profile_weekly_meeting_data.py`: stream-read weekly meeting business inputs into comparison, channel, daypart, dish sales mix, and attribution fact tables.
- `scripts/generate_weekly_meeting_report_html.py`: render the full weekly meeting HTML with trend, store-size-bucketed quadrant/ranking, channel, dish sales mix, driver, hourly revenue, and daypart attribution sections.
- `scripts/run_weekly_meeting_report.py`: execute the weekly meeting profiling and full HTML generation in one command.
- `scripts/profile_monthly_meeting_data.py`: stream-read monthly meeting business inputs into month-level comparison, 6-month trend, channel, daypart, dish sales mix, and attribution fact tables.
- `scripts/generate_monthly_meeting_report_html.py`: render the full monthly meeting HTML with month-level trend, quadrant, channel, dish sales mix, driver, hourly revenue, and daypart attribution sections.
- `scripts/run_monthly_meeting_report.py`: execute the monthly meeting profiling and full HTML generation in one command.
- `scripts/profile_monthly_profit_data.py`: stream-read a monthly profit workbook plus business exports and derive store-month profit-rate facts.
- `scripts/generate_monthly_profit_report_html.py`: render a standalone, self-contained monthly profit / profit-rate chart report.
- `scripts/run_monthly_profit_report.py`: execute the standalone profit report pipeline in one command.
- `scripts/download_meituan_signed_url.py`: download an export from an already-authorized signed Meituan/Sankuai URL.
- `references/meituan_export_workflow.zh.md`: read when the user asks to fetch or re-fetch data from Meituan 管家.
- `references/report_style.zh.md`: read before drafting narrative conclusions or changing report structure.
- `analysis_blueprint.md`: detailed Chinese blueprint and metric dictionary from the original analysis work.

## Data Acquisition

When the user asks to fetch new data from Meituan, read `references/meituan_export_workflow.zh.md`.

Before opening Meituan, first check whether the correctly named local raw export already exists under `documents/raw_exports/` and validate it with `file` / `unzip -t` when practical. If the local file is missing, outdated, has the wrong date range, or may lack required fields, create a fresh export from the relevant Meituan report page by following the workflow below.

Do not begin by browsing Meituan `下载清单` for old download records. Historical download-list rows may have the wrong date range, stale data, or missing fields. Use `下载清单` only after you have just configured the report, selected the required fields, clicked `查询`, and created a new export task; then download the row whose report name, date range, and creation/update time match that fresh task.

For business operating facts, use `自助营业取数`:

1. Use the user's logged-in browser session.
2. Open Meituan 管家 report center.
3. Navigate to `自助取数 -> 自助营业取数`.
4. Choose `全量数据`, set `营业日期`, expand filters, and select all fields.
5. Query, export, go to `下载清单`, and download the matching completed row.
6. If Chrome blocks the `s3plus.sankuai.com` temporary URL, use `scripts/download_meituan_signed_url.py`.

For weekly meeting reports, the business operating export must be a long-period `营业分组表`, not only a short current-week export. The long-period export must cover every business date needed by the full weekly HTML, including:

- the current week requested by the user;
- the previous comparison week;
- the year-over-year comparison week;
- the full trend window shown by the report, normally the recent 16 complete weekly buckets for the current year and the aligned prior-year period.

Prefer one or more long-period `营业分组表` exports that together cover the full current-year and prior-year trend windows. Let `profile_weekly_meeting_data.py` aggregate the current week, previous week, YoY week, and trend buckets from those long-period inputs. Do not shrink the business inputs to only current/previous/YoY week slices, because that breaks the 16-week trend section.

If a precise current-week export is also available, use it only for validation or as a replacement after removing the overlapping current-week rows from the long-period input. Never solve duplicate-count risk by discarding non-overlapping trend weeks. When in doubt, keep the long-period export as the source of truth and derive the current week from it.

For relative date ranges, prefer complete business days. If today is `2026-06-14` and the user asks for “过去七天”, use `2026/06/07-2026/06/13` unless they explicitly want partial current-day data.

Save all raw downloaded files under `documents/raw_exports/` with these names:

- Business operating export: `maijia_business_YYYYMMDD_YYYYMMDD.xlsx`
- Dish sales export: `maijia_dishes_YYYYMMDD_YYYYMMDD.xlsx`
- Dish catalog export: `maijia_dish_catalog_YYYYMMDD.xlsx`
- If a date range is split across multiple exports, append `_part01`, `_part02`, etc. before `.xlsx`.

Keep the date range in dish export filenames accurate. The weekly profiling script can use the `maijia_dishes_YYYYMMDD_YYYYMMDD.xlsx` / `_partNN` filename range as the inspection date coverage and skip an otherwise expensive first full-workbook scan before the actual attribution pass. If a dish file is not named with this pattern, the script falls back to scanning the workbook rows to infer dates.

Some large Meituan/WPS exports may paginate a single `.xlsx` across multiple worksheets, such as `菜品主题数据` and `菜品主题数据-2`, while keeping the same title/filter/header rows on each sheet. Treat these worksheets as one logical export. The weekly profiling script is expected to stream every matching worksheet in the workbook; do not assume `sheet1.xml` alone is complete. When filename date ranges prove that a dish export is fully outside the current, previous, and YoY attribution windows, the weekly profiler can skip that entire file instead of scanning every row.

When the weekly or monthly meeting report should include the `销售额菜品比例` pie chart, fetch a second export with `自助取数 -> 自助菜品取数`. Select all field groups, query, export, and download the matching `菜品主题数据(日期【...】)` row from `下载清单`. Save it as `documents/raw_exports/maijia_dishes_YYYYMMDD_YYYYMMDD.xlsx`. Use the `maijia-menu-analyse` skill for deeper menu penetration or dish-level root-cause work beyond this share chart.

## Daypart Attribution

Weekly and monthly meeting reports use `营业分组表` daypart attribution instead of stall/dish attribution. The required dimension is the business-export field named `时段`; when `餐段` is also present, aggregate by `门店名称 -> 餐段 -> 时段`.

Use the same comparison windows as the report:

1. Current period: 本周 or 本月.
2. Previous period: 环比周 or 上月.
3. Year-over-year period: 同比周 or 去年同月.

For each store and each comparison basis, calculate the revenue delta after aggregating `订单营业收入` by `餐段 + 时段`. Show the largest negative time slots and largest positive time slots, similar to the former stall attribution table:

- 环比时段归因: 本期 minus previous period.
- 同比时段归因: 本期 minus year-over-year period.
- Negative slots are the largest revenue decreases; positive slots are the largest revenue increases.

This attribution identifies when the revenue change occurred. It does not claim why the change happened. Do not describe dish, menu, kitchen, or stall causes unless a separate dish-level analysis is explicitly requested and supported by `自助菜品取数`.

## Dish Sales Mix

Weekly and monthly meeting reports can show `销售额菜品比例` when a matching `菜品主题数据` export is provided through `--dish-input`.

Use this exact口径:

- Denominator: `营业分组表.店内营业收入`, aggregated for the report's current period and selected store.
- Numerator: `菜品主题数据.菜品收入`, filtered to `订单分类 = 店内销售`, aggregated by `菜品名称` for the same current period and selected store.
- Display: pie chart with the top 10 dishes by share; aggregate all remaining current-period dish income into `其他`.
- Scope: include `全体门店` plus each store. Do not use `菜品销售额` for this module because it does not match the profit-analysis sales/revenue口径.
- Catalog: no菜品库 is required. Do not map dishes to档口 for this module.

## Weekly Meeting Report Guardrail

When the user asks for a weekly report, weekly meeting report, 周报, 周会 HTML, or a report for a specific current/previous/YoY comparison window, always use `scripts/run_weekly_meeting_report.py` or its two underlying scripts. This is the full weekly HTML pipeline.

Do not create a one-off baseline/ad hoc report for these requests. Do not use or imitate historical outputs under `documents/maijia_weekly_baseline_analysis/`, filenames like `maijia_weekly_baseline_report_*.html`, or screenshots named `maijia_weekly_baseline_report_*.png`. Those are historical temporary artifacts, not the current reporting standard.

For weekly reports, require long-period business inputs. The `--input` files must include `营业分组表` coverage for the report's complete 16-week current-year trend window and aligned prior-year trend window, plus the requested current/previous/YoY comparison windows. The current week should be derived from the long-period business input whenever possible. Do not use only three short exports for current week, previous week, and YoY week as the business input set; that may make comparison tables look complete while leaving the "最近 16 周收入趋势" chart mostly empty.

If overlapping business exports must be combined, remove or exclude only the duplicated date range before profiling. Do not cut away unrelated dates that are needed for trend charts. Prefer complete long-period coverage over short-window convenience, even when the long file is large; the profiling scripts are designed to stream large workbooks.

If a raw `.xlsx` contains multiple worksheets with the same report title, such as `营业分组表-2` or `菜品主题数据-2`, keep the workbook intact and pass the file once. The weekly profiler should combine all matching worksheets in that file and still use filename/date overlap rules only between separate input files.

Pass `--dish-input` when the weekly report should include the `销售额菜品比例` pie chart. The dish export should cover at least the current week. Do not pass `--catalog` for this module; the current weekly report uses daypart attribution from `营业分组表.时段` and does not generate档口归因.

## Monthly Meeting Report Guardrail

When the user asks for a monthly report, 月报, 月会 HTML, or a month-level current/previous/YoY comparison, use `scripts/run_monthly_meeting_report.py` or its two underlying scripts. Do not repurpose the weekly meeting pipeline and merely pass month date ranges, because the weekly pipeline's trend buckets, filenames, and report language are week-specific.

Monthly reports use these comparison windows:

- current month requested by the user, normally a complete natural month;
- previous month for MoM comparison;
- the same calendar month in the previous year for YoY comparison;
- a 6-month trend window ending at the current month, plus aligned prior-year months when covered by the business inputs.

For monthly reports, pass long-period `营业分组表` inputs covering the current month, previous month, YoY month, and the 6-month current-year/prior-year trend windows. The monthly profiler writes month-level fact tables and uses natural-month buckets. Pass `--dish-input` when the monthly report should include the `销售额菜品比例` pie chart; the dish export should cover at least the current month. Do not pass `--catalog` for this module; the attribution section uses `营业分组表.时段` and compares 本月 / 上月 / 去年同月 at store-daypart level.

## Analysis Pipeline

Run the full pipeline:

```bash
python3 maijia-business-analyse/scripts/run_pipeline.py \
  --input documents/raw_exports/maijia_business_YYYYMMDD_YYYYMMDD.xlsx \
  --output-dir documents/maijia_business_analysis \
  --report documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆
```

Or run individual steps:

```bash
python3 maijia-business-analyse/scripts/profile_business_data.py \
  --input documents/raw_exports/maijia_business_YYYYMMDD_YYYYMMDD.xlsx \
  --output-dir documents/maijia_business_analysis

python3 maijia-business-analyse/scripts/generate_business_report_html.py \
  --input-dir documents/maijia_business_analysis \
  --output documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆 \
  --source-name maijia_business_YYYYMMDD_YYYYMMDD.xlsx
```

For the weekly meeting report with daypart attribution, run:

```bash
python3 maijia-business-analyse/scripts/run_weekly_meeting_report.py \
  --input documents/raw_exports/maijia_business_CURRENT_TREND_START_CURRENT_END.xlsx \
          documents/raw_exports/maijia_business_YOY_TREND_START_YOY_END.xlsx \
  --dish-input documents/raw_exports/maijia_dishes_CURRENT_START_CURRENT_END.xlsx \
  --output-dir documents/maijia_weekly_meeting_analysis \
  --report documents/maijia_weekly_meeting_analysis/maijia_weekly_meeting_report.html \
  --company 麦家小馆 \
  --current-start YYYY/MM/DD \
  --current-end YYYY/MM/DD \
  --previous-start YYYY/MM/DD \
  --previous-end YYYY/MM/DD \
  --yoy-start YYYY/MM/DD \
  --yoy-end YYYY/MM/DD
```

The weekly report always attempts daypart attribution from the business inputs. `--dish-input` enables the `销售额菜品比例` pie chart; `--catalog` is not needed and is ignored by the standard report logic.

For the monthly meeting report with daypart attribution, run:

```bash
python3 maijia-business-analyse/scripts/run_monthly_meeting_report.py \
  --input documents/raw_exports/maijia_business_CURRENT_TREND_START_CURRENT_END.xlsx \
          documents/raw_exports/maijia_business_YOY_TREND_START_YOY_END.xlsx \
  --dish-input documents/raw_exports/maijia_dishes_CURRENT_START_CURRENT_END.xlsx \
  --output-dir documents/maijia_monthly_meeting_analysis \
  --report documents/maijia_monthly_meeting_analysis/maijia_monthly_meeting_report.html \
  --company 麦家小馆 \
  --current-start YYYY/MM/01 \
  --current-end YYYY/MM/DD \
  --previous-start YYYY/MM/01 \
  --previous-end YYYY/MM/DD \
  --yoy-start YYYY/MM/01 \
  --yoy-end YYYY/MM/DD \
  --trend-months 6
```

The monthly report always attempts daypart attribution from the business inputs. `--dish-input` enables the `销售额菜品比例` pie chart; `--catalog` is not needed and is ignored by the standard report logic.

## Monthly Profit And Profit-Rate Report Guardrail

When the user asks for a standalone 利润表、净利润趋势、利润率趋势、利润/利润率 HTML, use `scripts/run_monthly_profit_report.py`. This is a separate profit-report workflow and must not be folded into the weekly, monthly-meeting, or business-diagnosis report.

Metric rules:

- Preserve blank profit-workbook cells as `无数据／门店尚未开业`; do not convert them to zero or connect the line across them.
- Keep the X-axis fixed at January through December for every selected year.
- Calculate a monthly profit rate only after summing `店内营业收入` across every business-export detail row for the matching store and natural month: `净利润 ÷ 当月店内营业收入汇总`.
- Never average detail-row rates or precomputed rates.
- Map user-provided profit-sheet store labels explicitly to business-export store names. For the current 麦家小馆 convention: `保利店 -> 门店名称包含通州保利`.
- If business data begins partway through a month, leave that month’s profit rate blank unless the user explicitly requests a partial-month rate. For the current data set, keep 2024-06 and earlier blank.

Example:

```bash
python3 maijia-business-analyse/scripts/run_monthly_profit_report.py \
  --profit-file documents/tables/maijia_month_profit_202301_202606.xlsx \
  --business-input documents/raw_exports/maijia_business_20240101_20241031.xlsx \
                   documents/raw_exports/maijia_business_20241101_20250131.xlsx \
                   documents/raw_exports/maijia_business_20250201_20250625.xlsx \
                   documents/raw_exports/maijia_business_20250626_20260625.xlsx \
                   documents/raw_exports/maijia_business_20260626_20260628.xlsx \
                   documents/raw_exports/maijia_business_20260629_20260630.xlsx \
  --output-dir documents/maijia_month_profit_analysis \
  --report documents/maijia_month_profit_analysis/maijia_month_profit_report.html
```

Expected fact tables:

- `analysis_summary.json`
- `monthly_trend.csv`
- `store_summary.csv`
- `channel_summary.csv`
- `daypart_summary.csv`
- `member_summary.csv`
- `store_daypart_summary.csv`

Weekly meeting fact tables:

- `weekly_store_metrics.csv`
- `weekly_store_channel_metrics.csv`
- `weekly_store_daypart_metrics.csv` for the weekly report's store-selectable 24-hour revenue chart; the HTML aggregates this by `时段` only and does not display the `餐段` dimension.
- `weekly_store_daypart_comparison.csv` for 本周 / 环比周 / 同比周 daypart revenue comparisons by `门店名称 + 餐段 + 时段`
- `weekly_store_daypart_driver_summary.csv` for each store's largest negative and positive daypart drivers by 环比 and 同比
- `weekly_store_dish_sales_mix.csv` when `--dish-input` is provided; stores current-period dish收入 and店内营业收入 shares for `全体门店` and each store
- `weekly_trend_comparison_metrics.csv`
- `weekly_store_comparison.csv`
- `store_driver_summary.csv`
- `star_problem_stores.csv` with `store_size`; weekly reports classify stores inside the 大店 / 小店 bucket, using bucket-specific revenue, discount-rate, and AOV medians.

Monthly meeting fact tables:

- `monthly_meeting_summary.json`
- `monthly_store_metrics.csv`
- `monthly_store_channel_metrics.csv`
- `monthly_store_daypart_metrics.csv`
- `monthly_store_daypart_comparison.csv` for 本月 / 上月 / 去年同月 daypart revenue comparisons by `门店名称 + 餐段 + 时段`
- `monthly_store_daypart_driver_summary.csv` for each store's largest negative and positive daypart drivers by 环比 and 同比
- `monthly_store_dish_sales_mix.csv` when `--dish-input` is provided; stores current-period dish收入 and店内营业收入 shares for `全体门店` and each store
- `monthly_trend_comparison_metrics.csv`
- `monthly_store_comparison.csv`
- `store_driver_summary.csv`
- `star_problem_stores.csv`

## Report Drafting

Before writing or revising management conclusions, read `references/report_style.zh.md`.

Use this default structure:

1. Executive summary: 3-5 answer-first judgments.
2. Data and metric basis: scope, period, rows, stores, caveats.
3. Overall operating baseline: revenue, orders, discount, AOV, membership.
4. Store portfolio: ranking, segmentation, outliers, replication opportunities; ranking, segmentation, and quadrant judgments must compare 大店 only with 大店 and 小店 only with 小店.
5. Channel quality: dine-in, delivery, pickup, platforms, discount intensity.
6. Dish sales mix: current-period店内营业收入 by dish, Top 10 plus `其他`, with all-store and single-store views when dish input is available.
7. Hourly revenue opportunities: 24-hour revenue bar chart, with a dropdown for all stores or each single store, and peak/off-peak actions.
8. Daypart attribution: explain which `餐段 + 时段` combinations drive each store's biggest revenue gain/loss in 环比 and 同比.
9. Opportunity pool: 30/60/90 day actions with evidence strength.

Use charts and compact UI over long prose. Keep conclusions short and tied to a metric.

### 通用折线图视觉规范

所有由本 skill 生成的折线图都使用同一规则：折线与普通数据点为黄色；每条有效数据序列的最低点为红色、最高点为蓝色；只有一个有效点或最高/最低值完全相同的序列保持普通黄色。若同一图中有当前期和上一期/同期两个序列，当前期使用实线，对比序列使用虚线；两条线仍遵循各自的极值配色。

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
- Hourly bar charts, trend charts, heatmaps, and tables do not overlap.
- Tables are scrollable and sortable.
- The report does not expose raw row-level data unnecessarily.
