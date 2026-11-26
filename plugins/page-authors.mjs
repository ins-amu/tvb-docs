// Append an alphabetical, bottom-of-page contributor credit line from _build/contributors/contributors.json.
import { existsSync, readFileSync } from 'node:fs';
import { relative, resolve } from 'node:path';

const repoRoot = resolve('.');
const dataPath = resolve('_build/contributors/contributors.json');
const generatedApiDir = resolve('content/reference/api');
const generatedApiIndex = resolve('content/reference/api/index.md');
const contributorsPage = resolve('content/about/contributors.md');

let cachedData;
function loadContributorsData() {
  if (cachedData !== undefined) return cachedData;
  if (!existsSync(dataPath)) {
    cachedData = null;
    return cachedData;
  }
  try {
    cachedData = JSON.parse(readFileSync(dataPath, 'utf8'));
  } catch {
    cachedData = null;
  }
  return cachedData;
}

function pageAuthorsTransform() {
  return (tree, file) => {
    const data = loadContributorsData();
    if (!data?.pages || !file?.path || !Array.isArray(tree?.children)) return;

    const absPath = resolve(file.path);
    if (absPath === contributorsPage) return;
    if (absPath.startsWith(`${generatedApiDir}/`) && absPath !== generatedApiIndex) return;

    const relPath = relative(repoRoot, absPath).replaceAll('\\', '/');
    const page = data.pages[relPath];
    if (!page?.contributors?.length) return;

    const inlineChildren = [
      { type: 'strong', children: [{ type: 'text', value: 'Contributors: ' }] },
    ];

    page.contributors.forEach((contributor, index) => {
      if (index > 0) {
        inlineChildren.push({ type: 'text', value: ' · ' });
      }
      const targetId = `contributor-${contributor.id}`;
      inlineChildren.push({
        type: 'crossReference',
        identifier: targetId,
        label: targetId,
        children: [{ type: 'text', value: contributor.name }],
      });
    });

    if (page.last_updated) {
      inlineChildren.push({ type: 'text', value: ' · ' });
      inlineChildren.push({
        type: 'emphasis',
        children: [{ type: 'text', value: `Last updated ${page.last_updated}` }],
      });
    }

    tree.children.push(
      { type: 'thematicBreak' },
      { type: 'paragraph', children: inlineChildren },
    );
  };
}

const plugin = {
  name: 'TVB page authors',
  transforms: [{ name: 'tvb-page-authors', stage: 'document', plugin: pageAuthorsTransform }],
};

export default plugin;
