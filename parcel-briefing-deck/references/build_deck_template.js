// 官田案簡報 — 仿使用者範本(虛線網格底、黑框、黑標題+紅副標、■ 條列、左表右圖)
const pptxgen = require("pptxgenjs");
const path = require("path");

const SCRATCH = String.raw`C:\Users\user\AppData\Local\Temp\claude\C--Users-user-Documents-Claude-Projects-----\41a9cb82-7de8-4023-b542-7d9ad59cca20\scratchpad`;
const MAPS = String.raw`C:\Users\user\Documents\Claude\Projects\大量圖資轉換工具\outputs\20260707官田maxmap\圖檔_maxmap`;
const OUT = String.raw`C:\Users\user\Documents\Claude\Projects\大量圖資轉換工具\outputs\20260707官田maxmap\20260707官田綠能設施興建評估_簡報.pptx`;

const FONT = "Microsoft JhengHei";
const RED = "C00000", BLACK = "111111", NAVY = "1F3864", GRAY = "808080", HDRBG = "E7E7E7";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5

// ---------- 共用:網格底 + 黑外框 ----------
function chrome(slide) {
  slide.addImage({ path: path.join(SCRATCH, "grid_bg.png"), x: 0, y: 0, w: 13.333, h: 7.5 });
  slide.addShape("rect", { x: 0.07, y: 0.07, w: 13.19, h: 7.36, fill: { color: "FFFFFF", transparency: 100 }, line: { color: "000000", width: 2.2 } });
}

// ---------- 共用:內容頁頁首(黑主標+紅副標+底線+頁碼,仿範本) ----------
function header(slide, main, sub, pageNo) {
  slide.addText(main, { x: 0.35, y: 0.16, w: 4.1, h: 0.72, fontFace: FONT, fontSize: 30, bold: true, color: BLACK, margin: 0, align: "left" });
  slide.addText(sub, { x: 4.35, y: 0.30, w: 7.4, h: 0.55, fontFace: FONT, fontSize: 19, bold: true, color: RED, margin: 0, align: "left" });
  // 範本樣式:頁首下緣細線
  slide.addShape("line", { x: 0.35, y: 0.92, w: 12.35, h: 0, line: { color: "333333", width: 1.4 } });
  slide.addText(String(pageNo), { x: 12.55, y: 0.14, w: 0.6, h: 0.5, fontFace: FONT, fontSize: 20, bold: true, color: BLACK, align: "right", margin: 0 });
}

// ---------- 共用:■ 條列 ----------
function bullets(slide, items, x, y, w, opts = {}) {
  const runs = [];
  items.forEach((t, i) => {
    runs.push({ text: "■ ", options: { fontFace: FONT, fontSize: opts.size || 13, bold: true, color: BLACK } });
    runs.push({ text: t, options: { fontFace: FONT, fontSize: opts.size || 13, color: BLACK, breakLine: i < items.length ? true : false, paraSpaceAfter: 8 } });
  });
  slide.addText(runs, { x, y, w, h: opts.h || 3.2, align: "left", valign: "top", margin: 0, lineSpacingMultiple: 1.12 });
}

// ---------- 共用:小表(灰表頭) ----------
function table(slide, header_, rows, x, y, w, colW) {
  const trs = [header_.map(t => ({ text: t, options: { fontFace: FONT, fontSize: 12, bold: true, color: BLACK, fill: { color: HDRBG }, align: "center", valign: "middle" } }))];
  rows.forEach(r => trs.push(r.map(t => ({ text: String(t), options: { fontFace: FONT, fontSize: 12, color: BLACK, align: "center", valign: "middle" } }))));
  slide.addTable(trs, { x, y, w, colW, border: { type: "solid", color: GRAY, pt: 0.75 }, rowH: 0.34 });
}

// ---------- 共用:右側地圖(A4 橫式 1.414 比) ----------
function mapImg(slide, file, cap) {
  const w = 8.45, h = w / 1.4143;
  slide.addImage({ path: path.join(MAPS, file), x: 4.55, y: 1.12, w, h });
  if (cap) slide.addText(cap, { x: 4.55, y: 1.12 + h + 0.05, w, h: 0.32, fontFace: FONT, fontSize: 10, color: "555555", align: "right", margin: 0 });
}

// ================= 1. 封面 =================
{
  const s = pres.addSlide();
  chrome(s);
  s.addText([
    { text: "臺南市", options: { breakLine: true } },
    { text: "官田區番子渡頭段122地號等133筆土地；", options: { breakLine: true } },
    { text: "社子段389地號等12筆土地", options: { breakLine: true } },
    { text: "綠能設施興建評估案", options: {} },
  ], { x: 0.9, y: 1.7, w: 11.5, h: 2.8, fontFace: FONT, fontSize: 30, bold: true, color: BLACK, align: "center", lineSpacingMultiple: 1.25 });
  // 雙藍線 + 日期(仿範本頁尾)
  s.addShape("line", { x: 0.55, y: 6.62, w: 12.23, h: 0, line: { color: NAVY, width: 2.5 } });
  s.addShape("line", { x: 0.55, y: 6.70, w: 12.23, h: 0, line: { color: NAVY, width: 1 } });
  s.addText("2026/07/15", { x: 5.17, y: 6.82, w: 3, h: 0.4, fontFace: FONT, fontSize: 14, color: BLACK, align: "center", margin: 0 });
}

// ================= 2. 基地區位 =================
{
  const s = pres.addSlide();
  chrome(s);
  header(s, "基礎資料", "區位、位置及範圍", 2);
  bullets(s, [
    "基地座落於臺南市官田區番子渡頭段(133筆)、社子段(12筆),共145筆土地。",
    "土地權屬:私有地144筆;公有地1筆(番子渡頭段157地號,林業用地,財政部國有財產署管理)。",
    "基地面積合計約59.67公頃(596,672 m²)。",
    "基地東側緊鄰國道3號並鄰近官田系統交流道(國道3號×台84線);周邊有農路及防汛道路可及。",
  ], 0.4, 1.2, 3.95, { size: 13, h: 5.6 });
  mapImg(s, "001_20260707官田maxmap_正射套疊.png", "正射影像及通用電子地圖套疊(NLSC)");
}

// ================= 3. 使用分區 =================
{
  const s = pres.addSlide();
  chrome(s);
  header(s, "土地使用管制", "非都市土地使用分區", 3);
  bullets(s, [
    "基地145筆土地均屬非都市土地。",
    "使用分區均為「一般農業區」,共145筆、約59.67公頃。",
  ], 0.4, 1.2, 3.95, { size: 13, h: 1.6 });
  table(s, ["使用分區", "筆數", "面積(公頃)"], [["一般農業區", "145", "59.67"], ["合計", "145", "59.67"]], 0.4, 3.0, 3.95, [1.75, 0.9, 1.3]);
  mapImg(s, "001_20260707官田maxmap_使用分區.png", "非都市土地使用分區及都市計畫土地使用分區圖");
}

// ================= 4. 使用地編定 =================
{
  const s = pres.addSlide();
  chrome(s);
  header(s, "土地使用管制", "使用地編定", 4);
  bullets(s, [
    "基地使用地編定計2類:農牧用地、林業用地。",
    "農牧用地130筆(約52.87公頃);林業用地15筆(約6.80公頃)。",
  ], 0.4, 1.2, 3.95, { size: 13, h: 1.6 });
  table(s, ["使用地類別", "筆數", "面積(公頃)"], [["農牧用地", "130", "52.87"], ["林業用地", "15", "6.80"], ["合計", "145", "59.67"]], 0.4, 3.0, 3.95, [1.75, 0.9, 1.3]);
  mapImg(s, "001_20260707官田maxmap_使用地編定.png", "非都市土地使用地變更編定及都市計畫土地使用分區圖");
}

// ================= 5. 國土功能分區 =================
{
  const s = pres.addSlide();
  chrome(s);
  header(s, "國土功能分區", "草案成果", 5);
  bullets(s, [
    "依各縣市政府國土功能分區圖資(草案、示意性質,實際以公告為準),基地全數位屬「農業發展地區」。",
    "其中農業發展地區第一類約50.95公頃(85.4%)、第二類約8.72公頃(14.6%)。",
  ], 0.4, 1.2, 3.95, { size: 13, h: 2.2 });
  table(s, ["國土功能分區", "面積(公頃)", "佔比"], [["農業發展地區第一類", "50.95", "85.4%"], ["農業發展地區第二類", "8.72", "14.6%"], ["合計", "59.67", "100%"]], 0.4, 3.4, 3.95, [1.95, 1.1, 0.9]);
  mapImg(s, "001_20260707官田maxmap_國土功能分區.png", "國土功能分區圖(草案示意)");
}

// ================= 6. 環境敏感地(待補) =================
{
  const s = pres.addSlide();
  chrome(s);
  header(s, "環境敏感地", "調查成果", 6);
  bullets(s, [
    "環境敏感地區(第一級、第二級)查詢辦理中,調查成果將於後續補充。",
  ], 0.4, 1.2, 3.95, { size: 13, h: 1.0 });
  table(s, ["分級", "調查項目", "查詢結果"], [["第一級", "(待補)", "(待補)"], ["第二級", "(待補)", "(待補)"]], 0.4, 2.3, 3.95, [0.85, 1.7, 1.4]);
  // 圖面待補框(虛線)
  s.addShape("rect", { x: 4.55, y: 1.12, w: 8.45, h: 5.97, fill: { color: "FFFFFF", transparency: 100 }, line: { color: GRAY, width: 1.5, dashType: "dash" } });
  s.addText("環境敏感地調查成果圖面\n(待補)", { x: 4.55, y: 3.5, w: 8.45, h: 1.2, fontFace: FONT, fontSize: 18, bold: true, color: GRAY, align: "center" });
}

// ================= 7. 臨路條件檢核 =================
{
  const s = pres.addSlide();
  chrome(s);
  header(s, "臨路條件", "檢核成果", 7);
  bullets(s, [
    "依國土利用調查成果之道路地物,檢核各宗基地臨路條件。",
    "主基地(番子渡頭段132筆)直接臨路,同時臨接一般道路與防汛道路;社子段基地(11筆)直接臨路。",
    "另2筆零星宗地不臨路(距最近道路約49.4m、67.7m),後續需確認通行權或設置引道。",
  ], 0.4, 1.2, 3.95, { size: 13, h: 2.6 });
  table(s, ["編號", "臨路狀態", "距道路(m)"],
    [["S001", "直接臨路(一般+防汛道路)", "0"], ["S002", "直接臨路", "0"], ["S003", "不臨路", "49.4"], ["S004", "不臨路", "67.7"]],
    0.4, 4.0, 3.95, [0.7, 2.15, 1.1]);
  const w = 8.45, h = w / 1.5057; // 裁過頂列的圖,比例重算(3507x2326)
  s.addImage({ path: path.join(SCRATCH, "road_check_map.png"), x: 4.55, y: 1.12, w, h });
  s.addText("臨路判定圖(框色=臨路狀態;fishpv 臨路評估)", { x: 4.55, y: 1.12 + h + 0.05, w, h: 0.32, fontFace: FONT, fontSize: 10, color: "555555", align: "right", margin: 0 });
}

pres.writeFile({ fileName: OUT }).then(() => console.log("written:", OUT));
