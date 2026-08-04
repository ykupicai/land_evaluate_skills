/* RDS 農村決策空間圖台 圖層擷取器 —— 貼進已登入分頁的 console(或用 javascript_tool 注入)
   前提:使用者本人已登入 https://rds.ardswc.gov.tw/app/ (帳密+圖形驗證碼,agent 不可代填)
   原理:底層 ArcGIS Server 被 WAF 擋直連,只能走同源 /api/proxy?<url> 並帶 X-CSRF-TOKEN;
        token 由 /api/auth/knock 動態發放(登入後隨時可刷新,會計時輪替)。
   用法:
     await __rds.count(89)                 // 查筆數
     await __rds.meta(89)                  // 查欄位/幾何
     await __rds.extract(89, 449544)       // 抓取並觸發下載 rds_89.geojson
     __rds.batch([[93,3099],[131,9259]])   // 背景批次(不阻塞);查進度看 __rds.state
     __rds.setService('ardswc_analysis_114')  // 換服務(預設 ardswc_map_114)
     await __rds.verify([93,131])          // 驗收:比對各層 count 與已抓筆數
*/
(() => {
  let SERVICE = 'ardswc_map_114';     // 另有 ardswc_analysis_114 / ardswc_map_public_114
  const svcBase = () => 'https://rds.ardswc.gov.tw/server/rest/services/ardswc/' + SERVICE + '/MapServer';
  const PAGE = 2000;                  // = maxRecordCount,勿調高(伺服器會截斷)

  const knock = () => new Promise(res => {
    const x = new XMLHttpRequest();
    x.open('GET', '/api/auth/knock', true);
    x.onreadystatechange = () => {
      if (x.readyState === 4) { try { res(JSON.parse(x.responseText).csrfToken); } catch (e) { res(null); } }
    };
    x.send();
  });

  const q = (url, tok) => new Promise(res => {
    const x = new XMLHttpRequest();
    x.open('GET', '/api/proxy?' + url, true);
    x.setRequestHeader('X-CSRF-TOKEN', tok);
    x.onreadystatechange = () => { if (x.readyState === 4) res({ s: x.status, t: x.responseText }); };
    x.send();
  });

  // 403 = token 過期,刷新後重試一次(這是唯一該重試的狀態碼)
  const qRetry = async (url, ref) => {
    let r = await q(url, ref.tok);
    if (r.s === 403) { ref.tok = await knock(); r = await q(url, ref.tok); }
    return r;
  };

  // done 累積不清空(逾時後重跑 batch 也不會遺失前次紀錄);要清用 __rds.reset()
  const state = { done: [], got: {}, running: false, cur: null, msg: '' };

  async function count(id) {
    const ref = { tok: await knock() };
    const r = await qRetry(svcBase() + '/' + id + '/query?where=1%3D1&returnCountOnly=true&f=json', ref);
    return JSON.parse(r.t).count;
  }

  async function meta(id) {
    const ref = { tok: await knock() };
    const r = await qRetry(svcBase() + '/' + id + '?f=json', ref);
    const j = JSON.parse(r.t);
    return { id, name: j.name, geom: (j.geometryType || '').replace('esriGeometry', ''),
             maxRecord: j.maxRecordCount, fields: (j.fields || []).map(f => f.name) };
  }

  async function extract(id, total) {
    const ref = { tok: await knock() };
    let feats = [];
    for (let off = 0; off < total; off += PAGE) {
      const url = svcBase() + '/' + id + '/query?where=1%3D1&outFields=*&outSR=3826'
                + '&resultOffset=' + off + '&resultRecordCount=' + PAGE + '&f=geojson';
      const r = await qRetry(url, ref);
      if (r.s !== 200) return { id, err: 'HTTP' + r.s + '@' + off, got: feats.length };
      let g; try { g = JSON.parse(r.t); } catch (e) { return { id, err: 'parse@' + off, got: feats.length }; }
      feats = feats.concat(g.features || []);
      state.msg = id + ' ' + feats.length + '/' + total;
    }
    const fc = { type: 'FeatureCollection',
                 crs: { type: 'name', properties: { name: 'urn:ogc:def:crs:EPSG::3826' } },
                 features: feats };
    const blob = new Blob([JSON.stringify(fc)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'rds_' + id + '.geojson';
    document.body.appendChild(a); a.click(); a.remove();
    state.got[id] = feats.length;
    return { id, got: feats.length, bytes: blob.size };
  }

  // 背景批次:工具呼叫常有 30s 逾時,故不回傳 Promise,進度查 __rds.state
  async function batch(jobs) {
    state.running = true;
    for (const [id, n] of jobs) {
      state.cur = id;
      try { const r = await extract(id, n); state.done.push(r.id + ':' + (r.got !== undefined ? r.got : r.err)); }
      catch (e) { state.done.push(id + ':EXC'); }
      await new Promise(s => setTimeout(s, 800));
    }
    state.running = false; state.cur = null;
  }

  // 驗收:逐層比對伺服器 count 與本 session 已抓筆數;OK/MISMATCH/未抓
  async function verify(ids) {
    const out = [];
    for (const id of ids) {
      const c = await count(id);
      const g = state.got[id];
      out.push({ id, count: c, got: g === undefined ? null : g,
                 ok: g === c ? 'OK' : (g === undefined ? '未抓(本session)' : 'MISMATCH') });
    }
    return out;
  }

  window.__rds = {
    count, meta, extract, batch, verify, state, knock,
    setService: s => { SERVICE = s; return SERVICE; },
    getService: () => SERVICE,
    reset: () => { state.done = []; state.got = {}; return 'state cleared'; },
  };
  return 'rds-extractor ready → __rds.count/meta/extract/batch/verify/setService';
})();
