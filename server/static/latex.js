/* ggbpy LaTeX 序列化（表达式/几何对象 → LaTeX，P2 前端拆分）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _latex = GGB_LATEX.create({ get: _stateGet });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：CMD_W, FN_T, FN_W, GREEK_T, GREEK_W
 */
window.GGB_LATEX = (function () {
  'use strict';

  function create(env) {
      function toLatex(s) {
        var CMD_W = env.get('CMD_W'), FN_T = env.get('FN_T'), FN_W = env.get('FN_W'), GREEK_T = env.get('GREEK_T'), GREEK_W = env.get('GREEK_W');
        var out = '';
        var i = 0;
        var stack = [];  // 括号栈：'p'普通 '(' / 'f'函数 '(' / 's'sqrt{ / 'a'abs|
        while (i < s.length) {
          var ch = s[i];
          var hit = null;
          // 命令名 [ → \text{...} 保持
          for (var ci = 0; ci < CMD_W.length; ci++) {
            var cm = CMD_W[ci];
            if (s.slice(i, i + cm.length) === cm && s[i + cm.length] === '[') { hit = ['cmd', cm]; break; }
          }
          if (!hit) {
            for (var fi = 0; fi < FN_W.length; fi++) {
              var fw = FN_W[fi];
              if (s.slice(i, i + fw.length) === fw && s[i + fw.length] === '(') { hit = ['fn', fw]; break; }
            }
          }
          if (!hit) {
            for (var gi = 0; gi < GREEK_W.length; gi++) {
              var gw = GREEK_W[gi];
              if (s.slice(i, i + gw.length) === gw && !/[a-zA-Z]/.test(s[i + gw.length] || ' ')) { hit = ['gk', gw]; break; }
            }
          }
          if (hit && hit[0] === 'cmd') {
            out += '\\text{' + hit[1] + '}';
            i += hit[1].length;
            continue;
          }
          if (hit && hit[0] === 'fn') {
            if (hit[1] === 'sqrt') { out += '\\sqrt{'; stack.push('s'); }
            else if (hit[1] === 'abs') { out += '\\left|'; stack.push('a'); }
            else { out += FN_T[hit[1]] + '\\left('; stack.push('f'); }
            i += hit[1].length + 1;  // 跳过函数名与结构性的 '('
            continue;
          }
          if (hit && hit[0] === 'gk') {
            out += GREEK_T[hit[1]];
            i += hit[1].length;
            continue;
          }
          if (ch === '(') { out += '('; stack.push('p'); i++; continue; }
          if (ch === ')') {
            var kind = stack.pop() || 'p';
            if (kind === 's') out += '}';
            else if (kind === 'a') out += '\\right|';
            else if (kind === 'f') out += '\\right)';
            else out += ')';
            i++;
            continue;
          }
          if (ch === '^' || ch === '_') {
            var nx = s[i + 1];
            if (nx === '(' || nx === '{') {
              var depth = 1;
              var j = i + 2;
              var inner = '';
              while (j < s.length && depth > 0) {
                if (s[j] === '(' || s[j] === '{') depth++;
                else if (s[j] === ')' || s[j] === '}') { depth--; if (depth === 0) break; }
                inner += s[j];
                j++;
              }
              out += (ch === '^' ? '^{' : '_{') + toLatex(inner) + '}';
              i = j + 1;
              continue;
            }
            if (/[A-Za-z0-9\\u4e00-\\u9fff]/.test(nx || '')) {
              out += (ch === '^' ? '^{' : '_{') + nx + '}';
              i += 2;
              continue;
            }
            out += ch;
            i++;
            continue;
          }
          if (ch === '~') { out += '\\sim '; i++; continue; }
          if (ch === '*') { out += '\\cdot '; i++; continue; }
          if (ch === '<' && s[i + 1] === '=') { out += '\\le '; i += 2; continue; }
          if (ch === '>' && s[i + 1] === '=') { out += '\\ge '; i += 2; continue; }
          if (ch === '=') { out += '='; i++; continue; }
          out += ch;
          i++;
        }
        return out;
      }

    return {
      toLatex: toLatex,
    };
  }

  return { create: create };
})();
