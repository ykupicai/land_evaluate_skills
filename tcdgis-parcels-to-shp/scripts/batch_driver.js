// TCDGIS 多重地籍選取批次 driver(2026-07-15/16 清潔隊 107 組實測邏輯的固化版)
// 用法(模型只做三件事,不要重寫本檔邏輯):
//   1) javascript_exec: window.__QG = [ {c:縣市,t:鄉鎮,s:段,ss:小段,nos:[地號...]}, ... ]
//   2) javascript_exec: 貼上本檔全文(會自動啟動)
//   3) 輪詢 window.__BATCH 直到 done;errors/noFound 交回報
// 設計紀律(皆為實測教訓,downgrade 模型嚴禁「優化」):
//   * 平台限流:每批加入間隔 >= RATE_MS(10.5s)。「請勿連續進行查詢」= 限流,
//     等 10s 後可重試一次(唯一允許重試的訊息)。
//   * 「查無地號: X」= 即時最終回覆,記入 noFound,不重試、不換段猜號。
//   * alertify 可見性一律 getComputedStyle(el).display!=='none'(fixed 定位使 offsetParent 恆 null)。
//   * 每批結束清空 alertify 佇列,否則舊訊息會誤判成下一批結果。
//   * 本 driver 絕不呼叫 btnInsertCADA / addnewtheme(那是 finalize_download.js 的事,只准跑一次)。
(function () {
  if (!window.__QG || !window.__QG.length) { window.__BATCH = { fatal: 'window.__QG 未載入' }; return; }
  var RATE_MS = 10500;
  var S = window.__BATCH = { i: 0, total: window.__QG.length, added: 0, errors: [], noFound: [], rateHits: 0, done: false, cur: '' };
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function vis(e) { return e && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden'; }
  function norm(s) { return String(s || '').replace(/^\[\w+\]/, '').replace(/小段/g, '').replace(/段/g, '').replace(/\s/g, '').replace(/台/g, '臺'); }
  function opts(id) { var w = dijit.byId(id); if (!w) return []; return (typeof w.getOptions === 'function') ? w.getOptions() : (w.store && w.store.data ? w.store.data.map(function (d) { return { label: d.name, value: d.id }; }) : []); }
  function setVal(id, v) { dijit.byId(id).set('value', v); }
  function tableCount() { try { return $('#tabCadalayer_SKINDA3').dataTable().fnGetNodes().length; } catch (e) { return -1; } }
  function drainAlerts(collect) {
    var out = [];
    for (var k = 0; k < 15; k++) {
      var al = document.querySelector('.alertify');
      if (!(al && vis(al)) || document.querySelector('.alertify-text')) break;
      var txt = al.textContent.replace(/Reset Focus/g, '').trim();
      var ok = al.querySelector('.alertify-button-ok') || Array.from(al.querySelectorAll('button')).find(function (b) { return /確定|OK/i.test(b.textContent); });
      if (!ok) break;
      out.push(txt); ok.click();
      if (!collect) break;
    }
    return out;
  }
  async function waitOpts(id, pred, ms) {
    var t0 = Date.now();
    while (Date.now() - t0 < ms) { var o = opts(id).filter(pred); if (o.length) return o[0]; await sleep(500); }
    return null;
  }
  async function addBatch(nosCsv, expectInc) {
    var before = tableCount();
    document.getElementById('CADANO_SKINDA3').value = nosCsv;
    document.getElementById('btnCADANO_SKINDA3').click();
    var t0 = Date.now(), msgs = [];
    while (Date.now() - t0 < 6000) {
      await sleep(400);
      msgs = msgs.concat(drainAlerts(true));
      var now = tableCount();
      if (now >= 0 && before >= 0 && now - before >= expectInc) break;
      if (msgs.length) break;
    }
    return { inc: tableCount() - before, msgs: msgs };
  }
  async function run() {
    var lastC = null, lastT = null;
    for (var i = 0; i < window.__QG.length; i++) {
      var g = window.__QG[i]; S.i = i; S.cur = g.c + g.t + g.s + (g.ss || '');
      try {
        if (g.c !== lastC) {
          var co = opts('COUNTY_SKINDA3').find(function (o) { return norm(o.label) === norm(g.c); });
          if (!co) { S.errors.push(S.cur + ':無此縣市'); continue; }
          setVal('COUNTY_SKINDA3', co.value); lastC = g.c; lastT = null; await sleep(1200);
        }
        if (g.t !== lastT) {
          var to = await waitOpts('TOWN_SKINDA3', function (o) { return norm(o.label) === norm(g.t); }, 10000);
          if (!to) { S.errors.push(S.cur + ':查無鄉鎮(異體字?列出:' + opts('TOWN_SKINDA3').map(function (o) { return o.label; }).join('/').slice(0, 120) + ')'); continue; }
          setVal('TOWN_SKINDA3', to.value); lastT = g.t; await sleep(1200);
        }
        var want = norm(g.s + (g.ss || ''));
        var se = await waitOpts('SECTOR_SKINDA3', function (o) { return norm(o.label) === want; }, 10000);
        if (!se) se = opts('SECTOR_SKINDA3').find(function (o) { return norm(o.label).indexOf(want) >= 0 || want.indexOf(norm(o.label)) >= 0; });
        if (!se) { S.errors.push(S.cur + ':查無地段(全部:' + opts('SECTOR_SKINDA3').map(function (o) { return o.label; }).join('、').slice(0, 200) + ')'); continue; }
        setVal('SECTOR_SKINDA3', se.value); await sleep(700);

        var nos = Array.from(new Set(g.nos));
        var res = await addBatch(nos.join(','), nos.length);
        var rateMsg = res.msgs.find(function (m) { return /請勿連續|10秒/.test(m); });
        if (rateMsg) {                      // 限流:等 10s 重試一次(唯一允許)
          S.rateHits++; await sleep(10500);
          res = await addBatch(nos.join(','), nos.length);
        }
        res.msgs.forEach(function (m) {
          if (/查無地號/.test(m)) S.noFound.push(S.cur + ':' + m.slice(0, 60));      // 最終回覆,不重試
          else if (/不正確|錯誤|超過/.test(m)) S.errors.push(S.cur + ':' + m.slice(0, 40));
        });
        if (/不正確/.test(res.msgs.join(''))) {   // 格式不良地號剔除重試一次
          var clean = nos.filter(function (n) { return /^\d+(-\d+)?$/.test(n); });
          if (clean.length && clean.length < nos.length) {
            await sleep(RATE_MS);
            await addBatch(clean.join(','), clean.length);
            S.errors.push(S.cur + ':剔除格式不良[' + nos.filter(function (n) { return clean.indexOf(n) < 0; }).join(',') + ']後重試');
          }
        }
        S.added = tableCount();
      } catch (e) { S.errors.push(S.cur + ':EXC ' + String(e).slice(0, 80)); }
      await sleep(RATE_MS);                 // 節流:平台下限,勿縮短
    }
    S.done = true; S.i = S.total;
  }
  run();
})();
