// TCDGIS 收尾 driver:全範圍定位 → 匯出Excel → 建主題 → 加入主題(一次) → 下載 shp
// 用法:
//   1) javascript_exec: window.__FIN = { theme: '主題名(不可與既有重複)' }
//   2) javascript_exec: 貼上本檔全文(自動啟動)
//   3) 輪詢 window.__FINST 直到 done;之後去 %USERPROFILE%\Downloads 找 zip 與 xls
// 紀律(實測教訓,嚴禁更動):
//   * 先匯出 Excel 再搞主題——前端清單跳轉/逾時即消失,屬性先落地。
//   * btnInsertCADA 只呼叫一次;它的 confirm 只按一次「確定」;之後任何重複的
//     「確定將…新增至主題?」一律按「取消」(多按確定=重複插入,幾何加倍)。
//   * 建主題走 addnewtheme() 的 prompt;5 秒內 prompt 沒出現(alertify 佇列病態)
//     → fallback 直接 POST INSERTNEWTHEME。
//   * 下載成功的訊號=Downloads 出現 zip;network 的 ERR_ABORTED 是正常交接,不是失敗。
(function () {
  var CFG = window.__FIN || {};
  if (!CFG.theme) { window.__FINST = { fatal: '__FIN.theme 未設定' }; return; }
  var S = window.__FINST = { step: 'start', done: false, log: [], inserted: false };
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function vis(e) { return e && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden'; }
  function alertEl() { var al = document.querySelector('.alertify'); return (al && vis(al)) ? al : null; }
  function clickOk(al) { var b = al.querySelector('.alertify-button-ok') || Array.from(al.querySelectorAll('button')).find(function (x) { return /確定|OK/i.test(x.textContent); }); if (b) { b.click(); return true; } return false; }
  function clickCancel(al) { var b = al.querySelector('.alertify-button-cancel') || Array.from(al.querySelectorAll('button')).find(function (x) { return /取消/.test(x.textContent); }); if (b) { b.click(); return true; } return false; }
  async function drain(maxMs) {
    var t0 = Date.now();
    while (Date.now() - t0 < maxMs) {
      var al = alertEl();
      if (!al) { await sleep(300); continue; }
      var txt = al.textContent.replace(/Reset Focus/g, '').trim();
      if (document.querySelector('.alertify-text')) return 'prompt';       // 輸入框到了,交呼叫端
      if (/新增至主題/.test(txt)) {                                        // 多餘 confirm:取消
        if (S.inserted) { clickCancel(al); S.log.push('cancel extra confirm'); }
        else return 'confirm';
      } else { S.log.push('drain:' + txt.slice(0, 30)); clickOk(al); }
      await sleep(300);
    }
    return 'timeout';
  }
  async function run() {
    try {
      S.step = 'zoom'; try { zoomtoCADAAll('SKINDA3'); } catch (e) { S.log.push('zoom ERR ' + e); }
      await sleep(5000);
      S.step = 'export-excel'; BatchCADAToExcelMS('SKINDA3');   // 屬性先落地
      await sleep(6000); await drain(2000);
      S.step = 'create-theme';
      var exists = dijit.byId('cmbtheme').getOptions().some(function (o) { return o.label === CFG.theme; });
      if (!exists) {
        try { addnewtheme(); } catch (e) { S.log.push('addnewtheme ERR ' + e); }
        var got = await drain(5000);
        if (got === 'prompt') {
          document.querySelector('.alertify-text').value = CFG.theme;
          clickOk(alertEl()); S.log.push('theme via prompt');
        } else {                                               // fallback: 直接 POST
          await new Promise(function (res) {
            $.post('ws_data.ashx?CMD=INSERTNEWTHEME&TOKEN=' + layerToken, { VAL: CFG.theme })
              .always(function () { try { GetThemebyUID(CFG.theme); } catch (e) { } res(); });
          });
          S.log.push('theme via INSERTNEWTHEME POST');
        }
        await sleep(2500);
      }
      if (dijit.byId('cmbtheme').get('displayedValue') !== CFG.theme) { try { GetThemebyUID(CFG.theme); } catch (e) { } await sleep(2000); }
      S.themeSelected = dijit.byId('cmbtheme').get('displayedValue');
      S.step = 'insert-once'; await drain(1500);
      btnInsertCADA('SKINDA3');                                 // 只此一次
      var got2 = await drain(6000);
      if (got2 === 'confirm') { clickOk(alertEl()); S.inserted = true; S.log.push('insert confirmed once'); }
      else S.log.push('insert confirm not seen: ' + got2);
      await sleep(10000); await drain(3000);                    // 伺服器寫入 + 清多餘 confirm
      S.step = 'download'; downloadallshp();
      await sleep(8000);
      S.step = 'done'; S.done = true;
    } catch (e) { S.fatal = String(e).slice(0, 120); S.done = true; }
  }
  run();
})();
