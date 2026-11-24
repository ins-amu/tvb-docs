---
title: Installation
date: 2026-11-24
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../references.bib
---

# Installation

:::{note} Last verified
November 2026, on macOS with Python 3.12. If something here doesn't work,
please [open an issue](https://github.com/ins-amu/tvb-docs/issues).
:::

The simulation engine is the `tvb-library` package, installable from PyPI
(see [tvb-library on PyPI](https://pypi.org/project/tvb-library/) for the
current release and details). We recommend installing it into its own
environment. You need Python 3.10 or newer; other dependencies are installed
automatically.

## Installation via pip

```bash
python3 -m venv tvb-env
source tvb-env/bin/activate          # Windows: tvb-env\Scripts\activate
python -m pip install tvb-library tvb-data matplotlib
```

`tvb-data` contains the sample datasets, including the default connectivity
used throughout these docs. They can also be downloaded from
[Zenodo](https://zenodo.org/record/14992335).

## Installation via conda/mamba

If you use conda or mamba, create an environment with it and install TVB with
pip inside it:

```bash
conda create -n tvb python=3.12
conda activate tvb
python -m pip install tvb-library tvb-data matplotlib
```

## Installation from source

% REVIEW(2027-05): is the PyPI release still older than the GitHub version? If not, shorten this section.
Some newer examples on this site need a more recent `tvb-library` than the
PyPI release. To install the latest version directly from the source on
GitHub (requires `git`):

```bash
python -m pip install "tvb-library @ git+https://github.com/the-virtual-brain/tvb-root.git#subdirectory=tvb_library"
```

If you want to modify TVB itself, clone the repository and install the library
from its `tvb_library` subfolder in editable mode:

```bash
git clone https://github.com/the-virtual-brain/tvb-root.git
cd tvb-root/tvb_library
python -m pip install -e .
```

## Check your installation

Start Python in your environment and run:

```{code-cell} ipython3
:tags: [remove-stderr]
import tvb.simulator.lab
from importlib.metadata import version

version("tvb-library")
```

If this prints a version number without errors, TVB is installed correctly.

## Troubleshooting

| Problem | Fix |
|---|---|
| `pip: command not found` | Use `python3 -m pip` instead of `pip`. |
| `externally-managed-environment` | Create and activate a virtual environment first (see above). |
| An example fails with an import or attribute error | Install from source (see above). |
| Dependency conflicts | Start from a fresh environment. In conda, don't install the same package with both `conda` and `pip`. |
| Warning: `Geodesic distance module is unavailable` | Harmless unless you work with cortical surfaces. To enable those features, run `python -m pip install tvb-gdist` (if that fails to build, add `--no-build-isolation`). |

## Next steps

Continue with the [](quickstart-guide.md) to run your first simulation.