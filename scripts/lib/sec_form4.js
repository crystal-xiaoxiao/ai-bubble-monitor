// insider_sell_buy：SEC EDGAR Form 4 直接聚合 12 家 AI 龙头 30 日卖(S)/买(P)美元额
// 口径 = 公开市场交易（nonDerivativeTransaction 的 code S/P），衍生表与 A/M/F/G 不计。
// ARM 为外国私发行人（FPI）豁免 Section 16 无 Form 4；TSM 虽为 FPI 但内部人实际有申报（实测 2026-08）。
'use strict';

const { makeThrottle, fetchRetry, xmlBlocks, xmlValue } = require('./util');

const CIK = {
  NVDA: 1045810, AVGO: 1730168, AMD: 2488, MSFT: 789019,
  GOOGL: 1652044, META: 1326801, AMZN: 1018724, ORCL: 1341439,
  TSM: 1046179, MU: 723125, ARM: 1973239, PLTR: 1321655,
};

const WINDOW_DAYS = 30;
const FILING_LAG_DAYS = 7; // Form 4 须在交易后 2 个工作日内申报，filingDate 多取 7 天余量

function iso(d) { return d.toISOString().slice(0, 10); }

async function fetchInsiderSellBuy(env) {
  const ua = env.SEC_USER_AGENT;
  if (!ua) throw new Error('SEC_USER_AGENT 未设置（SEC 要求 UA 含联系方式，如 "ai-bubble-monitor admin you@example.com"）');
  const headers = { 'User-Agent': ua, 'Accept-Encoding': 'gzip, deflate' };
  const throttle = makeThrottle(220); // <=5 req/s，SEC 上限 10 留一半余量

  const end = new Date();
  const start = new Date(end.getTime() - WINDOW_DAYS * 864e5);
  const filingFloor = iso(new Date(start.getTime() - FILING_LAG_DAYS * 864e5));
  const windowStart = iso(start);
  const windowEnd = iso(end);

  const byTicker = {};
  const errors = [];
  let sellUsd = 0, buyUsd = 0, form4Count = 0;
  let skippedNoPrice = 0, skippedAmendments = 0, skippedAdMismatch = 0, skippedNonXml = 0;

  for (const [ticker, cik] of Object.entries(CIK)) {
    const t = { sell_usd: 0, buy_usd: 0, form4_count: 0 };
    byTicker[ticker] = t;
    try {
      await throttle();
      const subRes = await fetchRetry(
        `https://data.sec.gov/submissions/CIK${String(cik).padStart(10, '0')}.json`,
        { headers },
      );
      const sub = await subRes.json();
      const r = sub.filings && sub.filings.recent;
      if (!r) continue;
      for (let i = 0; i < r.form.length; i++) {
        if (r.filingDate[i] < filingFloor) continue;
        if (r.form[i] === '4/A') { skippedAmendments++; continue; } // 更正件 v1 不处理，计数以便审计
        if (r.form[i] !== '4') continue;
        const doc = String(r.primaryDocument[i] || '').split('/').pop(); // 去掉 xslF345X0N/ 渲染前缀
        if (!doc.endsWith('.xml')) { skippedNonXml++; continue; }
        const acc = r.accessionNumber[i].replace(/-/g, '');
        await throttle();
        let xml;
        try {
          const xmlRes = await fetchRetry(
            `https://www.sec.gov/Archives/edgar/data/${cik}/${acc}/${doc}`,
            { headers },
          );
          xml = await xmlRes.text();
        } catch (e) {
          errors.push(`${ticker} ${r.accessionNumber[i]}: ${e.message}`);
          continue;
        }
        t.form4_count++;
        form4Count++;
        for (const b of xmlBlocks(xml, 'nonDerivativeTransaction')) {
          const date = xmlValue(b, 'transactionDate');
          const code = xmlValue(b, 'transactionCode');
          if (!date || date < windowStart || date > windowEnd) continue;
          if (code !== 'S' && code !== 'P') continue;
          const ad = xmlValue(b, 'transactionAcquiredDisposedCode');
          if ((code === 'S' && ad !== 'D') || (code === 'P' && ad !== 'A')) { skippedAdMismatch++; continue; }
          const shares = parseFloat(xmlValue(b, 'transactionShares'));
          const price = parseFloat(xmlValue(b, 'transactionPricePerShare'));
          if (!isFinite(shares) || !isFinite(price) || price <= 0) { skippedNoPrice++; continue; } // 脚注定价不猜价
          const usd = shares * price;
          if (code === 'S') { t.sell_usd += usd; sellUsd += usd; }
          else { t.buy_usd += usd; buyUsd += usd; }
        }
      }
    } catch (e) {
      errors.push(`${ticker}: ${e.message}`);
    }
  }

  const okTickers = Object.keys(CIK).length - errors.filter((e) => /^[A-Z]+: /.test(e)).length;
  const zeroBuy = buyUsd < 1e6; // 买盘不足 $1M 视作近零（比值对分母极敏感，须提示）
  const ratio = buyUsd > 0 ? Math.round((sellUsd / buyUsd) * 10) / 10 : null;

  const fmt = (n) => n >= 1e9 ? `$${(n / 1e9).toFixed(2)}B` : `$${(n / 1e6).toFixed(1)}M`;
  return {
    status: errors.length === 0 ? 'ok' : (okTickers >= 8 ? 'partial' : 'error'),
    as_of: windowEnd,
    window: { start: windowStart, end: windowEnd },
    summary: `12 家 ${WINDOW_DAYS} 日（${windowStart}~${windowEnd}）：卖出 ${fmt(sellUsd)} / 买入 ${fmt(buyUsd)}` +
      (ratio === null ? '，买盘为零（比值无界）' : `，比值 ${ratio}x${zeroBuy ? '（买盘近零，比值对分母极敏感）' : ''}`) +
      `（Form 4 公开市场 S/P 口径，共 ${form4Count} 份）`,
    data: {
      sell_usd: Math.round(sellUsd), buy_usd: Math.round(buyUsd),
      ratio, zero_buy: zeroBuy, form4_count: form4Count,
      skipped_no_price: skippedNoPrice, skipped_amendments: skippedAmendments,
      skipped_ad_mismatch: skippedAdMismatch, skipped_non_xml: skippedNonXml,
      by_ticker: Object.fromEntries(Object.entries(byTicker).map(([k, v]) => [k, {
        sell_usd: Math.round(v.sell_usd), buy_usd: Math.round(v.buy_usd), form4_count: v.form4_count,
      }])),
    },
    source: 'SEC EDGAR (data.sec.gov submissions + Form 4 XML)',
    error: errors.length ? errors.join('; ').slice(0, 1500) : null,
  };
}

module.exports = { fetchInsiderSellBuy, CIK };
