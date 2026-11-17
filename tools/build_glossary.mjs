import { copyFileSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { relative, dirname, join } from 'node:path';
import { glossaryMatches, visitProse } from '../plugins/glossary-links.mjs';

const site = '_build/site/content';
const html = '_build/html';
const pages = readdirSync(site, { recursive: true })
  .filter((name) => name.endsWith('.json'))
  .map((name) => JSON.parse(readFileSync(join(site, name), 'utf8')))
  .filter((page) => page.mdast);
const glossary = pages.find((page) => page.location === '/content/glossary.md');
if (!glossary) throw new Error('Cannot find built glossary. Run the MyST HTML build first.');

function* walk(node) {
  yield node;
  for (const child of node.children ?? []) yield* walk(child);
}

const anchorIds = new Set([...walk(glossary.mdast)]
  .filter((node) => node.type === 'definitionTerm')
  .map((node) => node.html_id));
anchorIds.delete(undefined);
if (anchorIds.size === 0) throw new Error('The built glossary has no definition anchors.');
const glossaryHtml = readFileSync(join(html, 'glossary/index.html'), 'utf8');
for (const id of anchorIds) {
  if (!glossaryHtml.includes(`id="${id}"`)) throw new Error(`Missing glossary anchor: ${id}`);
}
const glossaryPaths = new Set(['/glossary', `${process.env.BASE_URL ?? ''}/glossary`]);

const matches = glossaryMatches();
let broken = 0;
let checked = 0;
let unlinked = 0;
for (const page of pages) {
  const location = page.location.replace(/^\//, '');
  for (const node of walk(page.mdast)) {
    if (node.type !== 'crossReference' || !node.identifier?.startsWith('term-')) continue;
    checked++;
    const pointsToGlossary = page === glossary || glossaryPaths.has(node.url?.replace(/\/$/, ''));
    if (!node.resolved || !anchorIds.has(node.html_id) || !pointsToGlossary) {
      console.error(`${location}: broken glossary link to "${node.label ?? node.identifier}"`);
      broken++;
    }
  }
  if (page === glossary) continue;
  const missed = new Set();
  visitProse(page.mdast, (node) => {
    for (const { label } of matches(node.value)) missed.add(label);
    return [node];
  });
  if (missed.size) {
    const detail = `Unlinked glossary terms: ${[...missed].sort().join(', ')}`;
    console.warn(process.env.GITHUB_ACTIONS
      ? `::warning file=${location}::${detail}`
      : `${location}: ${detail}`);
    unlinked += missed.size;
  }
}
console.log(`Checked ${checked} glossary links. Found ${unlinked} unlinked page/term pairs.`);
if (broken) process.exit(1);

// Load the enhancement on every entry page so client-side navigation to the
// glossary works too. A relative URL also supports GitHub Pages subpaths.
const script = 'glossary-search.js';
copyFileSync(join('content/_static', script), join(html, script));
for (const name of readdirSync(html, { recursive: true })) {
  if (!name.endsWith('.html') || name.split('/').some((part) => part.startsWith('_'))) continue;
  const path = join(html, name);
  const document = readFileSync(path, 'utf8');
  if (!document.includes('</body>') || document.includes('id="tvb-glossary-search-script"')) continue;
  const src = relative(dirname(path), join(html, script));
  const tag = `<script id="tvb-glossary-search-script" defer src="${src}"></script>`;
  writeFileSync(path, document.replace('</body>', `${tag}</body>`));
}
