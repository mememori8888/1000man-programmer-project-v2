import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "../outputs/qoo10-scraper-20260924";
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("実行記録");
sheet.showGridLines = false;

sheet.getRange("A1:D1").merge();
sheet.getRange("A1").values = [["Qoo10 小規模事前検証 実行記録"]];
sheet.getRange("A2:D2").merge();
sheet.getRange("A2").values = [["公開ページ、ログインなし、プロキシなし。アクセス制限は回避せず検知・停止します。"]];
sheet.getRange("A4:D12").values = [
  ["項目", "値", "単位・状態", "根拠"],
  ["開始時刻", "2026-09-24 13:39:27 +09:00", "JST", "run_log.jsonl"],
  ["終了時刻", "2026-09-24 13:42:15 +09:00", "JST", "run_log.jsonl"],
  ["処理時間", 167.0, "秒", "summary.json"],
  ["対象商品", 10, "商品", "検索ページ取得数"],
  ["CSV出力", 209, "種類別行", "qoo10_sample.csv"],
  ["画像出力", 100, "JPG", "すべて600x600"],
  ["未取得商品", 5, "商品", "failures.csvに理由を記録"],
  ["単体テスト", 4, "4件成功", "python -m unittest -v"],
];
sheet.getRange("A14:D17").values = [
  ["利用情報", "値", "状態", "備考"],
  ["Codex消費トークン", "取得不可", "未計測", "実行環境が正確なタスク別消費量を公開していないため推測しない"],
  ["観測区間", "2026-09-24 13:35:32 - 13:42:15 +09:00", "JST", "初回検証と修正版検証"],
  ["対象URL", "https://www.qoo10.jp/s/?keyword=%E3%83%91%E3%83%B3%E3%83%84%20%E3%83%AC%E3%83%87%E3%82%A3%E3%83%BC%E3%82%B9", "公開ページ", "Qoo10"],
];

sheet.getRange("A1:D17").format.font = { name: "Arial", size: 10, color: "#1F2937" };
sheet.getRange("A1").format.font = { name: "Arial", size: 15, bold: true, color: "#111827" };
sheet.getRange("A2").format.font = { name: "Arial", size: 10, italic: true, color: "#4B5563" };
for (const header of ["A4:D4", "A14:D14"]) {
  sheet.getRange(header).format = {
    fill: "#334155",
    font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
}
sheet.getRange("A5:D12").format.borders = { preset: "inside", style: "thin", color: "#E5E7EB" };
sheet.getRange("A15:D17").format.borders = { preset: "inside", style: "thin", color: "#E5E7EB" };
sheet.getRange("B7:B12").format.numberFormat = "#,##0.0";
sheet.getRange("A1:D17").format.verticalAlignment = "center";
sheet.getRange("A1:D17").format.wrapText = true;
sheet.getRange("A:A").format.columnWidth = 18;
sheet.getRange("B:B").format.columnWidth = 48;
sheet.getRange("C:C").format.columnWidth = 18;
sheet.getRange("D:D").format.columnWidth = 54;
sheet.getRange("1:2").format.rowHeight = 28;
sheet.getRange("5:17").format.autofitRows();
sheet.freezePanes.freezeRows(4);

const check = await workbook.inspect({
  kind: "table",
  range: "実行記録!A1:D17",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 4,
});
console.log(check.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 50 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "実行記録", range: "A1:D17", scale: 1.5, format: "png" });
await fs.writeFile(`${outputDir}/execution_log_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(`${outputDir}/execution_log.xlsx`);
