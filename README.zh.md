# maijia-business-analyse

麦家小馆 / 美团管家营业数据分析 skill：从美团 `自助营业取数` 导出营业分组表，流式处理大体积 Excel，生成事实表，并输出一份视觉化的“麦肯锡风格”经营诊断 HTML 报告。

## 可以做什么

- 指导 agent 从美团管家导出 `营业分组表`。
- 说明何时需要额外导出 `自助菜品取数`，用于菜品穿透和归因。
- 说明如何导出 `菜品库` 基础信息，并把 `基础分类` 作为档口维度。
- 处理很大的 `.xlsx` 文件，不需要一次性读完整工作簿。
- 生成门店、渠道、餐段、会员、月度趋势等事实表。
- 自动生成自包含 HTML 报告，包含 KPI、柱状图、散点图、热力图、排序表和机会池。
- 支持复用到 Codex、Claude Code、Cursor 等能读取本地 skill 文件夹的智能体。

## 安装

### Codex

把整个文件夹复制到 Codex skill 目录：

```bash
mkdir -p ~/.codex/skills
cp -R maijia-business-analyse ~/.codex/skills/
```

重启或刷新 Codex 后，用 `$maijia-business-analyse` 调用。

### Claude Code / Cursor / 其他 agent

把本文件夹放到项目或 agent 可读取的位置，并在提示词中说明：

```text
Use the skill at /path/to/maijia-business-analyse to analyze Meituan business data and generate the HTML operating diagnosis report.
```

## 使用方式

### 1. 获取营业数据

阅读 `references/meituan_export_workflow.zh.md`。核心流程是：

1. 打开美团管家报表中心。
2. 进入 `自助取数 -> 自助营业取数`。
3. 选择 `全量数据`，设置营业日期，展开筛选并全选字段。
4. 查询后点击报表页右上角 `导出`，创建导出任务。
5. 到 `下载清单记录`，找到刚才日期范围和申请时间都匹配的记录。
6. 等状态变为 `导出完成` 后，点击该行最右侧 `操作` 列的 `下载`；这个按钮通常在 `删除` 左侧，不是报表页右上角的 `导出`。

如果 Chrome 拦截 `s3plus.sankuai.com` 下载地址，可复制临时 URL 后运行：

```bash
python3 scripts/download_meituan_signed_url.py \
  --url '<signed-s3plus-url>' \
  --output documents/raw_exports/maijia_business_YYYYMMDD_YYYYMMDD.xlsx
```

### 原始下载文件命名

所有从美团下载的原始文件统一保存到 `documents/raw_exports/`：

| 导出类型 | 文件名 |
|---|---|
| `自助营业取数` / `营业分组表` | `maijia_business_YYYYMMDD_YYYYMMDD.xlsx` |
| `自助菜品取数` / `菜品主题数据` | `maijia_dishes_YYYYMMDD_YYYYMMDD.xlsx` |
| `菜品库` / `导出菜品基础信息` | `maijia_dish_catalog_YYYYMMDD.xlsx` |

如果同一日期范围被拆成多个文件，在 `.xlsx` 前追加 `_part01`、`_part02`。

当需要菜品穿透、菜单归因或“穿透到菜品”时，使用同一参考文件里的 `自助取数 -> 自助菜品取数` 流程。展开筛选并全选字段组，导出后在 `下载清单记录` 中下载匹配的 `菜品主题数据(日期【...】)` 行，并按标准命名保存，例如 `documents/raw_exports/maijia_dishes_20260614_20260620.xlsx`。

当需要档口归因时，还需要从 `运营中心 -> 菜品管理 -> 菜品库 -> 菜品导出 -> 导出菜品基础信息` 导出菜品库。选择目标品牌，通常是 `麦家小馆`，选择全部字段，并按标准命名保存，例如 `documents/raw_exports/maijia_dish_catalog_20260626.xlsx`。在本分析口径里，`档口 = 基础分类`。

### 2. 一键生成事实表和 HTML 报告

```bash
python3 scripts/run_pipeline.py \
  --input documents/raw_exports/maijia_business_YYYYMMDD_YYYYMMDD.xlsx \
  --output-dir documents/maijia_business_analysis \
  --report documents/maijia_business_analysis/maijia_business_diagnosis_report.html \
  --company 麦家小馆
```

### 3. 分步运行

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

## 输出文件

- `analysis_summary.json`：总览 KPI、字段样本、Top/Bottom 摘要。
- `monthly_trend.csv`：月度经营趋势。
- `store_summary.csv`：门店经营汇总。
- `channel_summary.csv`：订单分类/来源汇总。
- `daypart_summary.csv`：餐段/时段汇总。
- `member_summary.csv`：会员/非会员汇总。
- `store_daypart_summary.csv`：门店 × 餐段 × 时段事实表。
- `maijia_business_diagnosis_report.html`：自包含 HTML 经营诊断报告。

## 校验

```bash
file path/to/export.xlsx
unzip -t path/to/export.xlsx
python3 scripts/run_pipeline.py --help
```

打开 HTML 后检查：日期范围、样本行数、门店数、图表渲染、表格排序和移动端布局。

## 数据边界

本 skill 基于营业数据做经营诊断。没有菜品成本、人工、租金、平台佣金、门店面积和顾客评价时，不应把结论写成利润审计或确定性根因分析。
