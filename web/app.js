// Fog Map web analyzer. Posts a spec to the Vercel function and renders the
// ranked divergence report. All model and spec text is inserted as text, never HTML.
(function () {
  'use strict';
  const form = document.getElementById('analyze-form');
  if (!form) return;
  const API = 'api/analyze';
  const input = document.getElementById('spec-input');
  const counter = document.getElementById('spec-count');
  const button = document.getElementById('analyze-button');
  const sample = document.getElementById('load-sample');
  const clear = document.getElementById('clear-spec');
  const mode = document.getElementById('analyzer-mode');
  const status = document.getElementById('analyze-status');
  const results = document.getElementById('analyze-results');
  const sampleText = input.value;
  let limits = { max_chars: 20000, max_lines: 400 };
  let lastResult = null;

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function updateCount() {
    const chars = input.value.length;
    // Match Python's str.splitlines(): a trailing newline does not add a line.
    const lines = input.value ? input.value.replace(/(\r\n|\r|\n)$/, '').split(/\r\n|\r|\n/).length : 0;
    counter.textContent = `${lines} lines · ${chars.toLocaleString()} / ${limits.max_chars.toLocaleString()} characters`;
    counter.classList.toggle('over', chars > limits.max_chars || lines > limits.max_lines);
  }

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = 'analyze-status' + (kind ? ' ' + kind : '');
  }

  function unavailable() {
    mode.textContent = 'Analyzer offline on this host';
    mode.className = 'mode-badge muted-badge';
    button.disabled = true;
    setStatus('The web analyzer runs on the Vercel deployment. On this host, use the CLI below.', 'warn');
  }

  fetch(API, { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((info) => {
      limits = info;
      const live = info.backend !== 'offline';
      mode.textContent = live ? `Live model (${info.backend})` : 'Offline rules demo';
      mode.className = 'mode-badge' + (live ? ' live' : '');
      mode.title = info.label;
      updateCount();
    })
    .catch(unavailable);

  function markdown(result) {
    const out = ['# Fog Map ambiguity report', '', result.label, ''];
    result.findings.forEach((f, i) => {
      out.push(`## ${i + 1}. ${f.topic}: severity ${f.severity}/9`, `Line ${f.line}: ${f.spec}`, '');
      Object.entries(f.assumptions).forEach(([p, v]) => out.push(`- **${p}:** ${v}`));
      out.push('');
    });
    return out.join('\n');
  }

  function download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = el('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function card(f, rank) {
    const article = el('article', 'flag');
    const head = el('div', 'flag-head');
    head.appendChild(el('span', 'rank', String(rank).padStart(2, '0')));
    const title = el('div');
    title.appendChild(el('p', 'eyebrow', `SOURCE LINE ${f.line}`));
    title.appendChild(el('h3', 'flag-title', f.topic));
    head.appendChild(title);
    const score = el('span', 'score', String(f.severity));
    score.appendChild(el('small', '', '/9 severity'));
    head.appendChild(score);
    article.appendChild(head);
    article.appendChild(el('blockquote', '', f.spec));
    const grid = el('div', 'assumptions');
    Object.entries(f.assumptions).forEach(([persona, text]) => {
      const s = el('section', 'assumption');
      s.appendChild(el('h4', '', persona));
      s.appendChild(el('p', '', text));
      grid.appendChild(s);
    });
    article.appendChild(grid);
    article.appendChild(el('p', 'calculation',
      `${f.disagreeing_pairs} differing agent pairs × impact ${f.impact} = ${f.severity}.`));
    return article;
  }

  function render(result) {
    lastResult = result;
    results.replaceChildren();
    const summary = el('div', 'result-summary');
    summary.appendChild(el('p', 'eyebrow', result.backend === 'offline' ? 'OFFLINE RULES DEMO' : 'LIVE MODEL RESULT'));
    const n = result.findings.length;
    summary.appendChild(el('h3', '', n ? `${n} decision${n === 1 ? '' : 's'} to clarify.` : 'No divergent decisions found.'));
    summary.appendChild(el('p', 'muted', result.label));
    if (!n) {
      summary.appendChild(el('p', 'muted', result.backend === 'offline' && !result.topics_recognized
        ? 'The offline demo only recognizes five topic families (day boundaries, grace periods, team ownership, historical edits, notifications). None appear in this spec. A live model backend handles open-ended specs.'
        : 'All three readings agreed, or none addressed the same line and topic.'));
    } else {
      const actions = el('div', 'downloads');
      const copy = el('button', 'ghost', 'Copy as Markdown');
      copy.type = 'button';
      copy.addEventListener('click', () => {
        navigator.clipboard.writeText(markdown(lastResult)).then(
          () => { copy.textContent = 'Copied'; setTimeout(() => (copy.textContent = 'Copy as Markdown'), 1500); },
          () => download('fog-map-report.md', markdown(lastResult), 'text/markdown'));
      });
      const md = el('button', 'ghost', 'Download Markdown ↓');
      md.type = 'button';
      md.addEventListener('click', () => download('fog-map-report.md', markdown(lastResult), 'text/markdown'));
      const js = el('button', 'ghost', 'Download JSON ↓');
      js.type = 'button';
      js.addEventListener('click', () => download('fog-map-evidence.json', JSON.stringify(lastResult, null, 2), 'application/json'));
      actions.append(copy, md, js);
      summary.appendChild(actions);
    }
    results.appendChild(summary);
    result.findings.forEach((f, i) => results.appendChild(card(f, i + 1)));
    results.focus();
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!input.value.trim()) {
      setStatus('Paste a spec first.', 'warn');
      input.focus();
      return;
    }
    button.disabled = true;
    button.textContent = 'Analyzing…';
    setStatus('Reading the spec three ways…');
    fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ spec: input.value }),
    })
      .then((r) => r.json().catch(() => ({ error: `Server returned ${r.status}` })).then((body) => ({ ok: r.ok, body })))
      .then(({ ok, body }) => {
        if (!ok) throw new Error(body.error || 'Analysis failed');
        setStatus('');
        render(body);
      })
      .catch((error) => setStatus(error.message === 'Failed to fetch' ? 'Could not reach the analyzer. Try again in a moment.' : error.message, 'error'))
      .finally(() => {
        button.disabled = false;
        button.textContent = 'Analyze spec';
      });
  });

  input.addEventListener('input', updateCount);
  input.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') form.requestSubmit();
  });
  sample.addEventListener('click', () => { input.value = sampleText; updateCount(); input.focus(); });
  clear.addEventListener('click', () => { input.value = ''; updateCount(); input.focus(); });
  updateCount();
})();
