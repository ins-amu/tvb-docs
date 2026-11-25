# Python API Reference

This section documents the public Python API of **`tvb` (`tvb-library`)**, generated statically from source docstrings, type annotations, and `neotraits` descriptors.

- **Quick jump (`Ctrl+Shift+K` / `Cmd+Shift+K`)**: Open the client-side fuzzy symbol palette to jump directly to any module, class, trait, method, or function (supports camelCase/subsequence queries like `g2do` or `osc.dfun` and kind prefixes like `class:`, `mod:`, `fn:`, `trait:`).
- **Cross-references**: Authors can link to any documented symbol from prose using `{py}` — for example {py}`tvb.simulator.models.Generic2dOscillator` or short unambiguous names like {py}`Generic2dOscillator` and {py}`Connectivity`.

## Package Structure

| Package | Focus |
| --- | --- |
| [`tvb`](tvb.md) | Top-level `tvb-library` package index |
| [`tvb.simulator`](tvb.simulator.md) | Whole-brain simulator, neural mass models, coupling, integrators, noise, and monitors |
| [`tvb.datatypes`](tvb.datatypes.md) | Connectivity, surfaces, equations, patterns, sensors, and time series |
| [`tvb.analyzers`](tvb.analyzers.md) | BOLD balloon model, coherence, PCA/ICA, wavelets, and graph metrics |
| [`tvb.basic`](tvb.basic.md) | `neotraits` declarative attributes, profiles, readers, and logging |
