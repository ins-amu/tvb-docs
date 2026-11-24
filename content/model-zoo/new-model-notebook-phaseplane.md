---
title: Phase-Plane Notebook
bibliography:
  - ../references.bib
---

# Phase-Plane Notebook

To embed an interactive Trajecturtle (`tvb-phaseplane`) phase plane on a model card:

1. Add a `CardModelConfig` entry to `MODEL_CARD_SPECS` in `content/_code/tvb_card_widgets.py`
   using `ModelSpec.from_strings` with equations, state ranges, parameter domains, defaults,
   and optional `bounds` matching `tvb.simulator.models.<Class>.dfun`.
2. Add a `## Interactive Phase Plane` section to the model card with:

   ````markdown
   ```{phaseplane} <model_key>
   ```
   ````

3. Run `python make.py test` to verify `dfun` numerical parity (`rtol=1e-5, atol=1e-6`)
   and Nerdamer JS compilation, then `python make.py docs` to rebuild the site.
