import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/zhangdagang/Downloads/25年7月数据_副本.xlsx";
const outputDir = "/Users/zhangdagang/Desktop/MAIJIA_ANALYSE/outputs/weather_weekday_analysis";
const outputPath = `${outputDir}/2026年7月_参考2025规律预算拆解.xlsx`;
const weatherUrl =
  "https://archive-api.open-meteo.com/v1/archive?latitude=39.9042&longitude=116.4074&start_date=2025-07-01&end_date=2025-07-31&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum&timezone=Asia%2FShanghai";
const holiday2026SourceUrl = "https://www.scio.gov.cn/zdgz/jj/202511/t20251110_938367.html";

const weekdayOrder = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const weatherOrder = ["晴/少云", "多云/阴", "小雨/零星雨", "明显降雨"];
const holidayOrder = ["工作日", "周末", "法定节假日", "调休上班日"];
const growthRate = 0;
const weatherCodeMap = new Map([
  [0, "晴"],
  [1, "大部晴朗"],
  [2, "局部多云"],
  [3, "阴/多云"],
  [51, "小雨/毛毛雨"],
  [53, "中雨/毛毛雨"],
  [61, "小雨"],
  [63, "中雨"],
  [65, "大雨"],
]);

const statutoryHolidays2026 = new Set([
  "2026-01-01",
  "2026-01-02",
  "2026-01-03",
  "2026-02-15",
  "2026-02-16",
  "2026-02-17",
  "2026-02-18",
  "2026-02-19",
  "2026-02-20",
  "2026-02-21",
  "2026-02-22",
  "2026-02-23",
  "2026-04-04",
  "2026-04-05",
  "2026-04-06",
  "2026-05-01",
  "2026-05-02",
  "2026-05-03",
  "2026-05-04",
  "2026-05-05",
  "2026-06-19",
  "2026-06-20",
  "2026-06-21",
  "2026-09-25",
  "2026-09-26",
  "2026-09-27",
  "2026-10-01",
  "2026-10-02",
  "2026-10-03",
  "2026-10-04",
  "2026-10-05",
  "2026-10-06",
  "2026-10-07",
]);
const adjustedWorkdays2026 = new Set(["2026-01-04", "2026-02-14", "2026-02-28", "2026-05-09", "2026-09-20", "2026-10-10"]);

function parseDate(value) {
  if (value instanceof Date) return value;
  return new Date(`${String(value).replaceAll("/", "-")}T00:00:00+08:00`);
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

function ymd(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function weekdayCn(date) {
  return weekdayOrder[(date.getDay() + 6) % 7];
}

function isWeekend(weekday) {
  return weekday === "周六" || weekday === "周日";
}

function holidayGroup(date, weekday) {
  if (adjustedWorkdays2026.has(date)) return "调休上班日";
  if (statutoryHolidays2026.has(date)) return "法定节假日";
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

function round(value, digits = 2) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
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

function addRows(sheet, startCell, rows) {
  sheet.getRange(startCell).writeValues(rows);
}

function styleTable(sheet, address) {
  const range = sheet.getRange(address);
  range.format.borders = { preset: "all", style: "thin", color: "#D9E1E8" };
  range.format.font = { name: "Arial", size: 10 };
  range.getRow(0).format.font = { bold: true, color: "#17365D" };
}

function styleTitle(sheet, address) {
  sheet.getRange(address).format.font = { bold: true, size: 16, color: "#17365D" };
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getCell(0, index).format.columnWidth = width;
  });
}

const sourceWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sourceSheet = sourceWorkbook.worksheets.getItem("综合营业统计");
const rawValues = sourceSheet.getRange("A1:E97").values;
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
      营业收入: Number(row[4]),
    };
  });

const weatherResponse = await fetch(weatherUrl);
if (!weatherResponse.ok) throw new Error(`Weather request failed: ${weatherResponse.status}`);
const weatherPayload = await weatherResponse.json();
const weatherRows = weatherPayload.daily.time.map((date, index) => {
  const code = Number(weatherPayload.daily.weather_code[index]);
  const precipitation = Number(weatherPayload.daily.precipitation_sum[index]);
  return {
    日期: date,
    天气代码: code,
    天气: weatherCodeMap.get(code) || String(code),
    天气分组: weatherGroup(code, precipitation),
    降水量: precipitation,
  };
});
const weatherByDate = new Map(weatherRows.map((row) => [row.日期, row]));

const detailed2025 = dataRows.map((row) => ({ ...row, ...weatherByDate.get(row.营业日期) }));
const daily2025 = Array.from(groupBy(detailed2025, (row) => row.营业日期).entries())
  .map(([date, rows]) => ({
    日期: date,
    星期: rows[0].星期,
    天气分组: rows[0].天气分组,
    总收入: sum(rows, "营业收入"),
  }))
  .sort((a, b) => a.日期.localeCompare(b.日期));

const total2025 = sum(detailed2025, "营业收入");
const target2026 = total2025 * (1 + growthRate);
const avgDaily2025 = avg(daily2025, "总收入");

const weekdayFactors = new Map(
  weekdayOrder.map((weekday) => {
    const rows = daily2025.filter((row) => row.星期 === weekday);
    return [weekday, rows.length ? avg(rows, "总收入") / avgDaily2025 : 1];
  }),
);
const weatherFactors = new Map(
  weatherOrder.map((group) => {
    const rows = daily2025.filter((row) => row.天气分组 === group);
    return [group, rows.length ? avg(rows, "总收入") / avgDaily2025 : 1];
  }),
);
const storeShares = new Map(
  Array.from(groupBy(detailed2025, (row) => row.门店名称).entries()).map(([store, rows]) => [store, sum(rows, "营业收入") / total2025]),
);

const budgetDailyRaw = [];
for (let day = 1; day <= 31; day += 1) {
  const date = new Date(2026, 6, day);
  const dateText = ymd(date);
  const weekday = weekdayCn(date);
  const sameDay2025 = `2025-07-${String(day).padStart(2, "0")}`;
  const weather = weatherByDate.get(sameDay2025);
  const rawWeight = (weekdayFactors.get(weekday) || 1) * (weatherFactors.get(weather.天气分组) || 1);
  budgetDailyRaw.push({
    日期: dateText,
    星期: weekday,
    节假日分组: holidayGroup(dateText, weekday),
    天气情景来源: sameDay2025,
    天气情景: weather.天气分组,
    原始权重: rawWeight,
  });
}
const rawWeightSum = sum(budgetDailyRaw, "原始权重");
const budgetDaily = budgetDailyRaw.map((row) => ({
  ...row,
  归一化权重: row.原始权重 / rawWeightSum,
  日预算: target2026 * (row.原始权重 / rawWeightSum),
}));

const budgetStoreRows = [];
for (const day of budgetDaily) {
  for (const [store, share] of storeShares.entries()) {
    budgetStoreRows.push({
      ...day,
      门店名称: store,
      门店占比: share,
      门店日预算: day.日预算 * share,
    });
  }
}

const budgetByWeekday = weekdayOrder.map((weekday) => {
  const rows = budgetDaily.filter((row) => row.星期 === weekday);
  return [weekday, rows.length, round(sum(rows, "日预算"), 2), round(avg(rows, "日预算"), 2), round(avg(rows, "归一化权重"), 4)];
});
const budgetByWeather = weatherOrder
  .map((group) => {
    const rows = budgetDaily.filter((row) => row.天气情景 === group);
    return [group, rows.length, round(sum(rows, "日预算"), 2), round(avg(rows, "日预算"), 2), round(weatherFactors.get(group) || 1, 3)];
  })
  .filter((row) => row[1] > 0);
const budgetByHoliday = holidayOrder
  .map((group) => {
    const rows = budgetDaily.filter((row) => row.节假日分组 === group);
    return [group, rows.length, round(sum(rows, "日预算"), 2), round(avg(rows, "日预算"), 2)];
  })
  .filter((row) => row[1] > 0);
const budgetByStore = Array.from(storeShares.entries()).map(([store, share]) => {
  const rows = budgetStoreRows.filter((row) => row.门店名称 === store);
  return [store, round(share, 4), round(sum(rows, "门店日预算"), 2), round(avg(rows, "门店日预算"), 2)];
});

const workbook = Workbook.create();
const overview = workbook.worksheets.add("预算总览");
const dailySheet = workbook.worksheets.add("2026日预算");
const storeSheet = workbook.worksheets.add("门店日预算");
const factorSheet = workbook.worksheets.add("25规律因子");
const sourceSheetOut = workbook.worksheets.add("口径说明");
for (const sheet of [overview, dailySheet, storeSheet, factorSheet, sourceSheetOut]) {
  sheet.showGridLines = false;
}

overview.getRange("A1:H1").merge();
overview.getRange("A1").values = [["2026年7月预算拆解（参考2025年7月规律）"]];
styleTitle(overview, "A1:H1");
overview.getRange("A3:B9").writeValues([
  ["指标", "结果"],
  ["2025年7月实际收入", round(total2025, 2)],
  ["预算增长率", growthRate],
  ["2026年7月预算总额", round(target2026, 2)],
  ["2026年7月天数", 31],
  ["法定节假日/调休", "无"],
  ["天气口径", "按2025同月同日天气分组作为情景"],
]);
styleTable(overview, "A3:B9");
overview.getRange("B4:B6").setNumberFormat("#,##0.00");
overview.getRange("B5").setNumberFormat("0.0%");

overview.getRange("D3:G3").writeValues([["节假日分组", "天数", "预算额(元)", "平均日预算(元)"]]);
overview.getRange(`D4:G${3 + budgetByHoliday.length}`).writeValues(budgetByHoliday);
styleTable(overview, `D3:G${3 + budgetByHoliday.length}`);
overview.getRange(`F4:G${3 + budgetByHoliday.length}`).setNumberFormat("#,##0.00");
setWidths(overview, [22, 36, 3, 16, 8, 16, 18, 12]);

dailySheet.getRange("A1:J1").writeValues([["日期", "星期", "节假日分组", "天气情景来源", "天气情景", "星期因子", "天气因子", "原始权重", "归一化权重", "日预算(元)"]]);
dailySheet.getRange("A2:J32").writeValues(
  budgetDaily.map((row) => [
    row.日期,
    row.星期,
    row.节假日分组,
    row.天气情景来源,
    row.天气情景,
    round(weekdayFactors.get(row.星期) || 1, 3),
    round(weatherFactors.get(row.天气情景) || 1, 3),
    round(row.原始权重, 4),
    round(row.归一化权重, 5),
    round(row.日预算, 2),
  ]),
);
styleTable(dailySheet, "A1:J32");
dailySheet.getRange("F2:I32").setNumberFormat("0.000");
dailySheet.getRange("J2:J32").setNumberFormat("#,##0.00");
setWidths(dailySheet, [14, 8, 14, 14, 16, 10, 10, 12, 12, 16]);

storeSheet.getRange("A1:L1").writeValues([["日期", "星期", "节假日分组", "天气情景", "门店名称", "门店占比", "日预算(元)", "门店日预算(元)", "星期因子", "天气因子", "归一化权重", "天气情景来源"]]);
storeSheet.getRange(`A2:L${1 + budgetStoreRows.length}`).writeValues(
  budgetStoreRows.map((row) => [
    row.日期,
    row.星期,
    row.节假日分组,
    row.天气情景,
    row.门店名称,
    round(row.门店占比, 4),
    round(row.日预算, 2),
    round(row.门店日预算, 2),
    round(weekdayFactors.get(row.星期) || 1, 3),
    round(weatherFactors.get(row.天气情景) || 1, 3),
    round(row.归一化权重, 5),
    row.天气情景来源,
  ]),
);
styleTable(storeSheet, `A1:L${1 + budgetStoreRows.length}`);
storeSheet.getRange(`F2:F${1 + budgetStoreRows.length}`).setNumberFormat("0.0%");
storeSheet.getRange(`G2:H${1 + budgetStoreRows.length}`).setNumberFormat("#,##0.00");
setWidths(storeSheet, [14, 8, 14, 16, 24, 10, 14, 16, 10, 10, 12, 14]);

factorSheet.getRange("A1:E1").writeValues([["星期", "25天数", "25平均日收入", "25星期因子", "26预算额"]]);
factorSheet.getRange("A2:E8").writeValues(
  weekdayOrder.map((weekday) => {
    const historical = daily2025.filter((row) => row.星期 === weekday);
    const budget = budgetDaily.filter((row) => row.星期 === weekday);
    return [weekday, historical.length, round(avg(historical, "总收入"), 2), round(weekdayFactors.get(weekday) || 1, 3), round(sum(budget, "日预算"), 2)];
  }),
);
styleTable(factorSheet, "A1:E8");
factorSheet.getRange("G1:K1").writeValues([["天气分组", "25天数", "25平均日收入", "25天气因子", "26预算额"]]);
factorSheet.getRange(`G2:K${1 + budgetByWeather.length}`).writeValues(
  budgetByWeather.map((row) => {
    const historical = daily2025.filter((item) => item.天气分组 === row[0]);
    return [row[0], historical.length, round(avg(historical, "总收入"), 2), row[4], row[2]];
  }),
);
styleTable(factorSheet, `G1:K${1 + budgetByWeather.length}`);
factorSheet.getRange("C2:E8").setNumberFormat("#,##0.00");
factorSheet.getRange(`I2:K${1 + budgetByWeather.length}`).setNumberFormat("#,##0.00");
setWidths(factorSheet, [10, 10, 16, 12, 16, 3, 16, 10, 16, 12, 16]);

sourceSheetOut.getRange("A1:B1").writeValues([["项目", "说明"]]);
sourceSheetOut.getRange("A2:B10").writeValues([
  ["源文件", inputPath],
  ["预算月份", "2026-07-01 至 2026-07-31"],
  ["默认增长率", "0%，即以2025年7月实际收入作为2026年7月预算总额；如需增长目标，可按总额同比调整。"],
  ["星期规律", "使用2025年7月各星期平均日收入 / 2025年7月平均日收入。"],
  ["天气规律", "使用2025年7月各天气分组平均日收入 / 2025年7月平均日收入；2026天气未知，按2025同月同日天气作为情景。"],
  ["节假日规律", "2026年7月无国务院公布的法定节假日或调休上班日，因此预算拆解中只体现自然周末。"],
  ["门店拆分", "按2025年7月各门店收入占比分摊到门店日预算。"],
  ["天气来源", weatherUrl],
  ["2026节假日来源", holiday2026SourceUrl],
]);
styleTable(sourceSheetOut, "A1:B10");
sourceSheetOut.getRange("B2:B10").format.wrapText = true;
setWidths(sourceSheetOut, [18, 120]);

for (const sheet of [overview, dailySheet, storeSheet, factorSheet, sourceSheetOut]) {
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
  sheetId: "预算总览",
  range: "A1:G12",
  maxChars: 4000,
});
console.log(inspect.ndjson);
for (const name of ["预算总览", "2026日预算", "门店日预算", "25规律因子", "口径说明"]) {
  const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/preview_${name}.png`, new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(
  JSON.stringify(
    {
      outputPath,
      total2025,
      target2026,
      budgetByHoliday,
      budgetByStore,
    },
    null,
    2,
  ),
);
