import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';

const html = '_build/html';
const assets = 'content/_static';
const project = readJson('_build/site/config.json').projects[0];
const symbols = readJson('_build/apidoc/api-symbols.json');
const xrefs = readJson('content/reference/api/api-xref-map.json');
const native = readJson(join(html, 'myst.search.json'));
const base = (process.env.BASE_URL ?? '').replace(/\/$/, '');

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function writeJson(name, value) {
  writeFileSync(join(html, name), JSON.stringify(value));
}

// MyST's built page list flattens the TOC: level-1 caption rows start book
// parts; deeper captions must not replace the active part. Use built slugs,
// not filenames (including colliding index.md names and generated API pages).
const sections = [];
const sectionBySlug = new Map([[project.index, '']]);
let section = '';
for (const page of project.pages) {
  if (!page.slug && page.level === 1 && page.title) {
    section = page.title.toLowerCase().normalize('NFKD').replace(/\p{M}/gu, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section';
    const stem = section;
    for (let suffix = 2; sections.some(({ id }) => id === section); suffix++) {
      section = `${stem}-${suffix}`;
    }
    sections.push({ id: section, label: page.title });
  }
  if (page.slug) sectionBySlug.set(page.slug, section);
}

function normalizeRecordUrl(url) {
  // The native record schema uses root-relative URLs. Also accept a configured
  // base prefix so the browser always adds the deployment subpath exactly once.
  if (!url.startsWith('/') || url.startsWith('//')) throw new Error(`Unexpected search URL: ${url}`);
  if (base && (url === base || url.startsWith(`${base}/`) || url.startsWith(`${base}#`))) {
    const rest = url.slice(base.length);
    return rest.startsWith('/') ? rest : `/${rest}`;
  }
  return url;
}

if (native.version !== '1' || !Array.isArray(native.records)) {
  throw new Error('Unsupported MyST search index format');
}
const docs = native.records.map((record) => {
  const url = normalizeRecordUrl(record.url);
  const slug = url.split(/[?#]/, 1)[0].replace(/^\/|\/$/g, '') || project.index;
  if (!sectionBySlug.has(slug)) throw new Error(`Search record has no built page: ${url}`);
  const { lvl1: title = '', ...headings } = record.hierarchy;
  const heading = [2, 3, 4, 5, 6].map((level) => headings[`lvl${level}`]).filter(Boolean).at(-1) ?? '';
  return { url, title, heading, content: record.content ?? '', section: sectionBySlug.get(slug) };
});

const pageFiles = new Map();
for (const slug of sectionBySlug.keys()) {
  const path = [join(html, slug, 'index.html'), join(html, `${slug}.html`)].find(existsSync);
  if (!path) throw new Error(`No generated HTML entry for ${slug}`);
  pageFiles.set(slug, path);
}

// Keep the original API build's link validation, so malformed result links
// fail the docs build instead of sending readers to a missing target.
const apiPages = new Map();
let brokenAnchors = 0;
for (const [id, { slug, anchor }] of Object.entries(xrefs.symbols)) {
  if (!apiPages.has(slug)) {
    apiPages.set(slug, pageFiles.has(slug) ? readFileSync(pageFiles.get(slug), 'utf8') : '');
  }
  if (!apiPages.get(slug).includes(`id="${anchor}"`)) {
    console.error(`Missing API anchor: ${slug}#${anchor} (${id})`);
    brokenAnchors++;
  }
}
if (brokenAnchors) throw new Error(`Found ${brokenAnchors} missing API anchors`);
console.log(`Verified ${Object.keys(xrefs.symbols).length} API anchors.`);

writeJson('api-symbols.json', symbols);
writeJson('search-docs.json', docs);
writeJson('site-search-manifest.json', {
  sections,
  api: 'api-symbols.json',
  docs: 'search-docs.json',
  glossary: 'search-glossary.json',
});

const script = 'site-search.mjs';
mkdirSync(join(html, 'vendor'), { recursive: true });
for (const name of [script, 'vendor/fuse.min.mjs', 'vendor/minisearch-7.2.0.esm.js', 'vendor/minisearch-7.2.0.LICENSE.txt']) {
  copyFileSync(join(assets, name), join(html, name));
}

const entries = new Set([...pageFiles.values(), join(html, 'index.html')]);
for (const path of entries) {
  const doc = readFileSync(path, 'utf8');
  if (!doc.includes('</body>')) throw new Error(`Missing body in ${path}`);
  if (doc.includes('id="tvb-site-search-script"')) continue;
  const src = relative(dirname(path), join(html, script)).replaceAll('\\', '/');
  const tag = `<script id="tvb-site-search-script" type="module" src="${src}"></script>`;
  writeFileSync(path, doc.replace('</body>', `${tag}</body>`));
}

console.log(`Built site search: ${docs.length} docs records in ${sections.length} book sections, ${symbols.length} symbols; installed on ${entries.size} HTML pages.`);
