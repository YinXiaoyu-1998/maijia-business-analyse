# 美团管家营业分组表导出流程

用于从美团管家报表中心取得本 skill 所需的 `营业分组表` `.xlsx` 源文件。

## 浏览器前提

- 使用已经登录美团管家的 Chrome 或其他浏览器会话。
- 如需 agent 操作浏览器，优先使用能复用用户登录态的浏览器控制工具。
- 不要在对话或日志里暴露下载后的业务明细行；只报告文件路径、日期范围、行数和校验结果。

## 操作步骤

1. 打开 `https://pos.meituan.com/web/report/main#/rms-report/home`。
2. 点击左侧导航 `自助取数`。
3. 在展开菜单里点击 `自助营业取数`。
4. 在 `常用查询` 中选择 `全量数据`。
5. 设置 `营业日期`：
   - 用户说“过去 7 天”时，优先使用已经完整结束的 7 个营业日，避免把当天未完结数据混入。
   - 例如当前日期为 `2026-06-14`，则选择 `2026/06/07 - 2026/06/13`。
6. 点击 `展开筛选`。
7. 勾选所有参数；通常 `全量数据` 会自动勾选全部字段，但仍要用截图或页面状态确认。
8. 点击 `查询`，等待表格刷新并确认第一行日期落在目标范围内。
9. 点击右上角 `导出`。
10. 弹窗提示导出任务创建后，进入 `下载清单`。
11. 在 `下载清单记录` 中找到刚才日期范围对应的第一条记录，状态为 `导出完成` 后，点击右侧 `下载`。

## Chrome 拦截时的处理

有时点击 `下载` 会跳转到 `s3plus.sankuai.com` 临时 URL，但被 Chrome 扩展或客户端拦截，页面显示 `ERR_BLOCKED_BY_CLIENT`。

处理方式：

1. 从地址栏复制完整临时下载 URL。
2. 使用脚本下载：

```bash
python3 scripts/download_meituan_signed_url.py \
  --url '<signed-s3plus-url>' \
  --output documents/maijia_business_analysis/raw_exports/maijia_business_data_YYYYMMDD_YYYYMMDD.xlsx
```

3. 下载后校验：

```bash
file path/to/export.xlsx
unzip -t path/to/export.xlsx
```

应看到 `Microsoft OOXML` 且 `No errors detected`。
