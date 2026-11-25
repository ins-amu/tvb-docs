import { copyFileSync, existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { gzipSync } from 'node:zlib';

const htmlDir = '_build/html';
const configPath = '_build/site/config.json';
const rawSymbolsPath = '_build/apidoc/api-symbols.json';
const xrefMapPath = 'content/reference/api/api-xref-map.json';

if (!existsSync(rawSymbolsPath) || !existsSync(configPath)) {
  throw new Error('Missing _build/apidoc/api-symbols.json or _build/site/config.json. Run apidoc and myst build first.');
}

const config = JSON.parse(readFileSync(configPath, 'utf8'));
const builtSlugs = new Set((config.projects?.[0]?.pages ?? []).map((p) => p.slug).filter(Boolean));
const symbols = JSON.parse(readFileSync(rawSymbolsPath, 'utf8'));

// Verify each symbol's page slug against _build/site/config.json
let missingSlugs = 0;
for (const entry of symbols) {
  const [slug] = entry.url.replace(/^\//, '').split('#');
  if (!builtSlugs.has(slug)) {
    missingSlugs++;
  }
}
if (missingSlugs > 0) {
  console.warn(`Warning: ${missingSlugs} symbol entries reference slugs not found in _build/site/config.json`);
}

const symbolsJson = JSON.stringify(symbols);
const symbolsOut = join(htmlDir, 'api-symbols.json');
writeFileSync(symbolsOut, symbolsJson, 'utf8');
const gzBytes = gzipSync(Buffer.from(symbolsJson, 'utf8')).length;
console.log(
  `Wrote ${symbolsOut}: ${symbols.length} symbols, ${(Buffer.byteLength(symbolsJson) / 1024).toFixed(1)} KB raw, ${(gzBytes / 1024).toFixed(1)} KB gzipped`
);

// Also check built HTML anchors for all xref symbols
if (existsSync(xrefMapPath)) {
  const xrefMap = JSON.parse(readFileSync(xrefMapPath, 'utf8'));
  const htmlCache = new Map();
  let brokenAnchors = 0;
  for (const [cpath, info] of Object.entries(xrefMap.symbols ?? {})) {
    const htmlFile = join(htmlDir, info.slug, 'index.html');
    const altFile = join(htmlDir, `${info.slug}.html`);
    const targetFile = existsSync(htmlFile) ? htmlFile : (existsSync(altFile) ? altFile : null);
    if (!targetFile) {
      brokenAnchors++;
      continue;
    }
    let doc = htmlCache.get(targetFile);
    if (!doc) {
      doc = readFileSync(targetFile, 'utf8');
      htmlCache.set(targetFile, doc);
    }
    if (!doc.includes(`id="${info.anchor}"`)) {
      console.error(`Missing anchor id="${info.anchor}" in ${targetFile} for ${cpath}`);
      brokenAnchors++;
    }
  }
  if (brokenAnchors > 0) {
    throw new Error(`Found ${brokenAnchors} missing API anchors in built HTML.`);
  }
  console.log(`Verified ${Object.keys(xrefMap.symbols ?? {}).length} API symbol anchors in built HTML.`);
}

// Copy bundled Fuse.js + api-search.js and inject into every entry HTML page
copyFileSync('content/_static/vendor/fuse.min.mjs', join(htmlDir, 'fuse.min.mjs'));
copyFileSync('content/_static/api-search.js', join(htmlDir, 'api-search.js'));

let injected = 0;
for (const name of readdirSync(htmlDir, { recursive: true })) {
  if (!name.endsWith('.html')) continue;
  const parts = name.split('/');
  if (parts.some((p) => p.startsWith('_')) || parts[0] === 'lite') continue;
  const path = join(htmlDir, name);
  const doc = readFileSync(path, 'utf8');
  if (!doc.includes('</body>') || doc.includes('id="tvb-api-search-script"')) continue;
  const src = relative(dirname(path), join(htmlDir, 'api-search.js'));
  const symbolsHref = relative(dirname(path), symbolsOut);
  const tag = `<script id="tvb-api-search-script" type="module" src="${src}" data-symbols="${symbolsHref}"></script>`;
  writeFileSync(path, doc.replace('</body>', `${tag}</body>`), 'utf8');
  injected++;
}
console.log(`Injected API fuzzy symbol palette into ${injected} HTML pages.`);
