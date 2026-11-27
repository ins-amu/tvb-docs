// Inject the About-section mascot marker on pages under content/about/.
import { isAbsolute, relative, resolve } from 'node:path';

const aboutDir = resolve('content/about');

function isAboutPage(filePath) {
  if (!filePath) return false;
  const rel = relative(aboutDir, resolve(filePath));
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel);
}

function aboutThemeTransform() {
  return (tree, file) => {
    if (!Array.isArray(tree?.children) || !isAboutPage(file?.path)) return;
    tree.children.push({
      type: 'div',
      class: 'tvb-about-mascot',
      children: [],
    });
  };
}

const plugin = {
  name: 'TVB about section theme',
  transforms: [{ name: 'tvb-about-theme', stage: 'document', plugin: aboutThemeTransform }],
};

export default plugin;
