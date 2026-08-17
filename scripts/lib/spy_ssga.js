// top5_weight 备源：State Street 官方 SPY 日度持仓 XLSX（slickcharts 拒数据中心 IP 时用）
// XLSX = ZIP(deflate) + XML，用内置 zlib 手工解，保持零 npm 依赖
'use strict';

const zlib = require('zlib');
const { fetchRetry } = require('./util');

const URL_ = 'https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx';

// 最小 ZIP 读取：EOCD → 中央目录 → 按名字取条目并 inflate
function unzipEntry(buf, wantName) {
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65558); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('ZIP EOCD not found');
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16); // central directory offset
  for (let i = 0; i < count; i++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('bad central directory entry');
    const method = buf.readUInt16LE(p + 10);
    const csize = buf.readUInt32LE(p + 20);
    const nameLen = buf.readUInt16LE(p + 28);
    const extraLen = buf.readUInt16LE(p + 30);
    const commentLen = buf.readUInt16LE(p + 32);
    const localOff = buf.readUInt32LE(p + 42);
    const name = buf.toString('utf8', p + 46, p + 46 + nameLen);
    if (name === wantName) {
      const ln = buf.readUInt16LE(localOff + 26);
      const le = buf.readUInt16LE(localOff + 28);
      const dataStart = localOff + 30 + ln + le;
      const data = buf.slice(dataStart, dataStart + csize);
      return method === 8 ? zlib.inflateRawSync(data) : data;
    }
    p += 46 + nameLen + extraLen + commentLen;
  }
  throw new Error(`ZIP entry not found: ${wantName}`);
}

// 极简 sheet 解析：返回 rows[][]（按单元格出现顺序，t="s" 查 sharedStrings）
function parseSheet(buf) {
  const xml = buf.toString('utf8');
  let shared = [];
  return {
    withShared(sharedBuf) {
      if (sharedBuf) shared = [...sharedBuf.toString('utf8').matchAll(/<si>([\s\S]*?)<\/si>/g)]
        .map((m) => [...m[1].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map((t) => t[1]).join(''));
      return [...xml.matchAll(/<row[^>]*>([\s\S]*?)<\/row>/g)].map((rm) =>
        [...rm[1].matchAll(/<c([^>]*)>([\s\S]*?)<\/c>/g)].map((cm) => {
          const v = cm[2].match(/<v>([\s\S]*?)<\/v>/);
          if (!v) { const is = cm[2].match(/<t[^>]*>([\s\S]*?)<\/t>/); return is ? is[1] : ''; }
          return /t="s"/.test(cm[1]) ? (shared[Number(v[1])] ?? '') : v[1];
        }));
    },
  };
}

async function fetchTop5FromSpy() {
  const res = await fetchRetry(URL_, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' } });
  const buf = Buffer.from(await res.arrayBuffer());
  let sharedBuf = null;
  try { sharedBuf = unzipEntry(buf, 'xl/sharedStrings.xml'); } catch { /* 可能无共享串表 */ }
  const rows = parseSheet(unzipEntry(buf, 'xl/worksheets/sheet1.xml')).withShared(sharedBuf);

  // 找表头行（含 Ticker 与 Weight），此前的行是基金元信息
  const hi = rows.findIndex((r) => r.some((c) => /^Ticker$/i.test(c)) && r.some((c) => /Weight/i.test(c)));
  if (hi < 0) throw new Error('SPY XLSX 未找到 Ticker/Weight 表头');
  const tickerCol = rows[hi].findIndex((c) => /^Ticker$/i.test(c));
  const weightCol = rows[hi].findIndex((c) => /Weight/i.test(c));
  const holdings = rows.slice(hi + 1)
    .map((r) => ({ symbol: (r[tickerCol] || '').trim(), weight_pct: parseFloat(r[weightCol]) }))
    .filter((h) => h.symbol && isFinite(h.weight_pct) && h.weight_pct > 0)
    .sort((a, b) => b.weight_pct - a.weight_pct);
  if (holdings.length < 100) throw new Error(`SPY 持仓解析只得 ${holdings.length} 行（预期 ~500）`);
  return holdings.map((h) => ({ ...h, weight_pct: Math.round(h.weight_pct * 100) / 100 }));
}

module.exports = { fetchTop5FromSpy };
