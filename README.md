# maijia-business-analyse

A reusable skill for Maijia Xiaoguan / Meituan POS business analysis. It helps agents export Meituan `营业分组表` data, stream-process large `.xlsx` files, generate compact fact tables, and produce a visual McKinsey-style HTML operating diagnosis report.

## What It Does

- Guides data export from Meituan 管家 `自助营业取数`.
- Notes when to fetch `自助菜品取数` for dish-level penetration and attribution.
- Documents how to export `菜品库` basic information and use `基础分类` as the stall/档口 dimension.
- Processes large Excel exports without loading the whole workbook into memory.
- Builds fact tables for stores, channels, dayparts, members, and monthly trends.
- Generates a self-contained HTML report with KPI cards, bar charts, scatter plots, heatmaps, sortable tables, and an opportunity pool.
- Can be reused by Codex, Claude Code, Cursor, or similar coding agents.

## Installation

### Codex

Copy the whole folder into the Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R maijia-business-analyse ~/.codex/skills/
```

Restart or refresh Codex, then invoke it with `$maijia-business-analyse`.

### Claude Code / Cursor / Other Agents

Place this folder somewhere the agent can read and prompt it with:

```text
Use the skill at /path/to/maijia-business-analyse to analyze Meituan business data and generate the HTML operating diagnosis report.
```

## Usage

### 1. Fetch Business Data

Read `references/meituan_export_workflow.zh.md`. The core workflow is:

1. Open Meituan 管家 report center.
2. Go to `自助取数 -> 自助营业取数`.
3. Select `全量数据`, set business dates, expand filters, and select all fields.
4. Query, then click the report-page `导出` button to create an export task.
5. Open `下载清单记录`, find the row whose date range and request time match the task.
6. After the status becomes `导出完成`, click `下载` in that row's far-right `操作` column; it is usually next to `删除` and is not the report-page `导出` button.

If Chrome blocks the temporary `s3plus.sankuai.com` URL, copy the signed URL and run:

```bash
python3 scripts/download_meituan_signed_url.py \
  --url '<signed-s3plus-url>' \
  --output documents/raw_exports/maijia_business_YYYYMMDD_YYYYMMDD.xlsx
```

### Raw Export Naming

Save all raw downloaded files under `documents/raw_exports/`:

| Export | File name |
|---|---|
| `自助营业取数` / `营业分组表` | `maijia_business_YYYYMMDD_YYYYMMDD.xlsx` |
| `自助菜品取数` / `菜品主题数据` | `maijia_dishes_YYYYMMDD_YYYYMMDD.xlsx` |
| `菜品库` / `导出菜品基础信息` | `maijia_dish_catalog_YYYYMMDD.xlsx` |

For split downloads, append `_part01`, `_part02`, etc. before `.xlsx`.

When dish-level penetration, menu attribution, or "穿透到菜品" is required, use the same reference file and fetch `自助取数 -> 自助菜品取数`. Select all field groups and download the matching `菜品主题数据(日期【...】)` row from `下载清单记录`, then save it with the standard name such as `documents/raw_exports/maijia_dishes_20260614_20260620.xlsx`.

When stall/档口 attribution is required, also export the dish catalog from `运营中心 -> 菜品管理 -> 菜品库 -> 菜品导出 -> 导出菜品基础信息`. Select the target brand, usually `麦家小馆`, choose all fields, and save it with the standard name such as `documents/raw_exports/maijia_dish_catalog_20260626.xlsx`. In this analysis workflow, `档口 = 基础分类`.

### 2. Run the Full Pipeline

```bash
python3 scripts/run_pipeline.py \
  --input documents/raw_exports/maijia_business_YYYYMMDD_YYYYMMDD.xlsx \
  --output-dir documents/maijia_business_analysis \
  --report documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆
```

### 3. Run Step by Step

```bash
python3 scripts/profile_business_data.py \
  --input documents/raw_exports/maijia_business_YYYYMMDD_YYYYMMDD.xlsx \
  --output-dir documents/maijia_business_analysis

python3 scripts/generate_business_report_html.py \
  --input-dir documents/maijia_business_analysis \
  --output documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆 \
  --source-name maijia_business_YYYYMMDD_YYYYMMDD.xlsx
```

## Outputs

- `analysis_summary.json`: overall KPIs, field samples, top/bottom summaries.
- `monthly_trend.csv`: monthly trend.
- `store_summary.csv`: store-level summary.
- `channel_summary.csv`: order category/source summary.
- `daypart_summary.csv`: daypart/hour summary.
- `member_summary.csv`: member/non-member summary.
- `store_daypart_summary.csv`: store x daypart x hour fact table.
- `maijia_business_diagnosis_report.html`: self-contained HTML diagnosis report.

## Validation

```bash
file path/to/export.xlsx
unzip -t path/to/export.xlsx
python3 scripts/run_pipeline.py --help
```

Open the HTML report and verify the date range, row count, store count, charts, sorting, and responsive layout.

## Data Boundary

This skill diagnoses operating performance from sales data. Without menu costs, labor, rent, platform commission, store area, and customer reviews, do not present the output as a profit audit or definitive root-cause analysis.
