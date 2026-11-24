// Resolve `{py}` roles and dotted `tvb.*` inline code references against api-xref-map.json.
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const xrefPath = resolve('content/reference/api/api-xref-map.json');
const apiDir = resolve('content/reference/api');

let cachedMap = null;
function loadXrefMap() {
  if (cachedMap) return cachedMap;
  if (!existsSync(xrefPath)) {
    cachedMap = { symbols: {}, shortNames: {}, aliases: {} };
    return cachedMap;
  }
  try {
    cachedMap = JSON.parse(readFileSync(xrefPath, 'utf8'));
  } catch {
    cachedMap = { symbols: {}, shortNames: {}, aliases: {} };
  }
  return cachedMap;
}

function resolveTarget(rawTarget) {
  const map = loadXrefMap();
  let target = rawTarget.trim().replace(/^~/, '');
  if (map.aliases?.[target]) target = map.aliases[target];
  if (map.symbols?.[target]) return { canonical: target, entry: map.symbols[target] };
  const mapped = map.shortNames?.[target];
  if (mapped && map.symbols?.[mapped]) return { canonical: mapped, entry: map.symbols[mapped] };
  return null;
}

const pyRole = {
  name: 'py',
  doc: 'Link to a documented TVB Python symbol (module, class, method, function, or trait).',
  body: {
    type: String,
    required: true,
  },
  run(data, vfile) {
    const raw = String(data.body ?? '').trim();
    let display = null;
    let target = raw;
    const angle = raw.match(/^(.+?)\s*<([^>]+)>$/);
    if (angle) {
      display = angle[1].trim();
      target = angle[2].trim();
    }
    const tilde = target.startsWith('~');
    const cleanTarget = tilde ? target.slice(1) : target;
    if (!display) {
      display = tilde ? cleanTarget.split('.').pop() : cleanTarget;
    }

    const hit = resolveTarget(cleanTarget);
    if (!hit) {
      if (existsSync(xrefPath) && vfile?.message) {
        vfile.message(`Unresolved {py} API symbol: "${cleanTarget}"`);
      }
      return [{ type: 'inlineCode', value: display }];
    }

    if (hit.entry.kind === 'trait' || hit.entry.kind === 'attribute') {
      return [
        {
          type: 'link',
          url: hit.entry.url,
          children: [{ type: 'inlineCode', value: display }],
        },
      ];
    }

    return [
      {
        type: 'crossReference',
        identifier: hit.entry.anchor,
        label: hit.entry.anchor,
        children: [{ type: 'inlineCode', value: display }],
      },
    ];
  },
};

const skipTypes = new Set([
  'code', 'codeBlock', 'crossReference', 'heading', 'html', 'link',
  'linkReference', 'math', 'inlineMath', 'output', 'raw',
]);

function linkDottedInlineCode(tree, file) {
  if (!existsSync(xrefPath)) return;
  if (file?.path && resolve(file.path).startsWith(apiDir)) return;

  function walk(node, blocked) {
    if (!node?.children || skipTypes.has(node.type)) return;
    const isBlocked = blocked || node.type === 'definitionTerm';
    node.children = node.children.map((child) => {
      if (!isBlocked && child.type === 'inlineCode' && typeof child.value === 'string') {
        const val = child.value.trim();
        if (val.startsWith('tvb.')) {
          const hit = resolveTarget(val);
          if (hit) {
            if (hit.entry.kind === 'trait' || hit.entry.kind === 'attribute') {
              return {
                type: 'link',
                url: hit.entry.url,
                children: [{ type: 'inlineCode', value: val }],
              };
            }
            return {
              type: 'crossReference',
              identifier: hit.entry.anchor,
              label: hit.entry.anchor,
              children: [{ type: 'inlineCode', value: val }],
            };
          }
        }
      }
      walk(child, isBlocked);
      return child;
    });
  }

  walk(tree, false);
}

const plugin = {
  name: 'TVB Python API xrefs',
  roles: [pyRole],
  transforms: [{ name: 'tvb-py-inline-xrefs', stage: 'document', plugin: () => linkDottedInlineCode }],
};

export default plugin;
