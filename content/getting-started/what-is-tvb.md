---
title: What is TVB?
bibliography:
  - ../references.bib
---

# What is TVB?

The Virtual Brain (TVB) is an open-source ecosystem for whole-brain modeling. It represents the brain as a network of regions, each described by a neural mass model: a low-dimensional set of equations capturing the collective activity of a large population of neurons. Regions are linked according to structural connectivity data. Simulating how activity evolves across this network produces signals that can be compared with measured brain activity, such as sEEG, EEG, MEG or fMRI recordings.

## How a simulation works

The main components of a TVB simulation are:

1. **Connectivity:** the structural connectome, a network of brain regions
   with the strength and length of the fibre tracts between them, usually
   derived from diffusion MRI. This can be a group-averaged (template)
   connectome, such as TVB's default dataset, or a personalised connectome
   built from an individual's own brain scans.
   See [Connectivity](../user-guide/bb-connectivity.md) and
   [Preparing data](../user-guide/data/requirements.md).
2. **Model:** the neural mass model describing the activity of each region
   (for example Wilson–Cowan or Jansen–Rit).
   See [Model](../user-guide/bb-model.md) and the
   [Model zoo](../model-zoo/intro.md).
3. **Coupling:** how activity from connected regions is combined into each
   region's input. See [Coupling](../user-guide/bb-coupling.md).
4. **Monitors:** turn the simulated activity into the signals you analyse,
   such as raw time series, or BOLD, EEG and MEG signals.
   See [Monitors](../user-guide/bb-monitors.md) and
   [Understanding output](../user-guide/outward/states-observables.md).

## Ways to use TVB

- **As a Python library:** the `tvb-library` package, which these docs
  focus on. You build and run simulations in scripts or notebooks. See
  [Installation](installation.md) and [Quickstart guide](quickstart-guide.md).

% REVIEW: decide how prominently to feature the TVB website and web interface.
- **Through the web interface:** TVB also has a graphical interface, available
  as a downloadable distribution from the
  [TVB website](https://www.thevirtualbrain.org). There, work is organised
  into projects: you can import data such as connectivity files, run
  simulations, share data between projects and users, and export results for
  analysis in Python, MATLAB or R.

% REVIEW: decide whether JupyterLite stays part of the site (keep consistent with the README). Link only works in the full (CI) build.
- **In your browser:** run simulations without installing anything, using
  [JupyterLite Lab](/lite/lab/index.html).

## Getting help

% REVIEW: link to the Community & contributing page once it exists.
For help, the user forum and ways to get involved, see Community &
contributing (TO ADD).

## Citing TVB

If you use TVB, please cite the following papers:

- [@sanzleon2013]
- [@schirner2022]

## Next steps

- [Installation](installation.md): install TVB on your computer.
- [Quickstart guide](quickstart-guide.md): run your first simulation.