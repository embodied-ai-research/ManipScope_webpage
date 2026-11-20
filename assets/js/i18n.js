/* Bilingual UI. Keep original DOM nodes so links, listeners and media stay live. */
(function () {
  'use strict';
  var dictionary = window.__ZH__ || {};
  var originals = new WeakMap();
  var attributes = new WeakMap();
  var lang = 'en';
  var button = document.querySelector('.language-toggle');
  var skip = 'script,style,code,pre,svg,.instr,.info tr:first-child em,[data-i18n-skip]';
  var normalize = function (s) { return s.replace(/\s+/g, ' ').trim(); };
  function translate(s) {
    var key = normalize(s), value = dictionary[key];
    if (value === undefined) {
      // Preserve counts, family identifiers and direction markers in generated labels.
      var match = key.match(/^(D[1-6]\s*[·—]?\s*|←\s*)(.+?)(\s*→)?$/);
      if (match && dictionary[match[2]]) value = match[1] + dictionary[match[2]] + (match[3] || '');
      var arrow = key.match(/^(.+) →$/);
      if (arrow && dictionary[arrow[1]]) value = dictionary[arrow[1]] + ' →';
      var criterion = key.match(/^criterion: (.+)$/);
      if (criterion) value = '判据：' + (dictionary[criterion[1]] || criterion[1]);
      var count = key.match(/^(Seen|Unseen|Base tasks not used by any scene|Agent tool calls for this episode) \((\d+)\)$/);
      if (count) value = ({Seen:'已见指令',Unseen:'未见指令','Base tasks not used by any scene':'未被场景使用的基础任务','Agent tool calls for this episode':'本回合智能体工具调用'})[count[1]] + '（' + count[2] + '）';
      var scenes = key.match(/^(D[1-6]) · (\d+) scenes$/);
      if (scenes) value = scenes[1] + ' · ' + scenes[2] + ' 个场景';
    }
    return value === undefined ? s : s.match(/^\s*/)[0] + value + s.match(/\s*$/)[0];
  }
  function eligible(el) { return el && !el.closest(skip); }
  function apply(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      if (!eligible(node.parentElement)) continue;
      if (!originals.has(node)) originals.set(node, node.nodeValue);
      var source = originals.get(node);
      var target = lang === 'zh' ? translate(source) : source;
      if (node.nodeValue !== target) node.nodeValue = target;
    }
    root.querySelectorAll('[placeholder],[aria-label],[title],[alt]').forEach(function (el) {
      if (!eligible(el)) return;
      var saved = attributes.get(el);
      if (!saved) {
        saved = {};
        ['placeholder','aria-label','title','alt'].forEach(function (key) {
          if (el.hasAttribute(key)) saved[key] = el.getAttribute(key);
        });
        attributes.set(el, saved);
      }
      Object.keys(saved).forEach(function (key) {
        var value = lang === 'zh' ? translate(saved[key]) : saved[key];
        if (el.getAttribute(key) !== value) el.setAttribute(key, value);
      });
    });
  }
  var originalTitle = document.title;
  function setLang(next, updateUrl) {
    lang = next === 'zh' ? 'zh' : 'en';
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    document.documentElement.dataset.lang = lang;
    apply(document.body);
    document.title = lang === 'zh' ? originalTitle.split(' | ').map(translate).join(' | ').replace(/ Docs$/, ' 文档') : originalTitle;
    if (button) {
      button.setAttribute('aria-label', lang === 'en' ? 'Switch to Chinese' : '切换为英文');
      button.setAttribute('aria-pressed', lang === 'zh' ? 'true' : 'false');
    }
    try { localStorage.setItem('manipscope.lang', lang); } catch (_) {}
    if (updateUrl) {
      var url = new URL(location.href);
      url.searchParams.set('lang', lang);
      history.replaceState(null, '', url);
    }
    // Keep the explicit choice when following internal links, including in private mode.
    document.querySelectorAll('a[href]').forEach(function (a) {
      var raw = a.getAttribute('href');
      if (!raw || raw[0] === '#' || a.hasAttribute('download')) return;
      var url;
      try { url = new URL(raw, location.href); } catch (_) { return; }
      if (url.origin !== location.origin || !/\/index\.html$|\/$/.test(url.pathname)) return;
      url.searchParams.set('lang', lang);
      a.href = url.href;
    });
    document.dispatchEvent(new CustomEvent('languagechange', {detail:lang}));
  }
  var initial = new URLSearchParams(location.search).get('lang');
  if (initial !== 'en' && initial !== 'zh') {
    try { initial = localStorage.getItem('manipscope.lang'); } catch (_) {}
  }
  window.ManipScopeI18n = {
    getLanguage: function () { return lang; },
    translate: function (s) { return lang === 'zh' ? translate(s) : s; },
    searchText: function (s) {
      if (lang !== 'zh') return s;
      // Search prose is flattened at build time; retain exact phrase translations.
      Object.keys(dictionary).sort(function(a,b){return b.length-a.length;}).forEach(function(key){
        if (key.length > 3) s = s.split(key).join(dictionary[key]);
      });
      return s;
    }
  };
  setLang(initial, false);
  if (button) button.addEventListener('click', function () { setLang(lang === 'en' ? 'zh' : 'en', true); });
})();
