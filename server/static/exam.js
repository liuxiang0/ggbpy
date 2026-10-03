/* ggbpy 试卷渲染与导出（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _examMod = GGB_EXAM.create({ t: t, setMsg: setMsg,
 *                                    getExam: function () { return exam; },
 *                                    getLang: function () { return lang; } });
 *   之后 renderExam / exportExam / escHtml 由 app.js 保留同名薄包装，调用点无需改动。
 *
 * 状态访问：exam/lang 通过 env 只读获取；t/setMsg 由 env 注入；本模块不改动 app.js 状态。
 */
window.GGB_EXAM = (function () {
  'use strict';

  function create(env) {
    // 共享助手由 app.js 注入（t：中英词条；setMsg：状态栏提示）
    var t = env.t, setMsg = env.setMsg;

      function escHtml(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }

      function renderExam() {
          var exam = env.getExam();
        var s = '';
        for (var qi = 0; qi < exam.questions.length; qi++) {
          var q = exam.questions[qi];
          s += '<div class="eq" data-i="' + qi + '">'
            + '<div class="eq-head"><span class="eq-num">' + escHtml(t('exam_q')) + (qi + 1) + '</span> '
            + '<span class="eq-sc">' + escHtml(t('exam_score')) + '</span><input class="eq-score" type="number" min="0" max="100" value="' + (q.score || 0) + '">'
            + '<span class="eq-ops">'
            + '<button data-act="up" title="↑">↑</button>'
            + '<button data-act="down" title="↓">↓</button>'
            + '<button data-act="del" class="eb-del">' + escHtml(t('exam_del')) + '</button>'
            + '</span></div>'
            + '<img class="eq-img" src="' + q.img + '" alt="q' + qi + '">'
            + '<textarea class="eq-text" rows="2" placeholder="' + escHtml(t('exam_text_ph')) + '">' + escHtml(q.text) + '</textarea>'
            + '<textarea class="eq-text eq-ans" rows="1" placeholder="' + escHtml(t('exam_ans_ph')) + '">' + escHtml(q.answer) + '</textarea>'
            + '</div>';
        }
        document.getElementById('exam-questions').innerHTML = s || '<p class="cas-tip">' + escHtml(t('exam_empty')) + '</p>';
      }

      function exportExam() {
          var exam = env.getExam();
          var lang = env.getLang();
        if (!exam.questions.length) { setMsg('错误: 试卷没有题目，请先添加题目', true); return; }
        var h = [];
        h.push('<!DOCTYPE html>');
        h.push('<html lang="' + (document.documentElement.lang || 'zh-CN') + '"><head><meta charset="utf-8">');
        h.push('<title>' + escHtml(exam.title) + '</title><style>');
        h.push('@page { size: A4; margin: 18mm; }');
        h.push('* { box-sizing: border-box; } body { font-family: "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; max-width: 820px; margin: 0 auto; color: #111; line-height: 1.6; }');
        h.push('.h1 { text-align: center; font-size: 22px; font-weight: 700; margin: 4px 0 2px; }');
        h.push('.sub { text-align: center; font-size: 14px; color: #555; margin-bottom: 10px; }');
        h.push('.info { width: 100%; border-collapse: collapse; margin: 8px 0; }');
        h.push('.info td { border-bottom: 1px solid #999; padding: 6px 2px; font-size: 13px; width: 25%; }');
        h.push('.meta { font-size: 13px; text-align: center; color: #333; margin: 6px 0; }');
        h.push('.inst { font-size: 13px; color: #444; border-left: 3px solid #2563eb; padding: 4px 10px; background: #f8fafc; margin: 8px 0 14px; white-space: pre-wrap; }');
        h.push('.q { margin: 16px 0; page-break-inside: avoid; }');
        h.push('.q-head { font-size: 14px; font-weight: 600; margin-bottom: 4px; }');
        h.push('.q-text { font-size: 14px; white-space: pre-wrap; margin: 4px 0; }');
        h.push('.q-img { display: block; max-width: 70%; max-height: 300px; margin: 8px auto; }');
        h.push('.q-ans { font-size: 12px; color: #b45309; margin-top: 6px; }');
        h.push('.blank { height: 56px; border-bottom: 1px solid #bbb; margin-top: 10px; }');
        h.push('.footer { margin-top: 26px; text-align: right; font-size: 12px; color: #9ca3af; }');
        h.push('@media print { .q { page-break-inside: avoid; } }');
        h.push('</style></head><body>');
        h.push('<div class="h1">' + escHtml(exam.title) + '</div>');
        if (exam.subtitle) h.push('<div class="sub">' + escHtml(exam.subtitle) + '</div>');
        h.push('<table class="info"><tr>');
        h.push('<td>' + escHtml(t('exam_school_l')) + (exam.school ? '：' + escHtml(exam.school) : '__________') + '</td>');
        h.push('<td>' + escHtml(t('exam_klass_l')) + (exam.klass ? '：' + escHtml(exam.klass) : '__________') + '</td>');
        h.push('<td>' + escHtml(t('exam_name_l')) + (exam.name ? '：' + escHtml(exam.name) : '__________') + '</td>');
        h.push('<td>' + escHtml(t('exam_sid_l')) + (exam.sid ? '：' + escHtml(exam.sid) : '__________') + '</td>');
        h.push('</tr></table>');
        h.push('<div class="meta">' + escHtml(t('exam_total_l')) + ' <b>' + escHtml(exam.total) + '</b> ' + escHtml(t('exam_total_unit')) + '　' + escHtml(t('exam_time_l')) + ' <b>' + escHtml(exam.minutes) + '</b> ' + escHtml(t('exam_min_unit')) + '</div>');
        if (exam.instructions) h.push('<div class="inst">' + escHtml(exam.instructions) + '</div>');
        var totalScore = 0;
        for (var ei = 0; ei < exam.questions.length; ei++) {
          var q2 = exam.questions[ei];
          totalScore += q2.score || 0;
          h.push('<div class="q"><div class="q-head">' + escHtml(t('exam_q')) + (ei + 1) + '（' + (q2.score || 0) + ' ' + escHtml(t('exam_score_l')) + '）</div>');
          if (q2.text) h.push('<div class="q-text">' + escHtml(q2.text) + '</div>');
          if (q2.img) h.push('<img class="q-img" src="' + q2.img + '" alt="Q' + (ei + 1) + '">');
          if (exam.showAnswers && q2.answer) h.push('<div class="q-ans">' + escHtml(t('exam_ans_l')) + escHtml(q2.answer) + '</div>');
          h.push('<div class="blank"></div></div>');
        }
        h.push('<div class="footer">' + escHtml(t('exam_total_l')) + ' ' + totalScore + ' ' + escHtml(t('exam_score_l')) + '</div>');
        h.push('</body></html>');
        var blob = new Blob([h.join('')], { type: 'text/html;charset=utf-8' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '试卷_' + (exam.title || 'exam').replace(/[\\/:*?"<>|]/g, '_') + '.html';
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 800);
        setMsg(lang === 'en' ? 'Exported exam HTML (print to save as PDF)' : '已导出试卷 HTML（浏览器打印可存为 PDF）', false);
      }

    return { renderExam: renderExam, exportExam: exportExam, escHtml: escHtml };
  }

  return { create: create };
})();
