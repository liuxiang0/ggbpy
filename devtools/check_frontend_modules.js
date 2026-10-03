#!/usr/bin/env node
/* 前端模块静态守卫（**函数作用域**级）：server/static/*.js 里引用的标识符必须能解析——
 *   ① 本函数内的声明/参数 ② 外层函数（含 create() 作用域）或模块顶层的声明 ③ env ④ 已知全局/内建
 * 否则报「未定义标识符」。作用域级检查是刻意的：文件级检查抓不到「某个函数漏注入状态」这类 bug。
 *
 * 动机（真实事故）：draw2d 抽取时状态分析漏了 `cssH`（多声明 `var cssW = 0, cssH = 0, dpr = 1;`），
 * 模块内直接引用 → 运行时 ReferenceError（被 render 的 try/catch 吞掉）→ 对象列表面板不刷新，
 * 浏览器矩阵只表现为超时。此守卫在浏览器测试之前就能定位。
 *
 * 用法：node devtools/check_frontend_modules.js [文件...]
 * 退出码：0 干净 / 1 有未定义标识符
 */
const fs = require('fs');
const path = require('path');

const GLOBALS = new Set(['window', 'document', 'console', 'Math', 'JSON', 'Object', 'Array', 'String', 'Number',
  'Boolean', 'Date', 'RegExp', 'Error', 'Map', 'Set', 'Promise', 'Blob', 'URL', 'Image', 'Event',
  'KeyboardEvent', 'MouseEvent', 'PointerEvent', 'CustomEvent', 'FileReader', 'navigator', 'location', 'history',
  'localStorage', 'sessionStorage', 'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'encodeURIComponent',
  'decodeURIComponent', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'requestAnimationFrame',
  'cancelAnimationFrame', 'alert', 'confirm', 'prompt', 'fetch', 'btoa', 'atob', 'structuredClone', 'Intl',
  'performance', 'undefined', 'NaN', 'Infinity', 'null', 'true', 'false', 'this', 'arguments', 'env',
  'Function', 'Symbol', 'BigInt', 'Proxy', 'Reflect', 'WeakMap', 'WeakSet', 'ArrayBuffer', 'Uint8Array',
  'Float32Array', 'Float64Array', 'Int32Array', 'TextEncoder', 'TextDecoder', 'globalThis', 'escape', 'unescape',
  'getComputedStyle', 'devicePixelRatio', 'innerWidth', 'innerHeight', 'isArray', 'from', 'keys', 'values',
  'entries', 'assign', 'freeze', 'max', 'min', 'abs', 'sqrt', 'sin', 'cos', 'tan', 'atan2', 'PI', 'round',
  'floor', 'ceil', 'pow', 'log', 'exp', 'hypot', 'sign', 'trunc', 'random']);
const KEYWORDS = new Set(['if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default', 'break', 'continue',
  'return', 'function', 'var', 'let', 'const', 'new', 'typeof', 'instanceof', 'in', 'of', 'delete', 'void',
  'try', 'catch', 'finally', 'throw', 'class', 'extends', 'super', 'yield', 'await', 'async', 'static', 'get', 'set']);

function looksLikeRegex(out) {
  const m = out.match(/([A-Za-z0-9_$\]\)])\s*$/);
  if (!m) return true;
  return false;
}

/** 剥离字符串/注释/正则，保留换行（行号可对齐）。 */
function stripLiterals(src) {
  let out = '', i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === '/' && src[i + 1] === '/') { while (i < src.length && src[i] !== '\n') i++; }
    else if (c === '/' && src[i + 1] === '*') { i += 2; while (i + 1 < src.length && !(src[i] === '*' && src[i + 1] === '/')) i++; i += 2; }
    else if (c === "'" || c === '"') { const q = c; out += "''"; i++; while (i < src.length) { if (src[i] === '\\') { i += 2; continue; } if (src[i] === q) { i++; break; } i++; } }
    else if (c === '`') { out += '``'; i++; while (i < src.length) { if (src[i] === '\\') { i += 2; continue; } if (src[i] === '`') { i++; break; } i++; } }
    else if (c === '/' && looksLikeRegex(out)) {
      out += '0'; i++;
      let inClass = false;
      while (i < src.length) {
        const d = src[i];
        if (d === '\\') { i += 2; continue; }
        if (d === '[') inClass = true;
        else if (d === ']') inClass = false;
        else if (d === '/' && !inClass) { i++; break; }
        else if (d === '\n') break;
        i++;
      }
      while (i < src.length && /[a-z]/.test(src[i])) i++;
    } else { out += c; i++; }
  }
  return out;
}

function matchBrace(src, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return i; }
  }
  return src.length;
}

function declsIn(src, from, to) {
  const out = new Set();
  const seg = src.slice(from, to);
  for (const m of seg.matchAll(/\b(?:var|let|const)\s+([^;\n]+)/g)) {
    let depth = 0, cur = '';
    const parts = [];
    for (const ch of m[1]) {
      if ('{['.indexOf(ch) >= 0) depth++;
      if ('}]'.indexOf(ch) >= 0) depth--;
      if (ch === ',' && depth === 0) { parts.push(cur); cur = ''; } else cur += ch;
    }
    parts.push(cur);
    parts.forEach(p => { const t = p.match(/^\s*([A-Za-z_$][\w$]*)/); if (t) out.add(t[1]); });
  }
  for (const m of seg.matchAll(/\bfunction\s+([A-Za-z_$][\w$]*)/g)) out.add(m[1]);
  for (const m of seg.matchAll(/\bcatch\s*\(\s*([A-Za-z_$][\w$]*)/g)) out.add(m[1]);
  for (const m of seg.matchAll(/\(([^()]*)\)\s*(?:=>|\{)/g)) {
    m[1].split(',').forEach(p => { const t = p.match(/^\s*([A-Za-z_$][\w$]*)/); if (t) out.add(t[1]); });
  }
  for (const m of seg.matchAll(/\bfunction\s*[A-Za-z_$\w]*\s*\(([^)]*)\)/g)) {
    m[1].split(',').forEach(p => { const t = p.match(/^\s*([A-Za-z_$][\w$]*)/); if (t) out.add(t[1]); });
  }
  return out;
}

function usedIn(src, from, to) {
  const out = new Map();
  const seg = src.slice(from, to);
  const offsetLine = src.slice(0, from).split('\n').length - 1;
  for (const m of seg.matchAll(/(^|[^.\w$])([A-Za-z_$][\w$]*)/g)) {
    const name = m[2];
    if (KEYWORDS.has(name) || GLOBALS.has(name)) continue;
    const after = seg.slice(m.index + m[0].length);
    if (/^\s*:/.test(after)) continue;            // 对象字面量的键
    const line = offsetLine + seg.slice(0, m.index).split('\n').length;
    if (!out.has(name)) out.set(name, line);
  }
  return out;
}

function subtractRanges(from, to, ranges) {
  let segs = [[from, to]];
  for (const [a, b] of ranges) {
    const next = [];
    for (const [x, y] of segs) {
      if (b <= x || a >= y) { next.push([x, y]); continue; }
      if (a > x) next.push([x, a]);
      if (b < y) next.push([b, y]);
    }
    segs = next;
  }
  return segs;
}

/** 在 [from,to) 内声明、但**不属于任何嵌套函数**的名字（用于精确作用域链）。 */
function scopeDecls(src, from, to, fns) {
  const inner = fns.filter(f => f.start >= from && f.end <= to && !(f.start === from && f.end === to));
  const nested = inner.map(f => [f.start, f.end + 1]);
  const out = new Set();
  for (const [a, b] of subtractRanges(from, to, nested)) declsIn(src, a, b).forEach(d => out.add(d));
  // 嵌套函数**名字**属于本层作用域（兄弟函数互相可见），只是其函数体不算本层
  inner.forEach(f => { if (f.name !== '(anon)') out.add(f.name); });
  return out;
}

function checkFile(file) {
  const src = stripLiterals(fs.readFileSync(file, 'utf8'));
  const fns = [];
  for (const m of src.matchAll(/\bfunction\s*([A-Za-z_$][\w$]*)?\s*\(([^)]*)\)\s*\{/g)) {
    const brace = m.index + m[0].length - 1;
    fns.push({ name: m[1] || '(anon)', params: m[2] || '', start: m.index,
                end: matchBrace(src, brace), brace: brace });
  }
  const moduleScope = scopeDecls(src, 0, src.length, fns);
  const missing = [];
  for (const fn of fns) {
    const own = declsIn(src, fn.start, fn.end);
    fn.params.split(',').forEach(p => { const t = p.match(/^\s*([A-Za-z_$][\w$]*)/); if (t) own.add(t[1]); });
    const chain = new Set(moduleScope);
    for (const anc of fns) {                       // 祖先函数：只取其本层声明（排除嵌套函数内）
      if (anc !== fn && anc.start < fn.start && anc.end > fn.end) {
        scopeDecls(src, anc.start, anc.end, fns).forEach(d => chain.add(d));
      }
    }
    for (const [name, line] of usedIn(src, fn.start, fn.end)) {
      if (own.has(name) || chain.has(name)) continue;
      missing.push(`${fn.name}(): ${name}@L${line}`);
    }
  }
  return { file, missing };
}

const args = process.argv.slice(2);
const files = args.length ? args : ['keyboard.js', 'exam.js', 'panels.js', 'draw2d.js']
  .map(f => path.join(__dirname, '..', 'server', 'static', f));
let bad = 0;
for (const f of files) {
  if (!fs.existsSync(f)) { console.log('跳过（不存在）: ' + f); continue; }
  const r = checkFile(f);
  if (r.missing.length) {
    bad = 1;
    console.log('FAIL ' + path.basename(f) + ' 未解析标识符: ' + r.missing.slice(0, 8).join(', ')
      + (r.missing.length > 8 ? ` …（共 ${r.missing.length}）` : ''));
  } else {
    console.log('OK   ' + path.basename(f) + ' 全部标识符可解析（函数作用域检查）');
  }
}
process.exit(bad);
