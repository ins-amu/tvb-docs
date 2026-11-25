/**
 * Unified fuzzy site search for the TVB documentation.
 *
 * One dialog searches three independently ranked scopes and exposes every kind
 * of result the site ships:
 *
 *   docs      prose chunks (title/heading/content) via MiniSearch 7.2.0
 *   api       API symbols via Fuse 7.5, reusing the matcher features of the
 *             legacy api-search.js palette (acronyms such as `g2do`, dotted
 *             module.member queries such as `osc.dfun`, `kind:` prefixes and
 *             documentation-popularity tie-breaking)
 *   glossary  glossary terms and their definitions via MiniSearch
 *
 * Both fuzzy libraries are vendored next to this module (see ./vendor/, the
 * MiniSearch MIT license ships as minisearch-7.2.0.LICENSE.txt). The build is
 * expected to copy this file, ./vendor/ and a ./site-search-manifest.json plus
 * the three JSON indexes into the same output directory, so every URL below is
 * resolved module-relative and never against the current page path.
 *
 * The pure index helpers are exported so they can be exercised from Node
 * (`node --test tests/test_site_search.mjs`); the DOM wiring only runs when a
 * document exists.
 */

import Fuse from './vendor/fuse.min.mjs';
import MiniSearch from './vendor/minisearch-7.2.0.esm.js';

/* ------------------------------------------------------------------ */
/* Shared vocabulary                                                    */
/* ------------------------------------------------------------------ */

/** Every API symbol kind the index ships, in display order. */
export const API_KINDS = ['module', 'class', 'method', 'function', 'trait', 'attribute'];

/** Legacy `prefix:` query aliases, kept from the old API palette. */
export const API_KIND_ALIASES = {
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

export const API_KIND_BADGES = {
  module: 'mod',
  class: 'cls',
  method: 'meth',
  function: 'fn',
  trait: 'trait',
  attribute: 'attr',
};

/** Search scopes: the `all` scope queries all three indexes. */
export const SCOPES = ['all', 'docs', 'api', 'glossary'];

export const SCOPE_LABELS = {
  all: 'All',
  docs: 'Docs',
  api: 'API',
  glossary: 'Glossary',
};

/** Which lazy index each scope needs; the API scope never fetches prose. */
export const SCOPE_SOURCES = {
  all: ['api', 'docs', 'glossary'],
  docs: ['docs'],
  api: ['api'],
  glossary: ['glossary'],
};

export const MANIFEST_PATH = './site-search-manifest.json';

/** Collapsed/expanded result counts per group. */
export const COLLAPSED_LIMIT = 5;
export const EXPANDED_LIMIT = 50;

/* ------------------------------------------------------------------ */
/* Pure helpers                                                         */
/* ------------------------------------------------------------------ */

/** Initials of a symbol name, so `Generic2dOscillator` is reachable as `g2do`. */
export function makeAcronym(name) {
  const short = String(name || '').split('.').pop() || '';
  const parts = short.match(/[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|[0-9]+/g) || [];
  return parts.map((part) => part[0]).join('').toLowerCase();
}

export function isSubsequence(needle, haystack) {
  let i = 0;
  for (let j = 0; j < haystack.length && i < needle.length; j++) {
    if (haystack[j] === needle[i]) i++;
  }
  return i === needle.length;
}

/**
 * Split a raw query into an API kind filter (`class:model`, `fn:foo`) and the
 * remaining text. Tokens with an unknown prefix are ordinary search terms, so
 * `http://host` or `note:abc` survive untouched.
 */
export function parseQuery(raw) {
  const tokens = String(raw || '').trim().split(/\s+/).filter(Boolean);
  let kindFilter = null;
  const terms = [];
  for (const token of tokens) {
    const colon = token.indexOf(':');
    if (colon > 0) {
      const prefix = token.slice(0, colon).toLowerCase();
      if (Object.hasOwn(API_KIND_ALIASES, prefix)) {
        kindFilter = API_KIND_ALIASES[prefix];
        const rest = token.slice(colon + 1);
        if (rest) terms.push(rest);
        continue;
      }
    }
    terms.push(token);
  }
  return { kindFilter, query: terms.join(' ') };
}

/**
 * Resolve a site-root-relative record URL (`/quickstart-guide#intro`, `/`)
 * against the directory the module was served from, so a deployment subpath is
 * preserved. Absolute URLs are returned untouched.
 */
export function resolveRecordUrl(recordUrl, moduleUrl) {
  const value = String(recordUrl || '');
  if (!value) return '';
  if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith('//')) return value;
  const moduleDir = new URL('.', moduleUrl);
  return new URL(value.replace(/^\/+/, ''), moduleDir).href;
}

/** Keep the first item for each href and drop items without a link. */
export function uniqueByHref(items, toHref) {
  const seen = new Set();
  const kept = [];
  for (const item of items) {
    const href = toHref ? toHref(item) : item.href;
    if (!href || seen.has(href)) continue;
    seen.add(href);
    kept.push(item);
  }
  return kept;
}

export function normalizeManifest(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const sections = Array.isArray(source.sections)
    ? source.sections
        .filter((section) => section && section.id)
        .map((section) => ({ id: String(section.id), label: String(section.label || section.id) }))
    : [];
  return {
    sections,
    api: typeof source.api === 'string' ? source.api : 'api-symbols.json',
    docs: typeof source.docs === 'string' ? source.docs : 'search-docs.json',
    glossary: typeof source.glossary === 'string' ? source.glossary : 'search-glossary.json',
  };
}

/* ------------------------------------------------------------------ */
/* API symbol search (Fuse)                                             */
/* ------------------------------------------------------------------ */

/** Enough candidates from the selected kind to survive re-scoring. */
const API_CANDIDATE_LIMIT = 200;

const API_FUSE_OPTIONS = {
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
};

/**
 * Build the API symbol searcher.
 *
 * One Fuse index is built per symbol kind. The legacy palette searched a single
 * index with `limit: 80` and then discarded other kinds, so a kind filter could
 * return fewer hits than requested (or none) because the cutoff happened
 * *before* the filter. Searching the per-kind index applies the filter before
 * any cutoff.
 */
export function createApiSearch(rawEntries) {
  if (!Array.isArray(rawEntries)) throw new TypeError('API index must be an array');
  const entries = rawEntries.map((entry) => {
    const name = String(entry.name ?? '');
    const id = String(entry.id ?? '');
    const module = String(entry.module ?? '');
    return {
      ...entry,
      name,
      id,
      module,
      kind: String(entry.kind ?? ''),
      used_in_count: Number(entry.used_in_count) || 0,
      acronym: makeAcronym(name),
      lowerName: name.toLowerCase(),
      lowerId: id.toLowerCase(),
      lowerModule: module.toLowerCase(),
    };
  });

  const pools = new Map();
  for (const entry of entries) {
    if (!pools.has(entry.kind)) pools.set(entry.kind, []);
    pools.get(entry.kind).push(entry);
  }

  const fuseIndexes = new Map();
  function fuseFor(kind) {
    const key = kind || '';
    let fuse = fuseIndexes.get(key);
    if (!fuse) {
      const pool = kind ? (pools.get(kind) || []) : entries;
      fuse = new Fuse(pool, API_FUSE_OPTIONS);
      fuseIndexes.set(key, fuse);
    }
    return fuse;
  }

  function poolFor(kind) {
    return kind ? (pools.get(kind) || []) : entries;
  }

  function popularityFirst(a, b) {
    return (b.used_in_count - a.used_in_count) || a.name.localeCompare(b.name);
  }

  /**
   * @returns {{items: object[], total: number}} items capped to `limit`.
   */
  function search({ query = '', kind = '', limit = 35 } = {}) {
    const pool = poolFor(kind);
    if (!pool || !pool.length) return { items: [], total: 0 };
    const queryText = String(query || '').trim().toLowerCase();
    if (!queryText) {
      const popular = pool.slice().sort(popularityFirst);
      return { items: popular.slice(0, limit), total: popular.length };
    }

    const compactQuery = queryText.replace(/[._\s-]+/g, '');
    const dotIndex = queryText.lastIndexOf('.');
    const moduleQuery = dotIndex > 0 ? queryText.slice(0, dotIndex) : '';
    const memberQuery = dotIndex > 0 ? queryText.slice(dotIndex + 1) : '';

    const hits = fuseFor(kind).search(queryText, {
      limit: Math.min(pool.length, API_CANDIDATE_LIMIT),
    });
    const scored = new Map();
    for (const hit of hits) {
      const item = hit.item;
      let score = hit.score ?? 0.5;
      if (item.lowerName === queryText) score -= 0.6;
      else if (item.lowerName.startsWith(queryText)) score -= 0.35;
      else if (item.acronym === compactQuery || isSubsequence(compactQuery, item.acronym)) score -= 0.25;
      if (moduleQuery && memberQuery && item.lowerModule.includes(moduleQuery) && item.lowerName.includes(memberQuery)) {
        score -= 0.55;
      } else if (queryText.includes('.') && isSubsequence(compactQuery, item.lowerId.replace(/\./g, ''))) {
        score -= 0.22;
      }
      score -= Math.min(item.used_in_count, 20) * 0.004;
      scored.set(`${item.id}:${item.kind}`, { item, score });
    }

    // Acronym / dotted / subsequence matches that Fuse ranks too low for short
    // queries (e.g. `g2do`), plus the module.member `osc.dfun` shortcut.
    if (compactQuery.length >= 2) {
      for (const item of pool) {
        const key = `${item.id}:${item.kind}`;
        if (scored.has(key)) continue;
        const dottedHit = moduleQuery && memberQuery
          && item.lowerModule.includes(moduleQuery)
          && item.lowerName.includes(memberQuery);
        if (
          dottedHit
          || item.acronym === compactQuery
          || item.acronym.startsWith(compactQuery)
          || (queryText.includes('.') && isSubsequence(compactQuery, item.lowerId.replace(/\./g, '')))
        ) {
          scored.set(key, { item, score: dottedHit ? 0.05 : (item.acronym === compactQuery ? 0.02 : 0.18) });
        }
      }
    }

    // A qualified query like osc.dfun should put exact members ahead of
    // lookalikes such as osc.dfun_intermediates, even with a weaker Fuse score.
    const exactMember = (item) => Boolean(moduleQuery && memberQuery
      && item.lowerModule.includes(moduleQuery) && item.lowerId.endsWith(`.${memberQuery}`));
    const ranked = [...scored.values()]
      .sort((a, b) => Number(exactMember(b.item)) - Number(exactMember(a.item)) || a.score - b.score)
      .map((entry) => entry.item);
    return { items: ranked.slice(0, limit), total: ranked.length };
  }

  return { size: entries.length, search };
}

/* ------------------------------------------------------------------ */
/* Prose search (MiniSearch)                                            */
/* ------------------------------------------------------------------ */

/**
 * MiniSearch configuration shared by the docs and glossary indexes:
 * prefix matching on every token (so search-as-you-type finds partial words),
 * light fuzzy matching for typos, and all query terms required.
 */
function miniSearchOptions({ fields, storeFields, boost }) {
  return {
    fields,
    storeFields,
    searchOptions: {
      boost,
      prefix: (term) => term.length >= 2,
      fuzzy: 0.2,
      combineWith: 'AND',
    },
  };
}

/**
 * Documentation prose index. Every record carries a `section` from the
 * manifest, exposed as the Docs section filter.
 *
 * MiniSearch returns every matching document and only then hands the list to
 * the caller, and its `filter` option runs on that full list, so the section
 * filter is applied before our `limit` slice.
 */
export function createDocsSearch(records) {
  if (!Array.isArray(records)) throw new TypeError('Docs index must be an array');
  const documents = records.map((record, position) => ({
    id: String(position),
    url: String(record.url ?? ''),
    title: String(record.title ?? ''),
    heading: String(record.heading ?? ''),
    content: String(record.content ?? ''),
    section: String(record.section ?? ''),
  }));
  const index = new MiniSearch({
    idField: 'id',
    ...miniSearchOptions({
      fields: ['title', 'heading', 'content'],
      storeFields: ['url', 'title', 'heading', 'content', 'section'],
      boost: { title: 4, heading: 2 },
    }),
  });
  index.addAll(documents);

  function search({ query = '', section = '', limit = 30, excludeUrls } = {}) {
    const queryText = String(query || '').trim();
    if (!queryText) return { items: [], total: 0 };
    const options = section || excludeUrls?.size ? { filter: (result) =>
      (!section || result.section === section) && !excludeUrls?.has(result.url),
    } : {};
    const hits = uniqueByHref(index.search(queryText, options), (item) => item.url);
    return { items: hits.slice(0, limit), total: hits.length };
  }

  return { size: documents.length, search };
}

/** Glossary index: the term (title) and its definition (content) are searched. */
export function createGlossarySearch(records) {
  if (!Array.isArray(records)) throw new TypeError('Glossary index must be an array');
  const documents = records.map((record, position) => ({
    id: String(position),
    url: String(record.url ?? ''),
    title: String(record.title ?? ''),
    content: String(record.content ?? ''),
  }));
  const index = new MiniSearch({
    idField: 'id',
    ...miniSearchOptions({
      fields: ['title', 'content'],
      storeFields: ['url', 'title', 'content'],
      boost: { title: 3 },
    }),
  });
  index.addAll(documents);

  function search({ query = '', limit = 30 } = {}) {
    const queryText = String(query || '').trim();
    if (!queryText) return { items: [], total: 0 };
    const hits = index.search(queryText);
    return { items: hits.slice(0, limit), total: hits.length };
  }

  return { size: documents.length, search };
}

/* ------------------------------------------------------------------ */
/* Browser UI                                                          */
/* ------------------------------------------------------------------ */

const TRIGGER_ID = 'tvb-search-trigger';
const BACKDROP_ID = 'tvb-search-backdrop';
const DIALOG_ID = 'tvb-search-dialog';
const INPUT_ID = 'tvb-search-input';
const RESULTS_ID = 'tvb-search-results';
const MESSAGE_ID = 'tvb-search-message';
const STATUS_ID = 'tvb-search-status';
const SECTION_ID = 'tvb-search-section';
const STYLE_ID = 'tvb-search-styles';
const GLOBAL_KEY = '__tvbSiteSearch';

const STYLES = `
  .tvb-search-sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
  #${TRIGGER_ID} {
    position: fixed;
    right: 1.15rem;
    bottom: 1.15rem;
    z-index: 9990;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.5rem 0.85rem;
    border-radius: 9999px;
    border: 1px solid var(--myst-color-accent-surface-border, #cbd5e1);
    background: var(--myst-color-surface-header, #ffffff);
    color: var(--myst-color-text, #1c1e21);
    font: 500 13px/1.2 "Inter", system-ui, sans-serif;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
    cursor: pointer;
    transition: transform 0.12s ease, border-color 0.12s ease;
  }
  #${TRIGGER_ID}:hover {
    border-color: var(--myst-color-primary, #1e40af);
    transform: translateY(-1px);
  }
  #${TRIGGER_ID}:focus-visible {
    outline: 2px solid var(--myst-color-primary, #1e40af);
    outline-offset: 2px;
  }
  #${TRIGGER_ID} svg {
    width: 14px;
    height: 14px;
    flex: none;
  }
  #${TRIGGER_ID} kbd, .tvb-search-kbd {
    font: 500 11px/1 "JetBrains Mono", ui-monospace, monospace;
    padding: 0.15rem 0.35rem;
    border-radius: 4px;
    background: var(--myst-color-bg-secondary, #e9e7e1);
    color: var(--myst-color-text-secondary, #4b5563);
    border: 1px solid rgba(128, 128, 128, 0.25);
  }
  #${BACKDROP_ID} {
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
  #${BACKDROP_ID}.open { display: flex; }
  #${DIALOG_ID} {
    width: min(760px, 100%);
    max-height: 78vh;
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
  #tvb-search-input-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 0.9rem;
    border-bottom: 1px solid var(--myst-color-bg-secondary, #e5e7eb);
  }
  #${INPUT_ID} {
    flex: 1;
    border: 0;
    outline: none;
    background: transparent;
    color: inherit;
    font: 400 15px/1.4 "Inter", system-ui, sans-serif;
  }
  #tvb-search-filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.45rem 0.9rem;
    padding: 0.45rem 0.9rem;
    border-bottom: 1px solid var(--myst-color-bg-secondary, #e5e7e1);
    background: var(--myst-color-surface, #efece6);
    font-size: 12px;
  }
  .tvb-search-filter {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
  }
  .tvb-search-filter[hidden] { display: none; }
  .tvb-search-filter-label {
    color: var(--myst-color-text-secondary, #6b7280);
    font-weight: 500;
  }
  .tvb-search-chip {
    padding: 0.18rem 0.55rem;
    border-radius: 9999px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--myst-color-text-secondary, #4b5563);
    cursor: pointer;
    font: 500 12px/1.3 inherit;
  }
  .tvb-search-chip[aria-pressed="true"] {
    background: var(--myst-color-active-surface, #eef2ff);
    color: var(--myst-color-active, #1e40af);
    border-color: var(--myst-color-accent-surface-border, #c7d2fe);
  }
  .tvb-search-chip:focus-visible {
    outline: 2px solid var(--myst-color-primary, #1e40af);
    outline-offset: 1px;
  }
  #${SECTION_ID} {
    max-width: 12rem;
    padding: 0.15rem 0.3rem;
    border-radius: 6px;
    border: 1px solid var(--myst-color-accent-surface-border, #cbd5e1);
    background: var(--myst-color-surface-header, #ffffff);
    color: inherit;
    font: 400 12px/1.3 inherit;
  }
  #${RESULTS_ID} {
    overflow-y: auto;
    flex: 1;
    padding: 0.35rem;
  }
  .tvb-search-group + .tvb-search-group { margin-top: 0.15rem; }
  .tvb-search-group-head {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.7rem 0.15rem;
    font: 600 10.5px/1.3 "Inter", system-ui, sans-serif;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--myst-color-text-secondary, #6b7280);
  }
  .tvb-search-row {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.5rem 0.7rem;
    border-radius: 8px;
    cursor: pointer;
    text-decoration: none;
    color: inherit;
  }
  .tvb-search-row[aria-selected="true"], .tvb-search-row:hover {
    background: var(--myst-color-active-surface, #eef2ff);
  }
  .tvb-search-row-top {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
  }
  .tvb-search-badge {
    flex-shrink: 0;
    font: 600 10.5px/1.1 "JetBrains Mono", ui-monospace, monospace;
    padding: 0.18rem 0.4rem;
    border-radius: 4px;
    text-transform: uppercase;
    background: var(--myst-color-bg-secondary, #e5e7eb);
    color: var(--myst-color-primary, #1e40af);
  }
  .tvb-search-title {
    font: 600 13.5px/1.3 "Inter", system-ui, sans-serif;
    color: var(--myst-color-text, #1c1e21);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tvb-search-row-api .tvb-search-title {
    font-family: "JetBrains Mono", ui-monospace, monospace;
  }
  .tvb-search-trail {
    margin-left: auto;
    font: 400 11.5px/1.2 "JetBrains Mono", ui-monospace, monospace;
    color: var(--myst-color-text-secondary, #6b7280);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tvb-search-sub {
    font-size: 12px;
    color: var(--myst-color-text-secondary, #4b5563);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tvb-search-more {
    display: block;
    width: 100%;
    padding: 0.4rem 0.7rem;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--myst-color-active, #1e40af);
    font: 500 12px/1.3 "Inter", system-ui, sans-serif;
    text-align: left;
    cursor: pointer;
    text-decoration: none;
  }
  .tvb-search-more[aria-selected="true"], .tvb-search-more:hover {
    background: var(--myst-color-active-surface, #eef2ff);
  }
  #${MESSAGE_ID} {
    padding: 1rem;
    text-align: center;
    color: var(--myst-color-text-secondary, #6b7280);
    font-size: 12.5px;
  }
  #${MESSAGE_ID}[hidden] { display: none; }
  .tvb-search-note {
    display: block;
    margin-top: 0.35rem;
  }
  #tvb-search-footer {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: center;
    padding: 0.45rem 0.9rem;
    font-size: 11.5px;
    color: var(--myst-color-text-secondary, #6b7280);
    border-top: 1px solid var(--myst-color-bg-secondary, #e5e7eb);
    background: var(--myst-color-surface, #efece6);
  }
  .tvb-search-hint { white-space: nowrap; }
  @media (max-width: 640px) {
    #${BACKDROP_ID} { padding: 5vh 0.5rem 1rem; }
    #${DIALOG_ID} { max-height: 88vh; }
    .tvb-search-hint { display: none; }
  }
  @media (prefers-reduced-motion: reduce) {
    #${TRIGGER_ID} { transition: none; }
  }
`;

/**
 * Wire the palette into the live document. Runs once per page load and guards
 * itself with a window-level sentinel so a second copy of the module cannot add
 * a duplicate trigger or dialog.
 */
function startUi() {
  if (typeof document === 'undefined') return;
  if (window[GLOBAL_KEY]) return;

  const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent || '');
  const primaryShortcut = isMac ? '⌘K' : 'Ctrl K';

  /* ---------------- elements ---------------- */

  const trigger = document.createElement('button');
  trigger.id = TRIGGER_ID;
  trigger.type = 'button';
  trigger.setAttribute('aria-label', `Search documentation (${isMac ? 'Command K' : 'Control K'})`);
  trigger.setAttribute('aria-keyshortcuts', 'Control+K Meta+K');
  trigger.innerHTML = `
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" stroke-width="1.8"></circle>
      <path d="M12.8 12.8L17 17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></path>
    </svg>
    <span>Search</span>
    <kbd>${primaryShortcut}</kbd>
  `;

  const backdrop = document.createElement('div');
  backdrop.id = BACKDROP_ID;
  backdrop.innerHTML = `
    <div id="${DIALOG_ID}" role="dialog" aria-modal="true" aria-labelledby="tvb-search-title">
      <h2 id="tvb-search-title" class="tvb-search-sr-only">Search TVB documentation</h2>
      <div id="tvb-search-input-row">
        <label class="tvb-search-sr-only" for="${INPUT_ID}">Search all documentation, API symbols and glossary</label>
        <input id="${INPUT_ID}" type="search" role="combobox" aria-autocomplete="list"
          aria-expanded="true" aria-controls="${RESULTS_ID}" autocomplete="off" spellcheck="false"
          placeholder="Search docs, API and glossary (e.g. g2do, osc.dfun, class:model)" />
        <kbd class="tvb-search-kbd" aria-hidden="true">Esc</kbd>
      </div>
      <div id="tvb-search-filters">
        <div class="tvb-search-filter" id="tvb-search-scope-filter" role="group" aria-label="Search scope"></div>
        <div class="tvb-search-filter" id="tvb-search-docs-filter">
          <label class="tvb-search-filter-label" for="${SECTION_ID}">Section</label>
          <select id="${SECTION_ID}"><option value="">All sections</option></select>
        </div>
        <div class="tvb-search-filter" id="tvb-search-kind-filter" role="group" aria-label="API symbol kind"></div>
      </div>
      <div id="${RESULTS_ID}" role="listbox" aria-label="Search results"></div>
      <div id="${MESSAGE_ID}" role="status"></div>
      <div id="tvb-search-footer">
        <span id="${STATUS_ID}"></span>
        <span class="tvb-search-hint">↑↓ navigate · Enter open · Esc close</span>
      </div>
    </div>
  `;

  const input = backdrop.querySelector(`#${INPUT_ID}`);
  const resultsEl = backdrop.querySelector(`#${RESULTS_ID}`);
  const messageEl = backdrop.querySelector(`#${MESSAGE_ID}`);
  const statusEl = backdrop.querySelector(`#${STATUS_ID}`);
  const scopeFilter = backdrop.querySelector('#tvb-search-scope-filter');
  const docsFilter = backdrop.querySelector('#tvb-search-docs-filter');
  const kindFilter = backdrop.querySelector('#tvb-search-kind-filter');
  const sectionSelect = backdrop.querySelector(`#${SECTION_ID}`);

  /* ---------------- state ---------------- */

  const state = {
    scope: 'all',
    docsSection: '',
    apiKind: '',
    expanded: new Set(),
  };

  const manifestState = { status: 'idle', value: null, error: '' };
  const indexStates = {
    api: { status: 'idle', error: '' },
    docs: { status: 'idle', error: '' },
    glossary: { status: 'idle', error: '' },
  };
  const searches = { api: null, docs: null, glossary: null };
  const indexPromises = { api: null, docs: null, glossary: null };
  let manifestPromise = null;
  let options = [];
  let activeIndex = 0;
  let lastFocused = null;
  let sectionsSignature = '';

  /* ---------------- chips ---------------- */

  const scopeChips = SCOPES.map((scope) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'tvb-search-chip';
    chip.dataset.scope = scope;
    chip.textContent = SCOPE_LABELS[scope];
    chip.setAttribute('aria-pressed', String(scope === state.scope));
    chip.addEventListener('click', () => {
      setScope(scope);
      input.focus();
    });
    scopeFilter.appendChild(chip);
    return chip;
  });

  const kindChips = [['', 'All kinds'], ...API_KINDS.map((kind) => [kind, `${API_KIND_BADGES[kind]}:`])]
    .map(([kind, label]) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'tvb-search-chip';
      chip.dataset.kind = kind;
      chip.textContent = label;
      chip.setAttribute('aria-pressed', String(kind === state.apiKind));
      chip.addEventListener('click', () => {
        const parsed = parseQuery(input.value);
        if (parsed.kindFilter) input.value = parsed.query;
        state.apiKind = kind;
        render();
        input.focus();
      });
      kindFilter.appendChild(chip);
      return chip;
    });

  sectionSelect.addEventListener('change', () => {
    state.docsSection = sectionSelect.value;
    render();
    input.focus();
  });

  /* ---------------- data loading ---------------- */

  function fetchJson(relativePath) {
    const url = new URL(relativePath, import.meta.url).href;
    return fetch(url).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status} for ${relativePath}`);
      return response.json();
    });
  }

  function loadManifest() {
    if (manifestState.status === 'ready') return Promise.resolve(manifestState.value);
    if (manifestPromise) return manifestPromise;
    manifestState.status = 'loading';
    manifestState.error = '';
    manifestPromise = fetchJson(MANIFEST_PATH)
      .then((raw) => {
        manifestState.status = 'ready';
        manifestState.value = normalizeManifest(raw);
        return manifestState.value;
      })
      .catch((error) => {
        manifestState.status = 'error';
        manifestState.error = error?.message || String(error);
        manifestPromise = null;
        throw error;
      })
      .finally(() => render());
    return manifestPromise;
  }

  function buildSearch(name, raw) {
    if (!Array.isArray(raw)) throw new TypeError(`${name} index is not an array`);
    if (name === 'api') return createApiSearch(raw);
    if (name === 'docs') return createDocsSearch(raw);
    return createGlossarySearch(raw);
  }

  function loadIndex(name) {
    if (indexStates[name].status === 'ready') return Promise.resolve(searches[name]);
    if (indexPromises[name]) return indexPromises[name];
    indexStates[name].status = 'loading';
    indexStates[name].error = '';
    indexPromises[name] = loadManifest()
      .then((manifest) => fetchJson(manifest[name]))
      .then((raw) => {
        searches[name] = buildSearch(name, raw);
        indexStates[name].status = 'ready';
        return searches[name];
      })
      .catch((error) => {
        indexStates[name].status = 'error';
        indexStates[name].error = error?.message || String(error);
        indexPromises[name] = null;
        throw error;
      })
      .finally(() => render());
    return indexPromises[name];
  }

  function ensureSources() {
    loadManifest().catch(() => {});
    for (const name of SCOPE_SOURCES[state.scope] || []) {
      loadIndex(name).catch(() => {});
    }
  }

  function retry() {
    if (manifestState.status === 'error') {
      manifestState.status = 'idle';
    }
    for (const name of SCOPE_SOURCES[state.scope] || []) {
      if (indexStates[name].status === 'error') {
        indexStates[name].status = 'idle';
        indexPromises[name] = null;
      }
    }
    render();
    ensureSources();
  }

  /* ---------------- scopes and filters ---------------- */

  function setScope(scope) {
    if (!SCOPES.includes(scope)) return;
    state.scope = scope;
    for (const chip of scopeChips) {
      chip.setAttribute('aria-pressed', String(chip.dataset.scope === scope));
    }
    const showDocs = scope === 'all' || scope === 'docs';
    const showApi = scope === 'all' || scope === 'api';
    docsFilter.hidden = !showDocs;
    kindFilter.hidden = !showApi;
    ensureSources();
    render();
  }

  function syncSectionOptions() {
    const sections = manifestState.value?.sections || [];
    const signature = sections.map((section) => `${section.id}\u0000${section.label}`).join('\u0001');
    if (signature === sectionsSignature) return;
    sectionsSignature = signature;
    const current = state.docsSection;
    sectionSelect.replaceChildren();
    const all = document.createElement('option');
    all.value = '';
    all.textContent = 'All sections';
    sectionSelect.appendChild(all);
    for (const section of sections) {
      const option = document.createElement('option');
      option.value = section.id;
      option.textContent = section.label;
      sectionSelect.appendChild(option);
    }
    if (current && !sections.some((section) => section.id === current)) {
      state.docsSection = '';
    }
    sectionSelect.value = state.docsSection;
  }

  /* ---------------- rendering ---------------- */

  function truncate(text, max) {
    const value = String(text || '').replace(/\s+/g, ' ').trim();
    return value.length > max ? `${value.slice(0, max - 1)}…` : value;
  }

  function groupsForScope() {
    const groups = [];
    if (state.scope === 'all' || state.scope === 'docs') groups.push({ id: 'docs', label: 'Docs' });
    if (state.scope === 'all' || state.scope === 'api') groups.push({ id: 'api', label: 'API' });
    if (state.scope === 'all' || state.scope === 'glossary') groups.push({ id: 'glossary', label: 'Glossary' });
    return groups;
  }

  function searchGroup(id, query, limit, apiKind, excludeUrls) {
    const indexState = indexStates[id];
    if (indexState.status === 'error') return { status: 'error', error: indexState.error };
    const search = searches[id];
    if (indexState.status !== 'ready' || !search) {
      if (manifestState.status === 'error') return { status: 'error', error: manifestState.error };
      return { status: 'loading' };
    }
    try {
      if (id === 'api') return { status: 'ready', ...search.search({ query, kind: apiKind, limit }) };
      if (id === 'docs') return { status: 'ready', ...search.search({ query, section: state.docsSection, limit, excludeUrls }) };
      return { status: 'ready', ...search.search({ query, limit }) };
    } catch (error) {
      return { status: 'error', error: error?.message || String(error) };
    }
  }

  function sectionLabel(sectionId) {
    const sections = manifestState.value?.sections || [];
    return sections.find((section) => section.id === sectionId)?.label || '';
  }

  function addRow(container, groupId, item, href, optionList) {
    const anchor = document.createElement('a');
    anchor.className = `tvb-search-row tvb-search-row-${groupId}`;
    anchor.href = href;
    anchor.id = `tvb-search-opt-${optionList.length}`;
    anchor.setAttribute('role', 'option');
    anchor.setAttribute('aria-selected', 'false');
    anchor.tabIndex = -1;
    anchor.addEventListener('click', (event) => {
      if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) close();
    });

    const top = document.createElement('div');
    top.className = 'tvb-search-row-top';
    const title = document.createElement('span');
    title.className = 'tvb-search-title';
    const trail = document.createElement('span');
    trail.className = 'tvb-search-trail';
    const sub = document.createElement('div');
    sub.className = 'tvb-search-sub';

    if (groupId === 'api') {
      const badge = document.createElement('span');
      badge.className = 'tvb-search-badge';
      badge.textContent = API_KIND_BADGES[item.kind] || item.kind;
      top.appendChild(badge);
      title.textContent = `${item.name}${item.signature ? ` ${item.signature}` : ''}`;
      trail.textContent = `${item.module}${item.used_in_count ? ` · ${item.used_in_count} docs` : ''}`;
      sub.textContent = truncate(item.summary || item.id, 160);
    } else if (groupId === 'docs') {
      title.textContent = item.heading || item.title || item.url;
      const label = sectionLabel(item.section);
      if (label) {
        const badge = document.createElement('span');
        badge.className = 'tvb-search-badge';
        badge.textContent = label;
        top.appendChild(badge);
      }
      if (item.title && item.title !== title.textContent) trail.textContent = item.title;
      sub.textContent = truncate(item.content, 160);
    } else {
      title.textContent = item.title || item.url;
      sub.textContent = truncate(item.content, 160);
    }

    top.prepend(title);
    top.appendChild(trail);
    anchor.append(top, sub);
    container.appendChild(anchor);
    optionList.push({ element: anchor, action: 'open' });
  }

  function addMoreRow(container, groupId, label, expanded, optionList) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tvb-search-more';
    button.id = `tvb-search-opt-${optionList.length}`;
    button.setAttribute('role', 'option');
    button.setAttribute('aria-selected', 'false');
    button.tabIndex = -1;
    button.textContent = label;
    button.addEventListener('click', () => {
      toggleExpanded(groupId, !expanded);
    });
    container.appendChild(button);
    optionList.push({ element: button, action: 'toggle', groupId, expanded });
  }

  function setMessage(lines) {
    messageEl.hidden = !lines.length;
    messageEl.replaceChildren();
    for (const line of lines) {
      const span = document.createElement('span');
      span.className = 'tvb-search-note';
      span.textContent = line;
      messageEl.appendChild(span);
    }
  }

  function toggleExpanded(groupId, expanded) {
    if (expanded) state.expanded.add(groupId);
    else state.expanded.delete(groupId);
    render();
  }

  function render() {
    syncSectionOptions();

    const { kindFilter, query } = parseQuery(input.value);
    const apiKind = kindFilter || state.apiKind || '';
    for (const chip of kindChips) chip.setAttribute('aria-pressed', String(chip.dataset.kind === apiKind));
    const groups = groupsForScope();
    const singleGroup = groups.length === 1;
    const limitFor = (id) => singleGroup || state.expanded.has(id) ? EXPANDED_LIMIT : COLLAPSED_LIMIT;
    // In All, an API symbol is a better label for the same destination than
    // the generated page heading. Docs alone keeps all of its destinations.
    const apiResult = state.scope === 'all' ? searchGroup('api', query, limitFor('api'), apiKind) : null;
    const apiUrls = new Set(query ? apiResult?.items?.map((item) => item.url) ?? [] : []);
    const nextOptions = [];
    const notes = [];
    const parts = [];
    const rendered = [];
    let totalMatches = 0;
    let anyReady = false;

    for (const group of groups) {
      const limit = limitFor(group.id);
      const result = (group.id === 'api' && apiResult) || searchGroup(group.id, query, limit, apiKind, apiUrls);
      if (result.status === 'loading') {
        notes.push(`Loading the ${group.label.toLowerCase()} index…`);
        continue;
      }
      if (result.status === 'error') {
        notes.push(`Could not load the ${group.label.toLowerCase()} index: ${result.error}`);
        continue;
      }
      anyReady = true;
      const total = result.total || 0;
      totalMatches += total;
      const toHref = (item) => resolveRecordUrl(item.url, import.meta.url);
      const items = uniqueByHref(result.items || [], toHref);
      if (!items.length) continue;

      const section = document.createElement('div');
      section.className = 'tvb-search-group';
      section.setAttribute('role', 'group');
      section.setAttribute('aria-label', `${group.label} — ${total} match${total === 1 ? '' : 'es'}`);
      const head = document.createElement('div');
      head.className = 'tvb-search-group-head';
      head.setAttribute('aria-hidden', 'true');
      head.textContent = `${group.label} · ${items.length < total ? `${items.length} of ` : ''}${total}`;
      section.appendChild(head);

      for (const item of items) addRow(section, group.id, item, toHref(item), nextOptions);

      if (!singleGroup && total > COLLAPSED_LIMIT) {
        const expanded = state.expanded.has(group.id);
        const label = expanded ? `Show fewer ${group.label.toLowerCase()} matches`
          : `Show ${Math.min(total, EXPANDED_LIMIT)} ${group.label.toLowerCase()} matches`;
        addMoreRow(section, group.id, label, expanded, nextOptions);
      }

      rendered.push(section);
      parts.push(`${group.label} ${total}`);
    }

    resultsEl.replaceChildren();
    for (const section of rendered) resultsEl.appendChild(section);

    const uniqueNotes = [...new Set(notes)];
    if (!query.trim() && !totalMatches) {
      // An empty API scope shows popular symbols, so only claim "no matches"
      // for the prose scopes.
      setMessage(uniqueNotes.length ? uniqueNotes : [
        state.scope === 'api' ? 'Type to jump to a symbol.' : 'Type to search the documentation.',
      ]);
    } else if (!totalMatches) {
      setMessage(uniqueNotes.length ? uniqueNotes : ['No matches. Try fewer or different words.']);
    } else {
      setMessage(uniqueNotes);
    }

    if (notes.some((note) => note.startsWith('Could not load'))) {
      const retryButton = document.createElement('button');
      retryButton.type = 'button';
      retryButton.className = 'tvb-search-chip';
      retryButton.textContent = 'Retry';
      retryButton.addEventListener('click', retry);
      const line = document.createElement('span');
      line.className = 'tvb-search-note';
      line.appendChild(retryButton);
      messageEl.appendChild(line);
    }

    options = nextOptions;
    activeIndex = 0;
    paintActiveOption();

    const apiInScope = state.scope === 'all' || state.scope === 'api';
    const kindNote = apiInScope && kindFilter && kindFilter !== state.apiKind ? ` · kind: ${kindFilter}` : '';
    if (!anyReady && !notes.length) {
      statusEl.textContent = 'Loading search index…';
    } else if (!query.trim() && totalMatches) {
      statusEl.textContent = `${totalMatches} API symbol${totalMatches === 1 ? '' : 's'} — type to search docs and glossary`;
    } else if (!totalMatches) {
      statusEl.textContent = '';
    } else {
      statusEl.textContent = `${totalMatches} match${totalMatches === 1 ? '' : 'es'} · ${parts.join(' · ')}${kindNote}`;
    }
  }

  function paintActiveOption() {
    options.forEach((option, position) => {
      option.element.setAttribute('aria-selected', String(position === activeIndex));
    });
    const active = options[activeIndex];
    if (active) {
      input.setAttribute('aria-activedescendant', active.element.id);
      active.element.scrollIntoView({ block: 'nearest' });
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function moveActive(step) {
    if (!options.length) return;
    activeIndex = (activeIndex + step + options.length) % options.length;
    paintActiveOption();
  }

  function activateOption(index) {
    const option = options[index];
    if (!option) return;
    if (option.action === 'toggle') {
      toggleExpanded(option.groupId, !option.expanded);
      return;
    }
    option.element.click();
  }

  /* ---------------- open / close ---------------- */

  function isOpen() {
    return backdrop.classList.contains('open');
  }

  function open(scope = null) {
    if (scope) setScope(scope);
    if (!isOpen()) lastFocused = document.activeElement;
    backdrop.classList.add('open');
    ensureSources();
    render();
    input.focus();
    input.select();
  }

  function close() {
    if (!isOpen()) return;
    backdrop.classList.remove('open');
    const restoreTo = lastFocused;
    lastFocused = null;
    const restorable = restoreTo
      && restoreTo !== document.body
      && typeof restoreTo.focus === 'function'
      && restoreTo.isConnected;
    if (restorable) restoreTo.focus();
    // Focus must never stay inside the hidden dialog.
    if (backdrop.contains(document.activeElement) || document.activeElement === document.body) {
      trigger.focus();
    }
  }

  /* ---------------- events ---------------- */

  trigger.addEventListener('click', () => {
    if (isOpen()) close();
    else open();
  });

  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) close();
  });

  backdrop.addEventListener('keydown', (event) => {
    if (event.key === 'Tab') {
      const focusable = [...backdrop.querySelectorAll('a[href], button, input, select')]
        .filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0);
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === input)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  });

  input.addEventListener('input', () => {
    state.expanded.clear();
    if (state.scope !== 'api' && parseQuery(input.value).kindFilter) setScope('api');
    else render();
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveActive(1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveActive(-1);
    } else if (event.key === 'Enter') {
      if (!options.length) return;
      event.preventDefault();
      activateOption(activeIndex);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  });

  document.addEventListener('keydown', (event) => {
    const accel = isMac ? event.metaKey : event.ctrlKey;
    if (accel && !event.altKey && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      // Keep a native palette that may still be listening from opening on top.
      event.stopPropagation();
      if (event.shiftKey) {
        // Legacy API palette shortcut: open straight into the API scope.
        open('api');
      } else if (isOpen()) {
        close();
      } else {
        open();
      }
      return;
    }
    if (event.key === 'Escape' && isOpen()) {
      event.preventDefault();
      close();
    }
  }, { capture: true });

  // Declarative openers: any element marked for this palette (an anchor or a
  // navigation button the site injects), plus the `#search-glossary` hash so
  // Markdown links can open the glossary scope.
  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element
      ? event.target.closest('[data-tvb-search], a[href$="#search-glossary"]')
      : null;
    if (!target) return;
    const requested = target.getAttribute('data-tvb-search');
    if (requested === null) {
      // Plain `#search-glossary` link.
      event.preventDefault();
      open('glossary');
      return;
    }
    if (requested && !SCOPES.includes(requested)) return;
    event.preventDefault();
    open(requested || null);
  }, { capture: true });

  function openFromHash() {
    if (window.location.hash === '#search-glossary') open('glossary');
  }
  window.addEventListener('hashchange', openFromHash);

  /* ---------------- mount ---------------- */

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = STYLES;
    document.head.appendChild(style);
  }

  function mount() {
    injectStyles();
    if (!trigger.isConnected) document.body.appendChild(trigger);
    if (!backdrop.isConnected) document.body.appendChild(backdrop);
  }

  let mountScheduled = false;
  function scheduleMount() {
    if (mountScheduled) return;
    mountScheduled = true;
    const run = () => {
      mountScheduled = false;
      if (!trigger.isConnected || !backdrop.isConnected) mount();
    };
    if (typeof window.requestAnimationFrame === 'function') window.requestAnimationFrame(run);
    else window.setTimeout(run, 0);
  }

  // Mount the single palette instance and keep it mounted: MyST re-renders the
  // page on client-side navigation and may replace the body contents.
  mount();
  new MutationObserver(scheduleMount).observe(document.body, { childList: true });
  if (document.readyState === 'complete') openFromHash();
  else window.addEventListener('load', openFromHash, { once: true });

  window[GLOBAL_KEY] = {
    open: (scope) => open(scope),
    close,
    isOpen,
    setScope: (scope) => setScope(scope),
  };
}

if (typeof document !== 'undefined') {
  if (document.body) startUi();
  else document.addEventListener('DOMContentLoaded', startUi, { once: true });
}
