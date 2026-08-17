// 共用工具：限速、带重试的 fetch、简易 XML 取值
'use strict';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 全局限速器：保证相邻请求间隔 >= minGapMs（SEC 要求 <=10 req/s，我们取 <=5）
function makeThrottle(minGapMs) {
  let last = 0;
  return async function throttle() {
    const now = Date.now();
    const wait = last + minGapMs - now;
    if (wait > 0) await sleep(wait);
    last = Date.now();
  };
}

// fetch + 指数退避重试（403/429/5xx/网络错误）
async function fetchRetry(url, opts = {}, { retries = 3, backoffMs = 2000, timeoutMs = 30000 } = {}) {
  let lastErr;
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(url, { ...opts, signal: AbortSignal.timeout(timeoutMs) });
      if (res.ok) return res;
      lastErr = new Error(`HTTP ${res.status} ${res.statusText} for ${url}`);
      // 4xx 中只有限速类值得重试
      if (res.status !== 403 && res.status !== 429 && res.status < 500) throw lastErr;
    } catch (e) {
      lastErr = e;
      if (e.name === 'AbortError' || e.name === 'TimeoutError') lastErr = new Error(`timeout after ${timeoutMs}ms for ${url}`);
    }
    if (i < retries) await sleep(backoffMs * Math.pow(2, i));
  }
  throw lastErr;
}

// 取 <tag>...</tag> 的全部块
function xmlBlocks(xml, tag) {
  const out = [];
  const open = `<${tag}>`;
  const close = `</${tag}>`;
  let idx = 0;
  while (true) {
    const s = xml.indexOf(open, idx);
    if (s === -1) break;
    const e = xml.indexOf(close, s);
    if (e === -1) break;
    out.push(xml.slice(s + open.length, e));
    idx = e + close.length;
  }
  return out;
}

// 取 <tag> 内的值；若内含 <value> 则取 <value>（SEC ownership XML 惯用包装）
function xmlValue(block, tag) {
  const m = block.match(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`));
  if (!m) return null;
  const v = m[1].match(/<value>([\s\S]*?)<\/value>/);
  return (v ? v[1] : m[1]).trim();
}

module.exports = { sleep, makeThrottle, fetchRetry, xmlBlocks, xmlValue };
