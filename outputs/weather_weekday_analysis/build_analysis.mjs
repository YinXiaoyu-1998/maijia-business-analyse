import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/zhangdagang/Downloads/25年7月数据_副本.xlsx";
const outputDir = "/Users/zhangdagang/Desktop/MAIJIA_ANALYSE/outputs/weather_weekday_analysis";
const outputPath = `${outputDir}/25年7月_星期天气拆解分析.xlsx`;
const weatherUrl =
  "https://archive-api.open-meteo.com/v1/archive?latitude=39.9042&longitude=116.4074&start_date=2025-07-01&end_date=2025-07-31&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum&timezone=Asia%2FShanghai";
const holidaySourceUrl = "https://www.gov.cn/zhengce/content/202411/content_6986382.htm";

const weekdayOrder = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const weatherOrder = ["晴/少云", "多云/阴", "小雨/零星雨", "明显降雨"];
const holidayOrder = ["工作日", "周末", "法定节假日", "调休上班日"];
const statutoryHolidays2025 = new Set([
  "2025-01-01",
  "2025-01-28",
  "2025-01-29",
  "2025-01-30",
  "2025-01-31",
  "2025-02-01",
  "2025-02-02",
  "2025-02-03",
  "2025-02-04",
  "2025-04-04",
  "2025-04-05",
  "2025-04-06",
  "2025-05-01",
  "2025-05-02",
  "2025-05-03",
  "2025-05-04",
  "2025-05-05",
  "2025-05-31",
  "2025-06-01",
  "2025-06-02",
  "2025-10-01",
  "2025-10-02",
  "2025-10-03",
  "2025-10-04",
  "2025-10-05",
  "2025-10-06",
  "2025-10-07",
  "2025-10-08",
]);
const adjustedWorkdays2025 = new Set(["2025-01-26", "2025-02-08", "2025-04-27", "2025-09-28", "2025-10-11"]);
const weatherCodeMap = new Map([
  [0, "晴"],
  [1, "大部晴朗"],
  [2, "局部多云"],
  [3, "阴/多云"],
  [45, "雾"],
  [48, "雾凇"],
  [51, "小雨/毛毛雨"],
  [53, "中雨/毛毛雨"],
  [55, "大雨/毛毛雨"],
  [61, "小雨"],
  [63, "中雨"],
  [65, "大雨"],
  [80, "阵雨"],
  [81, "强阵雨"],
  [82, "暴阵雨"],
  [95, "雷暴"],
  [96, "雷暴伴冰雹"],
  [99, "强雷暴伴冰雹"],
]);

function parseDate(value) {
  if (value instanceof Date) return value;
  const s = String(value).replaceAll("/", "-");
  return new Date(`${s}T00:00:00+08:00`);
}

function ymdValue(value) {
  if (value instanceof Date) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  return String(value).replaceAll("/", "-");
}

function weekdayCn(date) {
  return weekdayOrder[(date.getDay() + 6) % 7];
}

function isWeekend(weekday) {
  return weekday === "周六" || weekday === "周日";
}

function holidayGroup(date, weekday) {
  if (adjustedWorkdays2025.has(date)) return "调休上班日";
  if (statutoryHolidays2025.has(date)) return "法定节假日";
  if (isWeekend(weekday)) return "周末";
  return "工作日";
}

function weatherGroup(code, precip) {
  if (precip >= 10) return "明显降雨";
  if (precip > 0) return "小雨/零星雨";
  if (code === 0 || code === 1) return "晴/少云";
  return "多云/阴";
}

function sum(rows, key) {
  return rows.reduce((acc, row) => acc + Number(row[key] || 0), 0);
}

function avg(rows, key) {
  return rows.length ? sum(rows, key) / rows.length : 0;
}

function groupBy(rows, keyFn) {
  const groups = new Map();
  for (const row of rows) {
    const key = keyFn(row);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return groups;
}

function pct(value) {
  return Number.isFinite(value) ? value : 0;
}

function round(value, digits = 2) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function addRows(sheet, startCell, rows) {
  sheet.getRange(startCell).writeValues(rows);
}

function styleTable(sheet, address) {
  const range = sheet.getRange(address);
  range.format.borders = { preset: "all", style: "thin", color: "#D9E1E8" };
  range.format.font = { name: "Arial", size: 10 };
  const header = range.getRow(0);
  header.format.font = { bold: true, color: "#17365D" };
}

function styleTitle(sheet, address) {
  const range = sheet.getRange(address);
  range.format.font = { bold: true, size: 16, color: "#17365D" };
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getCell(0, index).format.columnWidth = width;
  });
}

const sourceBlob = await FileBlob.load(inputPath);
const sourceWorkbook = await SpreadsheetFile.importXlsx(sourceBlob);
const sourceSheet = sourceWorkbook.worksheets.getItem("综合营业统计");
const rawValues = sourceSheet.getRange("A1:E97").values;
const header = rawValues[2];
const dataRows = rawValues
  .slice(3)
  .filter((row) => row[0] && row[0] !== "合计")
  .map((row) => {
    const date = parseDate(row[2]);
    return {
      城市: row[0],
      门店名称: row[1],
      营业日期: ymdValue(row[2]),
      星期: weekdayCn(date),
      营业天数: Number(row[3]),
      营业收入: Number(row[4]),
    };
  });

const weatherResponse = await fetch(weatherUrl);
if (!weatherResponse.ok) {
  throw new Error(`Weather request failed: ${weatherResponse.status} ${weatherResponse.statusText}`);
}
const weatherPayload = await weatherResponse.json();
const weatherRows = weatherPayload.daily.time.map((date, index) => {
  const code = Number(weatherPayload.daily.weather_code[index]);
  const precipitation = Number(weatherPayload.daily.precipitation_sum[index]);
  return {
    日期: date,
    天气代码: code,
    天气: weatherCodeMap.get(code) || String(code),
    天气分组: weatherGroup(code, precipitation),
    最高温: Number(weatherPayload.daily.temperature_2m_max[index]),
    最低温: Number(weatherPayload.daily.temperature_2m_min[index]),
    降水量: precipitation,
  };
});
const weatherByDate = new Map(weatherRows.map((row) => [row.日期, row]));

const detailedRows = dataRows.map((row) => ({
  ...row,
  是否周末: isWeekend(row.星期) ? "是" : "否",
  是否法定节假日: statutoryHolidays2025.has(row.营业日期) ? "是" : "否",
  是否调休上班: adjustedWorkdays2025.has(row.营业日期) ? "是" : "否",
  节假日分组: holidayGroup(row.营业日期, row.星期),
  是否暑期: "是",
  ...weatherByDate.get(row.营业日期),
}));

const dailyRows = Array.from(groupBy(detailedRows, (row) => row.营业日期).entries())
  .map(([date, rows]) => {
    const weather = weatherByDate.get(date);
    return {
      日期: date,
      星期: rows[0].星期,
      天气: weather.天气,
      天气分组: weather.天气分组,
      最高温: weather.最高温,
      最低温: weather.最低温,
      降水量: weather.降水量,
      是否周末: isWeekend(rows[0].星期) ? "是" : "否",
      是否法定节假日: statutoryHolidays2025.has(date) ? "是" : "否",
      是否调休上班: adjustedWorkdays2025.has(date) ? "是" : "否",
      节假日分组: holidayGroup(date, rows[0].星期),
      是否暑期: "是",
      门店数: new Set(rows.map((row) => row.门店名称)).size,
      总收入: sum(rows, "营业收入"),
      单店均收: avg(rows, "营业收入"),
    };
  })
  .sort((a, b) => a.日期.localeCompare(b.日期));

const totalRevenue = sum(detailedRows, "营业收入");
const avgDailyRevenue = avg(dailyRows, "总收入");
const avgStoreDayRevenue = avg(detailedRows, "营业收入");
const weekendRows = dailyRows.filter((row) => row.节假日分组 === "周末");
const workdayRows = dailyRows.filter((row) => row.节假日分组 === "工作日");
const rainyRows = dailyRows.filter((row) => row.降水量 > 0);
const noRainRows = dailyRows.filter((row) => row.降水量 === 0);
const statutoryCount = dailyRows.filter((row) => row.是否法定节假日 === "是").length;
const adjustedWorkdayCount = dailyRows.filter((row) => row.是否调休上班 === "是").length;
const maxDaily = dailyRows.reduce((best, row) => (row.总收入 > best.总收入 ? row : best), dailyRows[0]);
const minDaily = dailyRows.reduce((best, row) => (row.总收入 < best.总收入 ? row : best), dailyRows[0]);

const weekdaySummary = weekdayOrder.map((weekday) => {
  const rows = dailyRows.filter((row) => row.星期 === weekday);
  return [
    weekday,
    rows.length,
    round(sum(rows, "总收入"), 2),
    round(avg(rows, "总收入"), 2),
    round(avg(rows, "单店均收"), 2),
    round(avg(rows, "降水量"), 2),
    round(avg(rows, "总收入") / avgDailyRevenue - 1, 3),
  ];
});

const weatherSummary = weatherOrder
  .map((group) => {
    const rows = dailyRows.filter((row) => row.天气分组 === group);
    return [
      group,
      rows.length,
      round(sum(rows, "总收入"), 2),
      round(avg(rows, "总收入"), 2),
      round(avg(rows, "单店均收"), 2),
      round(avg(rows, "降水量"), 2),
      round(avg(rows, "总收入") / avgDailyRevenue - 1, 3),
    ];
  })
  .filter((row) => row[1] > 0);

const crossRows = [];
for (const weekday of weekdayOrder) {
  for (const weatherGroupName of weatherOrder) {
    const rows = dailyRows.filter((row) => row.星期 === weekday && row.天气分组 === weatherGroupName);
    if (rows.length) {
      crossRows.push([
        weekday,
        weatherGroupName,
        rows.length,
        round(sum(rows, "总收入"), 2),
        round(avg(rows, "总收入"), 2),
        round(avg(rows, "降水量"), 2),
      ]);
    }
  }
}

const holidaySummary = holidayOrder
  .map((group) => {
    const rows = dailyRows.filter((row) => row.节假日分组 === group);
    return [
      group,
      rows.length,
      round(sum(rows, "总收入"), 2),
      round(avg(rows, "总收入"), 2),
      round(avg(rows, "单店均收"), 2),
      round(avg(rows, "降水量"), 2),
      rows.length ? round(avg(rows, "总收入") / avgDailyRevenue - 1, 3) : 0,
    ];
  })
  .filter((row) => row[1] > 0);

const storeWeekdayRows = [];
const stores = Array.from(new Set(detailedRows.map((row) => row.门店名称))).sort();
for (const store of stores) {
  const base = [store];
  for (const weekday of weekdayOrder) {
    base.push(round(avg(detailedRows.filter((row) => row.门店名称 === store && row.星期 === weekday), "营业收入"), 2));
  }
  storeWeekdayRows.push(base);
}

const insightRows = [
  ["分析口径", "三店按日期汇总；天气用北京逐日历史天气；节假日按国务院安排。"],
  ["总营业收入", round(totalRevenue, 2)],
  ["平均日收入（三店合计）", round(avgDailyRevenue, 2)],
  ["平均单店日收入", round(avgStoreDayRevenue, 2)],
  ["周末较工作日", `${round((avg(weekendRows, "总收入") / avg(workdayRows, "总收入") - 1) * 100, 1)}%`],
  ["法定节假日天数", statutoryCount],
  ["调休上班日天数", adjustedWorkdayCount],
  ["暑期口径", "7月全月标记为暑期，因变量恒定，不能单独估算暑期增量。"],
  ["有雨较无雨", `${round((avg(rainyRows, "总收入") / avg(noRainRows, "总收入") - 1) * 100, 1)}%`],
  ["最高日", `${maxDaily.日期} ${maxDaily.星期} ${maxDaily.天气分组}，${round(maxDaily.总收入, 2)} 元`],
  ["最低日", `${minDaily.日期} ${minDaily.星期} ${minDaily.天气分组}，${round(minDaily.总收入, 2)} 元`],
];

const workbook = Workbook.create();
const overview = workbook.worksheets.add("分析总览");
const weekdaySheet = workbook.worksheets.add("星期拆解");
const weatherSheet = workbook.worksheets.add("天气拆解");
const holidaySheet = workbook.worksheets.add("节假日拆解");
const crossSheet = workbook.worksheets.add("星期天气交叉");
const detailSheet = workbook.worksheets.add("明细数据");
const sourceSheetOut = workbook.worksheets.add("数据源说明");

overview.showGridLines = false;
weekdaySheet.showGridLines = false;
weatherSheet.showGridLines = false;
holidaySheet.showGridLines = false;
crossSheet.showGridLines = false;
detailSheet.showGridLines = false;
sourceSheetOut.showGridLines = false;

overview.getRange("A1:G1").merge();
overview.getRange("A1").values = [["2025年7月 星期/天气/节假日拆解分析"]];
styleTitle(overview, "A1:G1");
overview.getRange("A3:B14").writeValues([["指标", "结果"], ...insightRows]);
styleTable(overview, "A3:B14");
overview.getRange("D3:K3").writeValues([["日期", "星期", "节假日分组", "天气", "天气分组", "降水量(mm)", "总收入(元)", "单店均收(元)"]]);
overview.getRange("D4:K34").writeValues(dailyRows.map((row) => [row.日期, row.星期, row.节假日分组, row.天气, row.天气分组, row.降水量, round(row.总收入, 2), round(row.单店均收, 2)]));
styleTable(overview, "D3:K34");
overview.getRange("I4:K34").setNumberFormat("#,##0.00");
overview.getRange("A2:K2").format.rowHeight = 10;
setWidths(overview, [20, 48, 2, 14, 10, 14, 16, 16, 14, 16, 16]);

weekdaySheet.getRange("A1:G1").merge();
weekdaySheet.getRange("A1").values = [["按星期拆解（三店合计日收入）"]];
styleTitle(weekdaySheet, "A1:G1");
addRows(weekdaySheet, "A3", [["星期", "天数", "总收入(元)", "平均日收入(元)", "平均单店收入(元)", "平均降水量(mm)", "较月均日收入"]]);
addRows(weekdaySheet, "A4", weekdaySummary);
styleTable(weekdaySheet, "A3:G10");
weekdaySheet.getRange("C4:F10").setNumberFormat("#,##0.00");
weekdaySheet.getRange("G4:G10").setNumberFormat("0.0%");
setWidths(weekdaySheet, [10, 8, 16, 18, 18, 16, 16]);

weatherSheet.getRange("A1:G1").merge();
weatherSheet.getRange("A1").values = [["按天气拆解（三店合计日收入）"]];
styleTitle(weatherSheet, "A1:G1");
addRows(weatherSheet, "A3", [["天气分组", "天数", "总收入(元)", "平均日收入(元)", "平均单店收入(元)", "平均降水量(mm)", "较月均日收入"]]);
addRows(weatherSheet, "A4", weatherSummary);
styleTable(weatherSheet, `A3:G${3 + weatherSummary.length}`);
weatherSheet.getRange(`C4:F${3 + weatherSummary.length}`).setNumberFormat("#,##0.00");
weatherSheet.getRange(`G4:G${3 + weatherSummary.length}`).setNumberFormat("0.0%");
setWidths(weatherSheet, [16, 8, 16, 18, 18, 16, 16]);

holidaySheet.getRange("A1:G1").merge();
holidaySheet.getRange("A1").values = [["按节假日因素拆解（三店合计日收入）"]];
styleTitle(holidaySheet, "A1:G1");
addRows(holidaySheet, "A3", [["节假日分组", "天数", "总收入(元)", "平均日收入(元)", "平均单店收入(元)", "平均降水量(mm)", "较月均日收入"]]);
addRows(holidaySheet, "A4", holidaySummary);
styleTable(holidaySheet, `A3:G${3 + holidaySummary.length}`);
holidaySheet.getRange(`C4:F${3 + holidaySummary.length}`).setNumberFormat("#,##0.00");
holidaySheet.getRange(`G4:G${3 + holidaySummary.length}`).setNumberFormat("0.0%");
holidaySheet.getRange("A9:B12").writeValues([
  ["口径提示", "2025年7月无国务院公布的法定节假日、无调休上班日。"],
  ["可解释因素", "本月可直接比较的是工作日与自然周末；暑期为全月共同背景。"],
  ["周末较工作日", `${round((avg(weekendRows, "总收入") / avg(workdayRows, "总收入") - 1) * 100, 1)}%`],
  ["暑期影响", "仅凭7月单月数据无法估算，需与6月下旬或8月/去年非暑期月份对比。"],
]);
styleTable(holidaySheet, "A9:B12");
setWidths(holidaySheet, [18, 54, 16, 18, 18, 16, 16]);

crossSheet.getRange("A1:F1").merge();
crossSheet.getRange("A1").values = [["星期 × 天气交叉表现"]];
styleTitle(crossSheet, "A1:F1");
addRows(crossSheet, "A3", [["星期", "天气分组", "天数", "总收入(元)", "平均日收入(元)", "平均降水量(mm)"]]);
addRows(crossSheet, "A4", crossRows);
styleTable(crossSheet, `A3:F${3 + crossRows.length}`);
crossSheet.getRange(`D4:F${3 + crossRows.length}`).setNumberFormat("#,##0.00");
setWidths(crossSheet, [10, 16, 8, 16, 18, 16]);

detailSheet.getRange("A1:R1").writeValues([[
  "城市",
  "门店名称",
  "营业日期",
  "星期",
  "营业天数",
  "营业收入(元)",
  "是否周末",
  "是否法定节假日",
  "是否调休上班",
  "节假日分组",
  "是否暑期",
  "天气代码",
  "天气",
  "天气分组",
  "最高温(℃)",
  "最低温(℃)",
  "降水量(mm)",
  "雨量判断",
]]);
detailSheet.getRange(`A2:R${1 + detailedRows.length}`).writeValues(
  detailedRows
    .sort((a, b) => a.门店名称.localeCompare(b.门店名称) || a.营业日期.localeCompare(b.营业日期))
    .map((row) => [
      row.城市,
      row.门店名称,
      row.营业日期,
      row.星期,
      row.营业天数,
      round(row.营业收入, 2),
      row.是否周末,
      row.是否法定节假日,
      row.是否调休上班,
      row.节假日分组,
      row.是否暑期,
      row.天气代码,
      row.天气,
      row.天气分组,
      row.最高温,
      row.最低温,
      row.降水量,
      row.降水量 > 0 ? "有雨" : "无雨",
    ]),
);
styleTable(detailSheet, `A1:R${1 + detailedRows.length}`);
detailSheet.getRange(`F2:F${1 + detailedRows.length}`).setNumberFormat("#,##0.00");
detailSheet.getRange(`O2:Q${1 + detailedRows.length}`).setNumberFormat("#,##0.00");
setWidths(detailSheet, [10, 24, 14, 8, 10, 14, 10, 16, 14, 14, 10, 10, 14, 14, 12, 12, 12, 10]);
detailSheet.freezePanes.freezeRows(1);

sourceSheetOut.getRange("A1:B1").writeValues([["项目", "说明"]]);
sourceSheetOut.getRange("A2:B9").writeValues([
  ["源文件", inputPath],
  ["原始表", "综合营业统计，营业日期 2025/07/01-2025/07/31，门店为全部"],
  ["收入口径", header[4]],
  ["天气来源", weatherUrl],
  ["节假日来源", holidaySourceUrl],
  ["天气地点", "北京，Open-Meteo 返回坐标约 39.89455, 116.35983，时区 Asia/Shanghai"],
  ["天气分组", "降水量>=10mm 为明显降雨；0<降水量<10mm 为小雨/零星雨；无降雨时按天气代码分为晴/少云或多云/阴。"],
  ["节假日口径", "2025年7月没有法定节假日或调休上班日；暑期为全月共同背景标签。"],
]);
styleTable(sourceSheetOut, "A1:B9");
setWidths(sourceSheetOut, [16, 120]);
sourceSheetOut.getRange("B2:B9").format.wrapText = true;

for (const sheet of [overview, weekdaySheet, weatherSheet, holidaySheet, crossSheet, detailSheet, sourceSheetOut]) {
  sheet.freezePanes.freezeRows(1);
}

await fs.mkdir(outputDir, { recursive: true });

const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errorScan.ndjson);

const inspect = await workbook.inspect({
  kind: "region",
  sheetId: "分析总览",
  range: "A1:K34",
  maxChars: 5000,
});
console.log(inspect.ndjson);

for (const name of ["分析总览", "星期拆解", "天气拆解", "节假日拆解", "星期天气交叉", "明细数据", "数据源说明"]) {
  const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
  const previewBytes = new Uint8Array(await preview.arrayBuffer());
  await fs.writeFile(`${outputDir}/preview_${name}.png`, previewBytes);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, totalRevenue, avgDailyRevenue, avgStoreDayRevenue, maxDaily, minDaily }, null, 2));
