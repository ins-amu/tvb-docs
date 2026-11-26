// MyST directive plugin for embedding Trajecturtle phase-plane cards.
// Usage in Markdown:
//   ```{phaseplane} suphopf
//   ```

const phaseplaneDirective = {
  name: 'phaseplane',
  doc: 'Embed an interactive Trajecturtle phase-plane widget for a registered TVB model card.',
  arg: {
    type: String,
    required: true,
    doc: 'Model key in content/_code/tvb_card_widgets.py (e.g. suphopf).',
  },
  run(data) {
    const key = String(data.arg || '').trim();
    if (!/^[a-z0-9_]+$/.test(key)) {
      throw new Error(`Invalid phaseplane model key: ${key}`);
    }
    return [
      {
        type: 'html',
        value: `<div class="ppw-card-host ppw-card-key-${key}"></div>`,
      },
    ];
  },
};

const plugin = {
  name: 'TVB phaseplane directive',
  directives: [phaseplaneDirective],
};

export default plugin;
