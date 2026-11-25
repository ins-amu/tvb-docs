// Lazy, content-cached wrapper around the jupyter-book-marimo executable plugin.
// Avoids spawning ~175 Python subprocesses for pages that contain no {marimo} cells,
// and caches compiled marimo outputs by node/binary fingerprint in _build/cache/marimo.
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const CACHE_DIR = resolve('_build/cache/marimo');

const BOOLEAN_OPTION = { type: 'boolean' };
const STRING_OPTION = { type: 'string' };
const NUMBER_OPTION = { type: 'number' };

const EXECUTION_OPTIONS = {
  eval: BOOLEAN_OPTION,
  echo: BOOLEAN_OPTION,
  editor: BOOLEAN_OPTION,
  output: BOOLEAN_OPTION,
  'server-output': BOOLEAN_OPTION,
  error: BOOLEAN_OPTION,
  include: BOOLEAN_OPTION,
};

const MARIMO_DIRECTIVE_OPTIONS = {
  ...EXECUTION_OPTIONS,
  query: STRING_OPTION,
  engine: STRING_OPTION,
  'hide-code': BOOLEAN_OPTION,
  'hide-output': BOOLEAN_OPTION,
  disabled: BOOLEAN_OPTION,
  unparsable: BOOLEAN_OPTION,
  name: STRING_OPTION,
  column: NUMBER_OPTION,
};

const MARIMO_CONFIG_OPTIONS = {
  ...EXECUTION_OPTIONS,
  'external-env': BOOLEAN_OPTION,
  header: STRING_OPTION,
  pyproject: STRING_OPTION,
};

function findMarimoBinary() {
  const candidates = [
    resolve('.venv/bin/jupyter-book-marimo'),
    resolve('.venv/Scripts/jupyter-book-marimo.exe'),
    resolve('.venv/Scripts/jupyter-book-marimo'),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return 'jupyter-book-marimo';
}

function runSyncDirective(name, data) {
  const bin = findMarimoBinary();
  const res = spawnSync(bin, ['--directive', name], {
    input: JSON.stringify(data),
    encoding: 'utf-8',
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  if (res.error) throw res.error;
  if (res.status !== 0) {
    throw new Error(
      `Non-zero error code (${res.status}) running "${bin}" for directive '${name}':\n${res.stderr}`,
    );
  }
  return JSON.parse(res.stdout);
}

function runAsyncTransform(bin, tree) {
  return new Promise((resolvePromise, rejectPromise) => {
    const proc = spawn(bin, ['--transform', 'marimo-islands']);
    const stdoutChunks = [];
    const stderrChunks = [];
    proc.stdout.on('data', (chunk) => stdoutChunks.push(chunk));
    proc.stderr.on('data', (chunk) => stderrChunks.push(chunk));
    proc.on('error', rejectPromise);
    proc.on('close', (code) => {
      if (code !== 0) {
        const stderr = Buffer.concat(stderrChunks).toString('utf-8');
        rejectPromise(
          new Error(`Non-zero error code (${code}) running "${bin}" for marimo-islands:\n${stderr}`),
        );
        return;
      }
      try {
        resolvePromise(JSON.parse(Buffer.concat(stdoutChunks).toString('utf-8')));
      } catch (err) {
        rejectPromise(err);
      }
    });
    proc.stdin.write(JSON.stringify(tree));
    proc.stdin.end();
  });
}

function collectMarimoNodes(node, out = []) {
  if (!node || typeof node !== 'object') return out;
  if (node.type === 'marimoCell' || node.type === 'marimoConfig') {
    out.push(node);
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) {
      collectMarimoNodes(child, out);
    }
  }
  return out;
}

function replaceMarimoNodes(node, nodeReplacements) {
  if (!node || typeof node !== 'object' || !Array.isArray(node.children)) return;
  const nextChildren = [];
  for (const child of node.children) {
    if (child && typeof child === 'object' && nodeReplacements.has(child)) {
      const replacement = nodeReplacements.get(child);
      if (Array.isArray(replacement)) {
        nextChildren.push(...replacement);
      }
      continue;
    }
    replaceMarimoNodes(child, nodeReplacements);
    nextChildren.push(child);
  }
  node.children = nextChildren;
}

function binarySignature(bin) {
  try {
    const st = statSync(bin);
    return { path: bin, mtimeMs: st.mtimeMs, size: st.size };
  } catch {
    return { path: bin, mtimeMs: 0, size: 0 };
  }
}

function computeCacheKey(nodes, binSig) {
  const hash = createHash('sha256');
  hash.update(JSON.stringify({ v: 1, binSig, nodes }));
  return hash.digest('hex');
}

function splitSentinelResult(children, count) {
  const replacements = [];
  let cursor = 0;
  for (let i = 0; i < count; i++) {
    const startMarker = `__TVB_MARIMO_START_${i}__`;
    const endMarker = `__TVB_MARIMO_END_${i}__`;
    while (cursor < children.length && children[cursor]?.value !== startMarker) {
      cursor++;
    }
    if (cursor >= children.length) {
      throw new Error(`Missing marimo sentinel start marker ${startMarker}`);
    }
    cursor++; // skip start marker
    const slice = [];
    while (cursor < children.length && children[cursor]?.value !== endMarker) {
      slice.push(children[cursor]);
      cursor++;
    }
    if (cursor >= children.length) {
      throw new Error(`Missing marimo sentinel end marker ${endMarker}`);
    }
    cursor++; // skip end marker
    replacements.push(slice);
  }
  return replacements;
}

function marimoTransform() {
  return async (tree) => {
    const collected = collectMarimoNodes(tree);
    if (collected.length === 0) return tree;

    const bin = findMarimoBinary();
    const useCache = process.env.TVB_MARIMO_NO_CACHE !== '1';
    const key = computeCacheKey(collected, binarySignature(bin));
    const cacheFile = join(CACHE_DIR, `${key}.json`);

    let replacements = null;
    if (useCache && existsSync(cacheFile)) {
      try {
        const cached = JSON.parse(readFileSync(cacheFile, 'utf-8'));
        if (Array.isArray(cached) && cached.length === collected.length) {
          replacements = cached;
        }
      } catch {
        replacements = null;
      }
    }

    if (replacements === null) {
      const wrappedChildren = [];
      for (let i = 0; i < collected.length; i++) {
        wrappedChildren.push({ type: 'text', value: `__TVB_MARIMO_START_${i}__` });
        wrappedChildren.push(collected[i]);
        wrappedChildren.push({ type: 'text', value: `__TVB_MARIMO_END_${i}__` });
      }
      const result = await runAsyncTransform(bin, { type: 'root', children: wrappedChildren });
      replacements = splitSentinelResult(result.children ?? [], collected.length);

      if (useCache) {
        try {
          mkdirSync(dirname(cacheFile), { recursive: true });
          const tmpFile = `${cacheFile}.${process.pid}.tmp`;
          writeFileSync(tmpFile, JSON.stringify(replacements), 'utf-8');
          renameSync(tmpFile, cacheFile);
        } catch {
          // Best-effort cache write; ignore races or read-only filesystems.
        }
      }
    }

    const mapping = new Map();
    for (let i = 0; i < collected.length; i++) {
      mapping.set(collected[i], replacements[i]);
    }
    replaceMarimoNodes(tree, mapping);
    return tree;
  };
}

const plugin = {
  name: 'TVB lazy marimo wrapper',
  directives: [
    {
      name: 'marimo',
      doc: 'Execute a marimo cell.',
      arg: {
        type: 'string',
        required: true,
        doc: 'Cell language: markdown, python, sql.',
      },
      options: MARIMO_DIRECTIVE_OPTIONS,
      body: {
        type: 'string',
        required: true,
        doc: 'Cell source code.',
      },
      run: (data) => runSyncDirective('marimo', data),
    },
    {
      name: 'marimo-config',
      doc: 'Configure marimo execution for the current page.',
      options: MARIMO_CONFIG_OPTIONS,
      body: {
        type: 'string',
        required: false,
        doc: 'TOML script metadata when the pyproject option is set.',
      },
      run: (data) => runSyncDirective('marimo-config', data),
    },
  ],
  transforms: [
    {
      name: 'marimo-islands',
      doc: 'Compile marimo cells and project them as hydrated islands.',
      stage: 'document',
      plugin: marimoTransform,
    },
  ],
};

export default plugin;
