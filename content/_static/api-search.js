import Fuse from './fuse.min.mjs';

const SCRIPT_ID = 'tvb-api-search-script';
const KIND_ALIASES = {
  cls: 'class',
  class: 'class',
  mod: 'module',
  module: 'module',
  fn: 'function',
  func: 'function',
  function: 'function',
  meth: 'method',
  method: 'method',
  trait: 'trait',
  attr: 'attribute',
  attribute: 'attribute',
};

const KIND_BADGES = {
  module: 'mod',
  class: 'cls',
  method: 'meth',
  function: 'fn',
  trait: 'trait',
  attribute: 'attr',
};

function makeAcronym(name) {
  const short = name.split('.').pop() || name;
  const parts = short.match(/[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|[0-9]+/g) || [];
  return parts.map((p) => p[0]).join('').toLowerCase();
}

function isSubsequence(needle, haystack) {
  let i = 0;
  for (let j = 0; j < haystack.length && i < needle.length; j++) {
    if (haystack[j] === needle[i]) i++;
  }
  return i === needle.length;
}

function parseQuery(raw) {
  const tokens = raw.trim().split(/\s+/).filter(Boolean);
  let kindFilter = null;
  const terms = [];
  for (const tok of tokens) {
    const colon = tok.indexOf(':');
    if (colon > 0) {
      const prefix = tok.slice(0, colon).toLowerCase();
      if (KIND_ALIASES[prefix]) {
        kindFilter = KIND_ALIASES[prefix];
        const rest = tok.slice(colon + 1);
        if (rest) terms.push(rest);
        continue;
      }
    }
    terms.push(tok);
  }
  return { kindFilter, query: terms.join(' ') };
}

function injectStyles() {
  if (document.getElementById('tvb-api-search-styles')) return;
  const style = document.createElement('style');
  style.id = 'tvb-api-search-styles';
  style.textContent = `
    #tvb-api-trigger {
      position: fixed;
      right: 1.15rem;
      bottom: 1.15rem;
      z-index: 9990;
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.48rem 0.85rem;
      border-radius: 9999px;
      border: 1px solid var(--myst-color-accent-surface-border, #cbd5e1);
      background: var(--myst-color-surface-header, #ffffff);
      color: var(--myst-color-text, #1c1e21);
      font: 500 13px/1.2 "Inter", system-ui, sans-serif;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
      cursor: pointer;
      transition: transform 0.12s ease, border-color 0.12s ease;
    }
    #tvb-api-trigger:hover {
      border-color: var(--myst-color-primary, #1e40af);
      transform: translateY(-1px);
    }
    #tvb-api-trigger kbd, .tvb-api-kbd {
      font: 500 11px/1 "JetBrains Mono", ui-monospace, monospace;
      padding: 0.15rem 0.35rem;
      border-radius: 4px;
      background: var(--myst-color-bg-secondary, #e9e7e1);
      color: var(--myst-color-text-secondary, #4b5563);
      border: 1px solid rgba(128, 128, 128, 0.25);
    }
    #tvb-api-backdrop {
      position: fixed;
      inset: 0;
      z-index: 10000;
      display: none;
      align-items: flex-start;
      justify-content: center;
      padding: 10vh 1rem 1rem;
      background: rgba(15, 23, 42, 0.55);
      backdrop-filter: blur(2px);
    }
    #tvb-api-backdrop.open { display: flex; }
    #tvb-api-modal {
      width: min(720px, 100%);
      max-height: 76vh;
      display: flex;
      flex-direction: column;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--myst-color-accent-surface-border, #cbd5e1);
      background: var(--myst-color-surface-header, #fbfaf7);
      color: var(--myst-color-text, #1c1e21);
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
      font-family: "Inter", system-ui, sans-serif;
    }
    #tvb-api-header {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.75rem 0.9rem;
      border-bottom: 1px solid var(--myst-color-bg-secondary, #e5e7eb);
    }
    #tvb-api-input {
      flex: 1;
      border: 0;
      outline: none;
      background: transparent;
      color: inherit;
      font: 400 15px/1.4 "Inter", system-ui, sans-serif;
    }
    #tvb-api-filters {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      padding: 0.45rem 0.9rem;
      border-bottom: 1px solid var(--myst-color-bg-secondary, #e5e7e1);
      background: var(--myst-color-surface, #efece6);
      font-size: 12px;
    }
    .tvb-api-chip {
      padding: 0.18rem 0.55rem;
      border-radius: 9999px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--myst-color-text-secondary, #4b5563);
      cursor: pointer;
      font: 500 12px/1.3 inherit;
    }
    .tvb-api-chip.active {
      background: var(--myst-color-active-surface, #eef2ff);
      color: var(--myst-color-active, #1e40af);
      border-color: var(--myst-color-accent-surface-border, #c7d2fe);
    }
    #tvb-api-results {
      overflow-y: auto;
      margin: 0;
      padding: 0.35rem;
      list-style: none;
    }
    .tvb-api-row {
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
      padding: 0.55rem 0.7rem;
      border-radius: 8px;
      cursor: pointer;
      text-decoration: none;
      color: inherit;
    }
    .tvb-api-row[aria-selected="true"], .tvb-api-row:hover {
      background: var(--myst-color-active-surface, #eef2ff);
    }
    .tvb-api-row-top {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      min-width: 0;
    }
    .tvb-api-badge {
      flex-shrink: 0;
      font: 600 11px/1.1 "JetBrains Mono", ui-monospace, monospace;
      padding: 0.18rem 0.4rem;
      border-radius: 4px;
      text-transform: uppercase;
      background: var(--myst-color-bg-secondary, #e5e7eb);
      color: var(--myst-color-primary, #1e40af);
    }
    .tvb-api-name {
      font: 600 13.5px/1.3 "JetBrains Mono", ui-monospace, monospace;
      color: var(--myst-color-text, #1c1e21);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .tvb-api-mod {
      margin-left: auto;
      font: 400 11.5px/1.2 "JetBrains Mono", ui-monospace, monospace;
      color: var(--myst-color-text-secondary, #6b7280);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .tvb-api-sub {
      font-size: 12px;
      color: var(--myst-color-text-secondary, #4b5563);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    #tvb-api-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.45rem 0.9rem;
      font-size: 11.5px;
      color: var(--myst-color-text-secondary, #6b7280);
      border-top: 1px solid var(--myst-color-bg-secondary, #e5e7eb);
      background: var(--myst-color-surface, #efece6);
    }
    .tvb-api-empty {
      padding: 1.5rem 1rem;
      text-align: center;
      color: var(--myst-color-text-secondary, #6b7280);
      font-size: 13px;
    }
  `;
  document.head.appendChild(style);
}

function initPalette() {
  const scriptEl = document.getElementById(SCRIPT_ID);
  if (!scriptEl || document.getElementById('tvb-api-backdrop')) return;
  const symbolsRel = scriptEl.getAttribute('data-symbols') || 'api-symbols.json';
  const symbolsUrl = new URL(symbolsRel, window.location.href).href;
  const baseRootUrl = symbolsUrl.replace(/api-symbols\.json$/, '');

  injectStyles();

  const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent);
  const shortcutLabel = isMac ? '⌘⇧K' : 'Ctrl+Shift+K';

  const trigger = document.createElement('button');
  trigger.id = 'tvb-api-trigger';
  trigger.type = 'button';
  trigger.setAttribute('aria-label', 'Jump to TVB API symbol');
  trigger.innerHTML = `<span>API Symbols</span><kbd>${shortcutLabel}</kbd>`;
  document.body.appendChild(trigger);

  const backdrop = document.createElement('div');
  backdrop.id = 'tvb-api-backdrop';
  backdrop.innerHTML = `
    <div id="tvb-api-modal" role="dialog" aria-modal="true" aria-label="TVB API Symbol Jump">
      <div id="tvb-api-header">
        <span class="tvb-api-kbd">py</span>
        <input id="tvb-api-input" type="search" autocomplete="off" spellcheck="false"
          placeholder="Jump to symbol (e.g. g2do, osc.dfun, class:model, trait:tau)..." />
        <span class="tvb-api-kbd">Esc</span>
      </div>
      <div id="tvb-api-filters">
        <button class="tvb-api-chip active" data-kind="">All</button>
        <button class="tvb-api-chip" data-kind="module">mod:</button>
        <button class="tvb-api-chip" data-kind="class">class:</button>
        <button class="tvb-api-chip" data-kind="method">meth:</button>
        <button class="tvb-api-chip" data-kind="function">fn:</button>
        <button class="tvb-api-chip" data-kind="trait">trait:</button>
      </div>
      <ul id="tvb-api-results" role="listbox"></ul>
      <div id="tvb-api-footer">
        <span id="tvb-api-status">Loading API symbols…</span>
        <span>↑↓ navigate · Enter open · Esc close</span>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const input = document.getElementById('tvb-api-input');
  const resultsEl = document.getElementById('tvb-api-results');
  const statusEl = document.getElementById('tvb-api-status');
  const chips = [...backdrop.querySelectorAll('.tvb-api-chip')];

  let items = null;
  let fuse = null;
  let loadingPromise = null;
  let activeKindChip = '';
  let rendered = [];
  let selectedIdx = 0;

  async function ensureIndex() {
    if (fuse) return;
    if (!loadingPromise) {
      loadingPromise = fetch(symbolsUrl)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((raw) => {
          items = raw.map((entry) => ({
            ...entry,
            acronym: makeAcronym(entry.name),
            lowerName: entry.name.toLowerCase(),
            lowerId: entry.id.toLowerCase(),
          }));
          fuse = new Fuse(items, {
            keys: [
              { name: 'name', weight: 0.45 },
              { name: 'acronym', weight: 0.25 },
              { name: 'id', weight: 0.2 },
              { name: 'summary', weight: 0.1 },
            ],
            threshold: 0.4,
            ignoreLocation: true,
            includeScore: true,
            minMatchCharLength: 2,
          });
          statusEl.textContent = `${items.length} API symbols indexed`;
        })
        .catch((err) => {
          statusEl.textContent = `Failed to load symbol index (${err.message})`;
        });
    }
    await loadingPromise;
  }

  function resolveHref(entry) {
    const clean = entry.url.replace(/^\//, '');
    const [slug, hash] = clean.split('#');
    return `${baseRootUrl}${slug}${hash ? `#${hash}` : ''}`;
  }

  function rankResults(rawQuery) {
    if (!items || !fuse) return [];
    const { kindFilter, query } = parseQuery(rawQuery);
    const activeKind = kindFilter || activeKindChip || null;
    const pool = activeKind ? items.filter((it) => it.kind === activeKind) : items;

    if (!query) {
      return pool
        .slice()
        .sort((a, b) => (b.used_in_count - a.used_in_count) || a.name.localeCompare(b.name))
        .slice(0, 30);
    }

    const q = query.toLowerCase();
    const compactQ = q.replace(/[._\s-]+/g, '');
    const dotIdx = q.lastIndexOf('.');
    const modQ = dotIdx > 0 ? q.slice(0, dotIdx) : '';
    const symQ = dotIdx > 0 ? q.slice(dotIdx + 1) : '';

    // If query contains dot (e.g. `osc.dfun`), match module+member across id as well as Fuse
    const fuseHits = fuse.search(query, { limit: 80 });
    const scored = new Map();
    for (const hit of fuseHits) {
      const item = hit.item;
      if (activeKind && item.kind !== activeKind) continue;
      let score = hit.score ?? 0.5;
      if (item.lowerName === q) score -= 0.6;
      else if (item.lowerName.startsWith(q)) score -= 0.35;
      else if (item.acronym === compactQ || isSubsequence(compactQ, item.acronym)) score -= 0.25;
      if (modQ && symQ && item.module.toLowerCase().includes(modQ) && item.lowerName.includes(symQ)) {
        score -= 0.55;
      } else if (q.includes('.') && isSubsequence(compactQ, item.lowerId.replace(/\./g, ''))) {
        score -= 0.22;
      }
      score -= Math.min(item.used_in_count, 20) * 0.004;
      scored.set(item.id + ':' + item.kind, { item, score });
    }

    // Add fast subsequence/acronym/dotted matches Fuse might rank lower for very short queries
    if (compactQ.length >= 2) {
      for (const item of pool) {
        const key = item.id + ':' + item.kind;
        if (scored.has(key)) continue;
        const dottedHit = modQ && symQ && item.module.toLowerCase().includes(modQ) && item.lowerName.includes(symQ);
        if (
          dottedHit ||
          item.acronym === compactQ ||
          item.acronym.startsWith(compactQ) ||
          (q.includes('.') && isSubsequence(compactQ, item.lowerId.replace(/\./g, '')))
        ) {
          scored.set(key, { item, score: dottedHit ? 0.05 : (item.acronym === compactQ ? 0.02 : 0.18) });
        }
      }
    }

    return [...scored.values()]
      .sort((a, b) => a.score - b.score)
      .slice(0, 35)
      .map((x) => x.item);
  }

  function render() {
    const t0 = performance.now();
    rendered = rankResults(input.value);
    selectedIdx = 0;
    resultsEl.innerHTML = '';

    if (!items) {
      resultsEl.innerHTML = '<li class="tvb-api-empty">Loading API symbols…</li>';
      return;
    }
    if (!rendered.length) {
      resultsEl.innerHTML = '<li class="tvb-api-empty">No matching symbols. Try <code>g2do</code>, <code>class:model</code>, or <code>trait:tau</code>.</li>';
      statusEl.textContent = `0 matches (${(performance.now() - t0).toFixed(1)} ms)`;
      return;
    }

    const frag = document.createDocumentFragment();
    rendered.forEach((item, idx) => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.className = 'tvb-api-row';
      a.href = resolveHref(item);
      a.setAttribute('role', 'option');
      a.setAttribute('aria-selected', idx === 0 ? 'true' : 'false');
      a.addEventListener('click', () => close());

      const badge = KIND_BADGES[item.kind] || item.kind;
      const sig = item.signature ? ` ${item.signature}` : '';
      const used = item.used_in_count > 0 ? ` · ${item.used_in_count} docs` : '';
      a.innerHTML = `
        <div class="tvb-api-row-top">
          <span class="tvb-api-badge">${badge}</span>
          <span class="tvb-api-name"></span>
          <span class="tvb-api-mod"></span>
        </div>
        <div class="tvb-api-sub"></div>
      `;
      a.querySelector('.tvb-api-name').textContent = `${item.name}${sig}`;
      a.querySelector('.tvb-api-mod').textContent = `${item.module}${used}`;
      a.querySelector('.tvb-api-sub').textContent = item.summary || item.id;
      li.appendChild(a);
      frag.appendChild(li);
    });
    resultsEl.appendChild(frag);
    statusEl.textContent = `${rendered.length} shown of ${items.length} symbols (${(performance.now() - t0).toFixed(1)} ms)`;
  }

  function updateSelection(nextIdx) {
    if (!rendered.length) return;
    selectedIdx = (nextIdx + rendered.length) % rendered.length;
    const rows = resultsEl.querySelectorAll('.tvb-api-row');
    rows.forEach((el, idx) => {
      const sel = idx === selectedIdx;
      el.setAttribute('aria-selected', sel ? 'true' : 'false');
      if (sel) el.scrollIntoView({ block: 'nearest' });
    });
  }

  async function open(initialQuery = '') {
    backdrop.classList.add('open');
    if (initialQuery) input.value = initialQuery;
    input.focus();
    input.select();
    await ensureIndex();
    render();
  }

  function close() {
    backdrop.classList.remove('open');
  }

  trigger.addEventListener('click', () => open());
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      activeKindChip = chip.dataset.kind || '';
      chips.forEach((c) => c.classList.toggle('active', c === chip));
      render();
      input.focus();
    });
  });

  input.addEventListener('input', render);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      updateSelection(selectedIdx + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      updateSelection(selectedIdx - 1);
    } else if (e.key === 'Enter' && rendered[selectedIdx]) {
      e.preventDefault();
      const url = resolveHref(rendered[selectedIdx]);
      close();
      window.location.assign(url);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  });

  document.addEventListener('keydown', (e) => {
    const accel = isMac ? e.metaKey : e.ctrlKey;
    if ((accel && e.shiftKey && e.key.toLowerCase() === 'k') || (e.altKey && e.key.toLowerCase() === 'k')) {
      e.preventDefault();
      if (backdrop.classList.contains('open')) close();
      else open();
    } else if (e.key === 'Escape' && backdrop.classList.contains('open')) {
      close();
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPalette, { once: true });
} else {
  initPalette();
}
