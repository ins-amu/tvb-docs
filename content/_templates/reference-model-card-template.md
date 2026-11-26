---
bibliography:
  - ../../references.bib
---

# <Model Name>

The `<Model Name>` model is a `<1-2 sentence description of the neural mass/population model, its biological basis, and primary application (e.g., resting-state fMRI, epilepsy, evoked potentials)>`. This card documents the TVB implementation in `tvb.simulator.models.<ModelClass>`, providing the mathematical state equations, parameter boundaries, and coupling points.

## Model

The model describes `<N>` state variables representing `<population firing rates / membrane potentials / ion concentrations>`.

$$
\begin{aligned}
\dot{x}_0 &= f_0(x_0, x_1, \dots, \mu) + C_{\text{in}} \\
\dot{x}_1 &= f_1(x_0, x_1, \dots, \mu)
\end{aligned}
$$

where $\mu$ collects the intrinsic parameters and $C_{\text{in}}$ denotes the incoming network coupling from other regions.

### State variables

- $x_0$ (`<var_name_0>`) — Description of state variable 0 (e.g. population membrane potential, firing rate), unit $[mV]$ or $[Hz]$.
- $x_1$ (`<var_name_1>`) — Description of state variable 1 (e.g. recovery variable, inhibitory feedback), unit $[mV]$ or $[a.u.]$.

### Network coupling

- **Coupled variables (`cvar`):** The model declares `cvar = [0]` (or indices of state variables receiving network input).
- **Coupling input:** In `dfun`, the incoming network activity enters as `coupling[0, :]`, scaled by the global coupling factor and structural connectivity weights.
- **Local coupling:** Local diffusion across cortical surfaces enters through `local_coupling` when spatial smoothing is enabled.

## Parameters

| name | range | default | description |
|------|-------|---------|-------------|
| `param_a` | 0.0 – 2.0 | 1.0 | Primary excitability parameter or time scale $[ms^{-1}]$ |
| `param_b` | -5.0 – 5.0 | 0.0 | Shift or threshold potential $[mV]$ |
| `tau` | 1.0 – 100.0 | 10.0 | Characteristic membrane time constant $[ms]$ |

## Typical Dynamics

Describe the dynamical regimes accessible by the model under standard parameter regimes:
- **Resting state:** For `<param_a> < threshold`, the system exhibits a single stable fixed point.
- **Oscillatory regime:** Crossing a supercritical Hopf / saddle-node on invariant circle (SNIC) bifurcation leads to limit-cycle oscillations at `<frequency>` Hz.
- **Bistability / Excitability:** In the intermediate regime, perturbations evoke transient burst responses or state transitions.

## Interactive Phase Plane

Register the model in `content/_code/tvb_card_widgets.py` (`MODEL_CARD_SPECS["<model_key>"]`)
and embed it here using the `{phaseplane}` directive:

````markdown
```{phaseplane} <model_key>
```
````

## Paper Reference

- [@citationKey] — Author, A., & Author, B. (Year). Title of the seminal paper. *Journal Name*, Vol(Issue), Pages. DOI: [10.xxxx/xxxxx](https://doi.org/10.xxxx/xxxxx)

For full details on using this model in simulations, see [First simulation](../../tutorials/first-simulation.md) or explore the [Phase plane explanation](../../explanation/phase-plane-explanation.md).
