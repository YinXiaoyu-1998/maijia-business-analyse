# maijia-business-analyse

A reusable skill for Maijia Xiaoguan / Meituan POS business analysis. It helps agents export Meituan `营业分组表` data, stream-process large `.xlsx` files, generate compact fact tables, and produce a visual McKinsey-style HTML operating diagnosis report.

## What It Does

- Guides data export from Meituan 管家 `自助营业取数`.
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

### 1. Fetch Data

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
  --output documents/maijia_business_analysis/raw_exports/maijia_business_data_YYYYMMDD_YYYYMMDD.xlsx
```

### 2. Run the Full Pipeline

```bash
python3 scripts/run_pipeline.py \
  --input documents/business_data.xlsx \
  --output-dir documents/maijia_business_analysis \
  --report documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆
```

### 3. Run Step by Step

```bash
python3 scripts/profile_business_data.py \
  --input documents/business_data.xlsx \
  --output-dir documents/maijia_business_analysis

python3 scripts/generate_business_report_html.py \
  --input-dir documents/maijia_business_analysis \
  --output documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆 \
  --source-name business_data.xlsx
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
