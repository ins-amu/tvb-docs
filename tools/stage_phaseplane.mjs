// Stage shared Trajecturtle assets + per-card JSON specs into _build/html/trajecturtle/
// and inject the relative-URL module script into built HTML pages.
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';

const html = '_build/html';
const outDir = join(html, 'trajecturtle');
mkdirSync(outDir, { recursive: true });
copyFileSync('content/_static/trajecturtle/hydrate.js', join(outDir, 'hydrate.js'));

const target = join(html, 'trajecturtle', 'hydrate.js');
for (const name of readdirSync(html, { recursive: true })) {
  if (!name.endsWith('.html') || name.split('/').some((part) => part.startsWith('_'))) continue;
  const path = join(html, name);
  const document = readFileSync(path, 'utf8');
  if (!document.includes('</body>') || document.includes('id="tvb-phaseplane-hydrate"')) continue;
  const src = relative(dirname(path), target).replaceAll('\\', '/');
  const tag = `<script id="tvb-phaseplane-hydrate" type="module" src="${src}"></script>`;
  writeFileSync(path, document.replace('</body>', `${tag}</body>`));
}
console.log('Staged Trajecturtle phase-plane assets and hydration script.');
