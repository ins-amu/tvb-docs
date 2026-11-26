// Add native MyST term references to prose before cross-reference resolution.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const glossaryPath = resolve('content/glossary.md');
const generatedApiDir = resolve('content/reference/api');
const generatedContributorsPath = resolve('content/about/contributors.md');

// These words often have other meanings. Use an explicit {term} role
// when the glossary sense is intended.
const explicitOnly = new Set([
  'Backend', 'Criticality', 'Edge', 'Monitor', 'Node', 'Perturbation',
  'Posterior', 'Prior', 'Saddle', 'Stability', 'Stimulus', 'Trajectory', 'Transient',
]);

const aliases = {
  'Conduction speed': ['conduction velocity'],
  'Dynamic functional connectivity': ['dynamic FC', 'dFC'],
  'Excitation–inhibition balance': ['excitation-inhibition balance', 'E/I balance'],
  'Feedback inhibition control': ['FIC'],
  'Fixed point': ['equilibrium', 'equilibria'],
  'Functional connectivity': ['FC'],
  'Neural mass model': ['NMM', 'NMMs', 'neural mass', 'neural masses'],
  'Ordinary differential equation': ['ODE', 'ODEs'],
  'Power spectral density': ['PSD'],
  'Runge–Kutta method': ['Runge-Kutta method'],
  'SEEG': ['sEEG'],
  'Simulation-based inference': ['SBI'],
  'Stochastic differential equation': ['SDE', 'SDEs'],
  'Structural connectivity': ['SC'],
  'Weight normalisation': ['weight normalization'],
};

const skip = new Set([
  'abbreviation', 'cite', 'citeGroup', 'code', 'codeBlock', 'crossReference',
  'definitionTerm', 'heading', 'html', 'inlineCode', 'link', 'linkReference',
  'math', 'inlineMath', 'output', 'raw', 'subscript', 'superscript',
]);

const key = (text) => text.replace(/\s+/g, ' ').toLowerCase();

export function glossaryMatches() {
  const glossary = readFileSync(glossaryPath, 'utf8');
  const terms = Array.from(glossary.matchAll(/^([^\n]+)\n: (.+)$/gm), ([, term, definition]) => {
    const plain = definition.replace(/\{term\}`([^`]+)`/g, (_, body) => body.split(' <')[0]);
    if (plain.trim().split(/\s+/).length > 25) {
      throw new Error(`Glossary definition exceeds 25 words: ${term}`);
    }
    return term;
  });

  const spellings = new Map();
  for (const label of terms) {
    if (explicitOnly.has(label)) continue;
    const identifier = `term-${key(label)}`;
    const forms = [label, ...(aliases[label] ?? [])];
    if (/^[a-z -]+$/i.test(label) && !/[A-Z]{2}|s$/.test(label)) {
      forms.push(`${label}s`);
    }
    for (const form of forms) {
      const caseSensitive = /[a-z][A-Z]|[A-Z]{2}/.test(form);
      const id = key(form);
      const entry = spellings.get(id) ?? { identifier, label, forms: new Set(), caseSensitive };
      entry.forms.add(form);
      if (caseSensitive && /^[a-z]+ /.test(form)) {
        entry.forms.add(form[0].toUpperCase() + form.slice(1));
      }
      spellings.set(id, entry);
    }
  }

  const pattern = [...spellings.keys()]
    .sort((a, b) => b.length - a.length)
    .map((form) => form.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replaceAll(' ', '\\s+'))
    .join('|');
  const matches = new RegExp(`(?<![\\p{L}\\p{N}_])(?:${pattern})(?![\\p{L}\\p{N}_])`, 'giu');

  return function* (value) {
    for (const { 0: display, index } of value.matchAll(matches)) {
      const entry = spellings.get(key(display));
      if (entry.caseSensitive && !entry.forms.has(display.replace(/\s+/g, ' '))) continue;
      yield { display, index, identifier: entry.identifier, label: entry.label };
    }
  };
}

export function visitProse(node, onText, inProse = false) {
  if (!node.children || skip.has(node.type)) return;
  const prose = inProse || node.type === 'paragraph' || node.type === 'tableCell';
  node.children = node.children.flatMap((child) => {
    if (prose && child.type === 'text') return onText(child);
    visitProse(child, onText, prose);
    return [child];
  });
}

function termTransform() {
  const matches = glossaryMatches();

  function linkText(node) {
    const nodes = [];
    let offset = 0;
    for (const { display, index, identifier, label } of matches(node.value)) {
      if (index > offset) nodes.push({ type: 'text', value: node.value.slice(offset, index) });
      nodes.push({
        type: 'crossReference',
        identifier,
        label,
        children: [{ type: 'text', value: display }],
      });
      offset = index + display.length;
    }
    if (offset === 0) return [node];
    if (offset < node.value.length) nodes.push({ type: 'text', value: node.value.slice(offset) });
    return nodes;
  }

  return (tree, file) => {
    const filePath = file.path ? resolve(file.path) : '';
    if (
      filePath &&
      filePath !== glossaryPath &&
      filePath !== generatedContributorsPath &&
      !filePath.startsWith(`${generatedApiDir}/`)
    ) {
      visitProse(tree, linkText);
    }
  };
}

const plugin = {
  name: 'TVB glossary links',
  transforms: [{ name: 'tvb-glossary-links', stage: 'document', plugin: termTransform }],
};

export default plugin;
