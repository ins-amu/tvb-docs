---
bibliography:
  - ../../references.bib
---
# FitzHugh–Nagumo

*Reference — model card and an interactive explorer.*

## Model

A FitzHugh–Nagumo neural mass with delayed network coupling `Cx`. In TVB, FitzHugh–Nagumo dynamics are canonically provided by `tvb.simulator.models.Generic2dOscillator` (see the [Generic 2D oscillator card](generic-2d-oscillator.md)); the formulation below and the interactive explorer match the implementation in `tvbl.core.DFun` used throughout the tutorial workflows:

```{math}
:label: fhn
\begin{aligned}
\frac{dX}{dt} &= \tau \left( X - \frac{X^3}{3} + Y \right) \\
\frac{dY}{dt} &= \frac{1}{\tau} \left( a - k\,C_x - X \right)
\end{aligned}
```

## Parameters

| Parameter | Meaning | Range | Default |
| --- | --- | --- | --- |
| `a` | external drive | 1.0 – 1.4 | 1.28 |
| `tau` | timescale ratio | 1.0 – 2.0 | 1.35 |
| `k` | coupling gain | `exp(-7)` – `exp(-3)` | `exp(-4.8)` |
| noise `z` | stochastic scale | `exp(-1)` – `exp(1)` | `exp(0.16)` |

## Interactive Phase Plane

Drag the sliders (`a`, `tau`) or click anywhere in the plane to launch a
trajectory. This matches {eq}`fhn` with `Cx = 0` directly in your browser.

```{phaseplane} fitzhugh_nagumo
```

The same model, coupled across a network, is simulated and inferred on the
[Tutorial](../tutorials/tvbl-quickstart.md) and [How-to](../howtos/tvbl-inference.md) pages.

## Paper Reference

Primary reference: [@fitzhugh1961; @nagumo1962].
