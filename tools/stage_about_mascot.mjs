// Stage the About-section mascot audio script into _build/html/
// and inject the relative-URL module script into built documentation HTML pages.
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_ID = 'tvb-about-mascot-script';

/**
 * Copy `about-mascot.mjs` (and `goat.opus` if not already staged) into `htmlDir`,
 * then inject `<script id="tvb-about-mascot-script" ...>` into documentation HTML files.
 */
export function stageAboutMascot({
  htmlDir = '_build/html',
  scriptSrc = 'content/_static/about-mascot.mjs',
  audioSrc = '_static/goat.opus',
} = {}) {
  mkdirSync(htmlDir, { recursive: true });
  const target = join(htmlDir, 'about-mascot.mjs');
  copyFileSync(scriptSrc, target);

  const audioTarget = join(htmlDir, 'goat.opus');
  if (existsSync(audioSrc) && !existsSync(audioTarget)) {
    copyFileSync(audioSrc, audioTarget);
  }

  let injected = 0;
  for (const name of readdirSync(htmlDir, { recursive: true })) {
    const normalized = String(name).replaceAll('\\', '/');
    if (!normalized.endsWith('.html')) continue;
    const parts = normalized.split('/');
    if (parts.some((part) => part.startsWith('_'))) continue;
    if (parts[0] === 'lite' || parts[0] === 'notebooks') continue;
    if (parts[parts.length - 1] === 'phase-plane-standalone.html') continue;

    const path = join(htmlDir, name);
    const document = readFileSync(path, 'utf8');
    if (!document.includes('</body>') || document.includes(`id="${SCRIPT_ID}"`)) continue;
    const src = relative(dirname(path), target).replaceAll('\\', '/');
    const tag = `<script id="${SCRIPT_ID}" type="module" src="${src}"></script>`;
    writeFileSync(path, document.replace('</body>', `${tag}</body>`));
    injected++;
  }
  return { injected, target, audioTarget };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { injected } = stageAboutMascot();
  console.log(`Staged About mascot audio script on ${injected} HTML pages.`);
}
