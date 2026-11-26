/**
 * Node tests for the browser-side unified search module.
 *
 * Run with: node --test tests/test_site_search.mjs
 *
 * Only the pure (DOM-free) half of content/_static/site-search.mjs is covered
 * here: query parsing, API ranking (including the filter-before-limit fix),
 * prose/glossary fuzzy matching, section filtering and URL resolution.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  API_KINDS,
  createApiSearch,
  createDocsSearch,
  createGlossarySearch,
  makeAcronym,
  normalizeManifest,
  parseQuery,
  resolveRecordUrl,
  uniqueByHref,
} from '../content/_static/site-search.mjs';

const MODULE_URL = 'https://example.org/tvb-docs/site-search.mjs';

/* ------------------------------------------------------------------ */
/* Fixtures                                                             */
/* ------------------------------------------------------------------ */

function apiEntry({ id, kind, module, name, signature = '', summary = '', used = 0 }) {
  return {
    id,
    name: name ?? id.split('.').pop(),
    kind,
    module,
    signature,
    summary,
    url: `/${id.replace(/\./g, '-')}#${kind}-${id.replace(/\./g, '-')}`,
    anchor: `${kind}-${id.replace(/\./g, '-')}`,
    page: `${id}.md`,
    used_in_count: used,
  };
}

const API_FIXTURE = [
  apiEntry({
    id: 'tvb.simulator.models.oscillator.Generic2dOscillator',
    kind: 'class',
    module: 'tvb.simulator.models.oscillator',
    used: 32,
  }),
  apiEntry({
    id: 'tvb.simulator.models.oscillator.Generic2dOscillator.dfun',
    kind: 'method',
    module: 'tvb.simulator.models.oscillator',
  }),
  apiEntry({
    id: 'tvb.simulator.models.oscillator.SupHopf.dfun',
    kind: 'method',
    module: 'tvb.simulator.models.oscillator',
  }),
  apiEntry({
    id: 'tvb.simulator.models.base.Model.dfun',
    kind: 'method',
    module: 'tvb.simulator.models.base',
  }),
  apiEntry({
    id: 'tvb.simulator.models.oscillator',
    kind: 'module',
    module: 'tvb.simulator.models.oscillator',
    used: 1,
  }),
  apiEntry({
    id: 'tvb.simulator.models.oscillator.SupHopf.tau',
    kind: 'trait',
    module: 'tvb.simulator.models.oscillator',
  }),
  apiEntry({
    id: 'tvb.simulator.models.oscillator.SupHopf.state_variables',
    kind: 'attribute',
    module: 'tvb.simulator.models.oscillator',
  }),
  apiEntry({
    id: 'tvb.analyzers.fft.compute_fast_fourier_transform',
    kind: 'function',
    module: 'tvb.analyzers.fft',
    name: 'compute_fast_fourier_transform',
  }),
];

const DOCS_FIXTURE = [
  {
    url: '/quickstart-guide#intro',
    title: 'Quickstart',
    heading: 'Introduction',
    content: 'Run your first network simulation with the generic 2d oscillator.',
    section: 'tutorials',
  },
  {
    url: '/quickstart-guide#neuro',
    title: 'Quickstart',
    heading: 'Neuroimaging datasets',
    content: 'Loading structural neuroimaging data and building connectivity matrices.',
    section: 'tutorials',
  },
  {
    url: '/reference/connectivity#delays',
    title: 'Connectivity',
    heading: 'Conduction delays',
    content: 'Track length delays are derived from the white-matter tracts.',
    section: 'reference',
  },
  {
    url: '/old-about#scope',
    title: 'About these docs',
    heading: 'Scope',
    content: 'This book is a living document for the TVB simulation stack.',
    section: 'about',
  },
];

const GLOSSARY_FIXTURE = [
  {
    url: '/glossary#term-oscillator',
    title: 'Oscillator',
    content: 'A dynamical system whose state follows a closed orbit in phase space.',
  },
  {
    url: '/glossary#term-neural-mass-model',
    title: 'Neural mass model',
    content: 'A mean-field reduction that describes the average activity of a population of neurons.',
  },
  {
    url: '/glossary#term-synaptic-plasticity',
    title: 'Synaptic plasticity',
    content: 'Experience-dependent change in synaptic weights.',
  },
];

/* ------------------------------------------------------------------ */
/* Query parsing                                                        */
/* ------------------------------------------------------------------ */

test('parseQuery recognises every legacy API kind prefix', () => {
  const expected = {
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
  assert.deepEqual(expected, {
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
  });
  for (const [prefix, kind] of Object.entries(expected)) {
    assert.deepEqual(parseQuery(`${prefix}:g2do`), { kindFilter: kind, query: 'g2do' }, prefix);
  }
});

test('parseQuery keeps unknown prefixes as search terms', () => {
  assert.deepEqual(parseQuery('note:abc'), { kindFilter: null, query: 'note:abc' });
  assert.deepEqual(parseQuery('http://x'), { kindFilter: null, query: 'http://x' });
  assert.deepEqual(parseQuery('constructor:x'), { kindFilter: null, query: 'constructor:x' });
  assert.deepEqual(parseQuery('  '), { kindFilter: null, query: '' });
});

/* ------------------------------------------------------------------ */
/* API index                                                            */
/* ------------------------------------------------------------------ */

test('makeAcronym produces g2do for the generic 2d oscillator', () => {
  assert.equal(makeAcronym('Generic2dOscillator'), 'g2do');
  assert.equal(makeAcronym('tvb.simulator.models.oscillator.SupHopf'), 'sh');
});

test('API search resolves acronym queries such as g2do', () => {
  const api = createApiSearch(API_FIXTURE);
  const { items, total } = api.search({ query: 'g2do' });
  assert.ok(total >= 1);
  assert.equal(items[0].id, 'tvb.simulator.models.oscillator.Generic2dOscillator');
});

test('API search resolves dotted module.member queries such as osc.dfun', () => {
  const api = createApiSearch(API_FIXTURE);
  const { items } = api.search({ query: 'osc.dfun' });
  const names = items.map((item) => item.id);
  assert.ok(names.includes('tvb.simulator.models.oscillator.Generic2dOscillator.dfun'), names.join(', '));
  assert.ok(names.includes('tvb.simulator.models.oscillator.SupHopf.dfun'), names.join(', '));
  assert.ok(
    names.indexOf('tvb.simulator.models.oscillator.Generic2dOscillator.dfun')
      < names.indexOf('tvb.simulator.models.base.Model.dfun'),
    'oscillator members outrank unrelated modules',
  );
});

test('exact dotted members outrank prefix lookalikes', () => {
  const lookalike = apiEntry({
    id: 'tvb.simulator.models.oscillator.SupHopf.dfun_intermediates',
    module: 'tvb.simulator.models.oscillator', kind: 'trait', used: 30,
  });
  const { items } = createApiSearch([lookalike, ...API_FIXTURE]).search({ query: 'osc.dfun' });
  assert.equal(items[0].kind, 'method');
  assert.ok(items.some(({ id }) => id === lookalike.id));
});

test('API search exposes all six kinds', () => {
  const api = createApiSearch(API_FIXTURE);
  assert.deepEqual(API_KINDS, ['module', 'class', 'method', 'function', 'trait', 'attribute']);
  for (const kind of API_KINDS) {
    const { items } = api.search({ query: 'tvb', kind, limit: 10 });
    assert.ok(items.length > 0, `no hits for kind ${kind}`);
    assert.ok(items.every((item) => item.kind === kind), `mixed kinds returned for ${kind}`);
  }
});

test('API search rank-filters by kind before the candidate cutoff', () => {
  // 250 functions dominate the unfiltered ranking; five classes only match
  // weakly. Filtering after a global cutoff (the legacy palette) loses them.
  const entries = [];
  for (let i = 0; i < 250; i++) {
    entries.push(apiEntry({
      id: `pkg.fn${i}.kernel_launcher_${i}`,
      kind: 'function',
      module: `pkg.fn${i}`,
      name: 'kernel_launcher',
    }));
  }
  for (let i = 0; i < 5; i++) {
    entries.push(apiEntry({
      id: `pkg.kernels.Kernelish${i}`,
      kind: 'class',
      module: 'pkg.kernels',
      name: `Kernelish${i}`,
    }));
  }

  const all = createApiSearch(entries);
  const classOnly = createApiSearch(entries.filter((entry) => entry.kind === 'class'));

  const filtered = all.search({ query: 'kernel', kind: 'class', limit: 5 });
  const reference = classOnly.search({ query: 'kernel', limit: 5 });

  assert.equal(filtered.total, 5, 'kind filter must not be truncated by other kinds');
  assert.deepEqual(
    filtered.items.map((item) => item.id),
    reference.items.map((item) => item.id),
  );
  assert.equal(filtered.items.length, 5);
});

test('API search orders empty queries by documentation popularity', () => {
  const api = createApiSearch(API_FIXTURE);
  const { items } = api.search({ kind: 'class', limit: 5 });
  assert.equal(items.length, 1);
  assert.equal(items[0].name, 'Generic2dOscillator');
  const popular = createApiSearch([
    apiEntry({ id: 'a', kind: 'class', module: 'a', used: 1 }),
    apiEntry({ id: 'b', kind: 'class', module: 'b', used: 9 }),
  ]).search({ limit: 5 });
  assert.deepEqual(popular.items.map((item) => item.id), [
    'b',
    'a',
  ]);
});

test('API search respects an explicit limit and reports the true total', () => {
  const api = createApiSearch(API_FIXTURE);
  const { items, total } = api.search({ query: 'osc', limit: 2 });
  assert.equal(items.length, 2);
  assert.ok(total > items.length);
});

/* ------------------------------------------------------------------ */
/* Docs index                                                           */
/* ------------------------------------------------------------------ */

test('docs search matches prefixes while typing', () => {
  const docs = createDocsSearch(DOCS_FIXTURE);
  const { items } = docs.search({ query: 'neuro' });
  assert.equal(items.length, 1);
  assert.equal(items[0].url, '/quickstart-guide#neuro');
});

test('docs search tolerates a typo', () => {
  const docs = createDocsSearch(DOCS_FIXTURE);
  const { items } = docs.search({ query: 'oscilator' });
  assert.equal(items[0].url, '/quickstart-guide#intro');
});

test('docs search filters by section before applying its limit', () => {
  const records = [];
  for (let i = 0; i < 200; i++) {
    records.push({
      url: `/tutorials/page-${i}#networks`,
      title: 'Network tutorial',
      heading: 'Networks',
      content: 'Network construction with connectivity matrices.',
      section: 'tutorials',
    });
  }
  records.push({
    url: '/reference/connectivity#networks',
    title: 'Connectivity',
    heading: 'Networks',
    content: 'Network connectivity matrices are stored as dense arrays.',
    section: 'reference',
  });

  const docs = createDocsSearch(records);
  const filtered = docs.search({ query: 'networks', section: 'reference', limit: 3 });
  assert.equal(filtered.total, 1);
  assert.deepEqual(filtered.items.map((item) => item.url), ['/reference/connectivity#networks']);

  const unfiltered = docs.search({ query: 'networks', section: 'tutorials', limit: 3 });
  assert.equal(unfiltered.items.length, 3);
  assert.ok(unfiltered.items.every((item) => item.section === 'tutorials'));
});

test('docs search deduplicates by destination before limiting and can exclude API hits', () => {
  const first = { ...DOCS_FIXTURE[0], title: 'Oscillator' };
  const second = { ...first, url: '/another-oscillator', title: 'Another oscillator' };
  const search = createDocsSearch([first, first, second]);
  const { items, total } = search.search({ query: 'oscillator', limit: 2 });
  assert.equal(total, 2);
  assert.equal(new Set(items.map(({ url }) => url)).size, 2);
  const withoutApi = search.search({ query: 'oscillator', excludeUrls: new Set([first.url]) });
  assert.deepEqual(withoutApi.items.map(({ url }) => url), [second.url]);
});

test('docs search accepts records with empty heading and content', () => {
  const docs = createDocsSearch([
    { url: '/bare#top', title: 'Bare page', heading: '', content: '', section: 'about' },
  ]);
  const { items } = docs.search({ query: 'bare' });
  assert.equal(items.length, 1);
  assert.equal(items[0].url, '/bare#top');
});

test('docs search returns nothing for an empty query', () => {
  const docs = createDocsSearch(DOCS_FIXTURE);
  assert.deepEqual(docs.search({ query: '   ' }), { items: [], total: 0 });
});

/* ------------------------------------------------------------------ */
/* Glossary index                                                       */
/* ------------------------------------------------------------------ */

test('glossary search matches terms and definitions, fuzzily', () => {
  const glossary = createGlossarySearch(GLOSSARY_FIXTURE);

  const byTerm = glossary.search({ query: 'oscill' });
  assert.equal(byTerm.items[0].url, '/glossary#term-oscillator');

  const byDefinition = glossary.search({ query: 'phase space' });
  assert.equal(byDefinition.items[0].url, '/glossary#term-oscillator');

  const typo = glossary.search({ query: 'synapitc' });
  assert.equal(typo.items[0].url, '/glossary#term-synaptic-plasticity');
});

/* ------------------------------------------------------------------ */
/* Manifest, links and de-duplication                                   */
/* ------------------------------------------------------------------ */

test('normalizeManifest keeps sections and defaults index paths', () => {
  const manifest = normalizeManifest({
    sections: [{ id: 'tutorials', label: 'Tutorials' }, { id: 'about', label: 'About' }],
  });
  assert.deepEqual(manifest.sections, [
    { id: 'tutorials', label: 'Tutorials' },
    { id: 'about', label: 'About' },
  ]);
  assert.equal(manifest.api, 'api-symbols.json');
  assert.equal(manifest.docs, 'search-docs.json');
  assert.equal(manifest.glossary, 'search-glossary.json');

  const custom = normalizeManifest({ api: 'data/api.json', docs: 'data/docs.json', glossary: 'data/glossary.json' });
  assert.equal(custom.api, 'data/api.json');
  assert.equal(custom.docs, 'data/docs.json');
  assert.equal(custom.glossary, 'data/glossary.json');
});

test('record URLs resolve against the module directory, not the page path', () => {
  assert.equal(
    resolveRecordUrl('/quickstart-guide#intro', MODULE_URL),
    'https://example.org/tvb-docs/quickstart-guide#intro',
  );
  assert.equal(resolveRecordUrl('/', MODULE_URL), 'https://example.org/tvb-docs/');
  assert.equal(resolveRecordUrl('glossary#term-tau', MODULE_URL), 'https://example.org/tvb-docs/glossary#term-tau');
  assert.equal(resolveRecordUrl('https://elsewhere.test/x', MODULE_URL), 'https://elsewhere.test/x');
  assert.equal(resolveRecordUrl('', MODULE_URL), '');
});

test('uniqueByHref keeps the first hit per link and drops linkless rows', () => {
  const items = [
    { url: '/a#x', id: 1 },
    { url: '/a#x', id: 2 },
    { url: '/b', id: 3 },
    { url: '', id: 4 },
  ];
  const kept = uniqueByHref(items, (item) => resolveRecordUrl(item.url, MODULE_URL));
  assert.deepEqual(kept.map((item) => item.id), [1, 3]);
});
