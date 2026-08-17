// top5_weight：slickcharts S&P 500 成分表，前 5 行权重求和（单类口径，与 raw_history 现行一致）
'use strict';

const { execFile } = require('child_process');

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';

// slickcharts 的 Cloudflare 按 TLS 指纹拦 node fetch（undici 403），curl 能过——走 curl 子进程
function curlGet(url) {
  return new Promise((resolve, reject) => {
    execFile('curl', ['-sS', '--fail', '--max-time', '30', '-A', UA, url],
      { maxBuffer: 20 * 1024 * 1024 },
      (err, stdout, stderr) => err ? reject(new Error(`curl: ${(stderr || err.message).trim()}`)) : resolve(stdout));
  });
}

async function fetchTop5Weight() {
  const html = await curlGet('https://www.slickcharts.com/sp500');

  // 逐 <tr> 解析：symbol 取第一个 /symbol/ 链接，weight 取行内第一个百分数（列序：#, Company, Symbol, Weight, ...）
  const rows = [];
  for (const tr of html.split('<tr>').slice(1)) {
    const cell = tr.split('</tr>')[0];
    const sym = cell.match(/\/symbol\/([A-Z][A-Z0-9.\-]*)/);
    const pct = cell.match(/>\s*([\d.]+)%/);
    if (sym && pct) rows.push({ symbol: sym[1], weight_pct: parseFloat(pct[1]) });
  }
  if (rows.length < 100) throw new Error(`解析失败：只识别出 ${rows.length} 行成分（预期 ~500），页面结构可能已改版`);

  const sum = (arr) => Math.round(arr.reduce((s, r) => s + r.weight_pct, 0) * 100) / 100;
  const top5 = rows.slice(0, 5);
  const top5Pct = sum(top5);
  // 双类合并口径：Alphabet 两类（GOOGL+GOOG）都算一家
  const top5Syms = new Set(top5.map((r) => r.symbol));
  let dualExtra = 0;
  if (top5Syms.has('GOOGL') && !top5Syms.has('GOOG')) {
    const goog = rows.find((r) => r.symbol === 'GOOG');
    if (goog) dualExtra = goog.weight_pct;
  }
  const top5Dual = Math.round((top5Pct + dualExtra) * 100) / 100;
  const top10Pct = sum(rows.slice(0, 10));

  // sanity check：防解析漂移拿到错数
  const suspicious = top5Pct < 20 || top5Pct > 40 || rows[0].weight_pct > 15 || rows[0].weight_pct < 3;
  return {
    status: suspicious ? 'partial' : 'ok',
    as_of: new Date().toISOString().slice(0, 10),
    summary: `slickcharts 前 5 单类权重合计 ${top5Pct}%（${top5.map((r) => `${r.symbol} ${r.weight_pct}`).join(' / ')}）；` +
      `含 Alphabet 双类约 ${top5Dual}%；top10 ${top10Pct}%`,
    data: {
      top5_single_class_pct: top5Pct,
      top5_with_dual_class_pct: top5Dual,
      top10_pct: top10Pct,
      constituents: rows.slice(0, 10),
    },
    source: 'https://www.slickcharts.com/sp500',
    error: suspicious ? `sanity check 未通过（top5=${top5Pct}%），请人工核对解析结果` : null,
  };
}

module.exports = { fetchTop5Weight };
