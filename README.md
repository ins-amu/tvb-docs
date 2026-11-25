---
bibliography:
  - content/references.bib
---
# The Virtual Brain documentation

The Virtual Brain (TVB) is an open-source platform for simulating whole-brain
dynamics. It combines a structural connectome (a map of the connections
between brain regions, either averaged across a group or based on an
individual's own brain scans) with neural mass models describing the activity
of each region. The resulting simulated brain activity can be compared with
real recordings such as EEG, MEG or fMRI [@sanzleon2013].

**New to TVB?** Read [What is TVB?](content/getting-started/what-is-tvb.md),
then follow [Installation](content/getting-started/installation.md) instructions and the
[Quickstart guide](content/getting-started/quickstart-guide.md).

## Navigating the documentation

% REVIEW: add links for API reference and Extended tutorials once those sections exist; confirm the final name of Extended tutorials.
| Section | Contents | Start with |
| --- | --- | --- |
| **Getting started** | What TVB is, how to install it, and a first simulation | [What is TVB?](content/getting-started/what-is-tvb.md) |
| **User guide** | How to build, run and analyse simulations: building blocks, preparing data, understanding output, parameter sweeps, inference, high-performance computing and high-resolution simulations | [Mathematical framework](content/user-guide/mathematical-framework.md) |
| **Model zoo** | Detailed explanations of the neural mass models available in TVB, and instructions how to add your own | [Introduction](content/model-zoo/intro.md) |
| **API reference** | Technical reference for TVB's code | TO ADD |
| **Extended tutorials** | Complete worked examples for specific research applications | TO ADD |

Look up unfamiliar terms in the [Glossary](content/glossary.md). Information
on contributing to these docs is in

The code examples in these docs are run every time the site is built, so they
stay working as TVB changes.

% REVIEW: decide whether JupyterLite stays part of the site and where to feature it. These links only work in the full (CI) build, not in a local preview.
:::{tip} Try TVB in your browser
You can run simulations here without installing anything:
[open JupyterLite Lab](/lite/lab/index.html), or go straight to
[your first simulation](/lite/lab/index.html?path=tutorials/first-simulation.ipynb).
:::