---
bibliography:
  - ../../references.bib
---
# Jansen–Rit

The Jansen–Rit model is a neural mass model of a cortical column: pyramidal
cells with an excitatory and an inhibitory interneuron population, built to
generate alpha rhythms and visual evoked potentials in EEG [@jansenRit1995].
This card documents the TVB implementation in
`tvb.simulator.models.JansenRit`, providing the state equations, parameter
ranges and coupling points.

## Model

The model describes three post-synaptic potentials and their time
derivatives. Time is in ms and firing rates are in ms⁻¹, so `mu = 0.22` is 220
pulses/s.

$$
\begin{aligned}
\dot{y}_0 &= y_3 \\
\dot{y}_3 &= A\,a\,\mathcal{S}(y_1 - y_2) - 2a\,y_3 - a^2 y_0 \\
\dot{y}_1 &= y_4 \\
\dot{y}_4 &= A\,a\,\big(\mu + \alpha_2 J\,\mathcal{S}(\alpha_1 J\,y_0) + C_{\text{in}} + C_{\text{loc}}\big) - 2a\,y_4 - a^2 y_1 \\
\dot{y}_2 &= y_5 \\
\dot{y}_5 &= B\,b\,\alpha_4 J\,\mathcal{S}(\alpha_3 J\,y_0) - 2b\,y_5 - b^2 y_2 \\
\mathcal{S}(v) &= \frac{2\,\nu_{max}}{1 + e^{\,r\,(v_0 - v)}}
\end{aligned}
$$

Each pair of equations is a second-order synaptic filter with impulse response
$A\,a\,t\,e^{-at}$ (excitatory) or $B\,b\,t\,e^{-bt}$ (inhibitory). The
equations are those executed by `JansenRit.dfun`. Its docstrings contain two
transcription slips ($\alpha_2 J + S$ for $\alpha_2 J\,S$, and $2a^2y_0$ for
$a^2y_0$).

### State variables

- $y_0$ (`y0`): post-synaptic potential produced by pyramidal firing
  $\mathcal{S}(y_1 - y_2)$; the excitatory and inhibitory interneurons receive
  it scaled by $\alpha_1 J$ and $\alpha_3 J$ [mV].
- $y_1$ (`y1`): excitatory post-synaptic potential on the pyramidal cells, from
  the excitatory interneurons and the extrinsic input [mV].
- $y_2$ (`y2`): inhibitory post-synaptic potential on the pyramidal cells, from
  the inhibitory interneurons [mV].
- $y_3, y_4, y_5$ (`y3`, `y4`, `y5`): time derivatives of $y_0, y_1, y_2$
  [mV ms⁻¹].

The model's output is $y_1 - y_2$, the mean membrane potential of the
pyramidal cells, which is the EEG-like signal [@jansenRit1995; @grimbertFaugeras2006].
Monitors do not compute it. The default `variables_of_interest` are
`("y0", "y1", "y2", "y3")`, so form `y1 - y2` from their output.

### Network coupling

- **Coupled variables (`cvar`):** `cvar = [1, 2]`; the coupling function
  receives $y_1$ and $y_2$ of each source region.
- **Coupling input:** `coupling[0]` is $C_{\text{in}}$, added to $\mu$ in the
  $\dot y_4$ equation, so network input acts as extra extrinsic drive. The
  matching coupling function, `coupling.SigmoidalJansenRit`, sends
  $a_c \sum_j w_{ij}\,\mathcal{S}_c(y_{1j} - y_{2j})$, where $\mathcal{S}_c$
  is a sigmoid with its own parameters. Its defaults (`cmax = 0.005`,
  `r = 0.56`, `midpoint = 6.0`) reproduce the model's $\mathcal{S}$ only if
  the model uses `v0 = 6`.
- **Local coupling:** $C_{\text{loc}} = \texttt{local\_coupling}\,(y_1 - y_2)$.
- **Stimulus:** a spatiotemporal stimulus is added to the derivatives of the
  variables in `model.stvar`, which defaults to $y_1$ and $y_2$. The input $p$
  enters $\dot y_4$ with gain $A\,a$, so a stimulus meant as an input pulse
  needs `stvar = [4]` and an amplitude scaled by $A\,a$.

## Parameters

| name | range | default | description |
|------|-------|---------|-------------|
| `A` | 2.6 – 9.75 | 3.25 | Maximum EPSP amplitude [mV] |
| `B` | 17.6 – 110.0 | 22.0 | Maximum IPSP amplitude [mV] |
| `a` | 0.05 – 0.15 | 0.1 | Reciprocal excitatory time constant [ms⁻¹] |
| `b` | 0.025 – 0.075 | 0.05 | Reciprocal inhibitory time constant [ms⁻¹] |
| `v0` | 3.12 – 6.0 | 5.52 | Sigmoid threshold [mV]; Jansen & Rit used 6.0 |
| `nu_max` | 0.00125 – 0.00375 | 0.0025 | Half the maximum firing rate [ms⁻¹] |
| `r` | 0.28 – 0.84 | 0.56 | Sigmoid steepness [mV⁻¹] |
| `J` | 65.0 – 1350.0 | 135.0 | Average number of synapses between populations ($C$ in the paper) |
| `a_1` | 0.5 – 1.5 | 1.0 | Connectivity fraction, pyramidal → excitatory interneurons |
| `a_2` | 0.4 – 1.2 | 0.8 | Connectivity fraction, excitatory interneurons → pyramidal |
| `a_3` | 0.125 – 0.375 | 0.25 | Connectivity fraction, pyramidal → inhibitory interneurons |
| `a_4` | 0.125 – 0.375 | 0.25 | Connectivity fraction, inhibitory interneurons → pyramidal |
| `mu` | 0.0 – 0.22 | 0.22 | Constant extrinsic input $p$ [ms⁻¹] |
| `p_min` | 0.0 – 0.12 | 0.12 | Lower bound of the paper's input range [ms⁻¹]; not used by `dfun` |
| `p_max` | 0.0 – 0.32 | 0.32 | Upper bound of the paper's input range [ms⁻¹]; not used by `dfun` |

Ranges are the trait domains declared in `tvb.simulator.models.JansenRit`.
They are not enforced. Defaults are the shipped `NArray` defaults. Jansen & Rit
used `v0 = 6` [@jansenRit1995], and so does the TVB demo notebook. The TVB
default of 5.52 changes the dynamics, as described below.

## Typical Dynamics

With `v0 = 6`, the regimes depend on the constant input $p$ (`mu` × 1000, in
pulses/s). The list follows the bifurcation diagram of Grimbert & Faugeras
[@grimbertFaugeras2006]. TVB's implementation reproduces the Hopf and
saddle-node points they report.

- **Rest ($0 \le p < 89.83$):** two stable equilibria, a low one and a higher
  one. The higher one has a small basin of attraction, so trajectories
  usually settle on the low one.
- **Rest and alpha ($89.83 < p < 113.58$):** a Hopf bifurcation creates a
  ~10 Hz limit cycle that coexists with the resting state.
- **Spikes and alpha ($113.58 < p < 137.38$):** the low fixed point
  disappears in a saddle-node; slow, large spike-like cycles coexist with
  alpha.
- **Alpha ($137.38 < p < 315.70$):** the ~10 Hz cycle is the only attractor.
  At `mu = 0.22` its peak-to-peak swing in $y_1 - y_2$ is about 3 mV.
- **Damped alpha ($p > 315.70$):** a second Hopf bifurcation; the column rests
  and rings at ~11 Hz after perturbations.
- **Shipped defaults (`v0 = 5.52`, `mu = 0.22`):** a ~7 Hz limit cycle with
  a peak-to-peak swing of about 10 mV, not alpha.
- **Evoked response:** from rest, a brief input pulse produces a damped
  deflection of $y_1 - y_2$ that returns to baseline, which is the model's
  evoked potential.

The derivation of these regimes is on the
[bifurcation analysis](../../explanation/bifurcation-analysis.md#jansen-rit-diagram)
page. Keeping a coupled network inside them is covered in
[Keep a Jansen–Rit network in the alpha regime](../../howtos/jansen-rit-alpha-network.md).

## Interactive Phase Plane

The phase-plane widget covers two-variable models. Jansen–Rit has six state
variables, so it has no widget; the how-to guide above simulates its time
series instead.

## Paper Reference

- [@jansenRit1995] — Jansen, B. H., & Rit, V. G. (1995). Electroencephalogram and visual evoked potential generation in a mathematical model of coupled cortical columns. *Biological Cybernetics*, 73(4), 357–366. DOI: [10.1007/BF00199471](https://doi.org/10.1007/BF00199471)
- [@jansen1993] — Jansen, B. H., Zouridakis, G., & Brandt, M. E. (1993). A neurophysiologically-based mathematical model of flash visual evoked potentials. *Biological Cybernetics*, 68(3), 275–283. DOI: [10.1007/BF00224863](https://doi.org/10.1007/BF00224863)
- [@grimbertFaugeras2006] — Grimbert, F., & Faugeras, O. (2006). Bifurcation analysis of Jansen's neural mass model. *Neural Computation*, 18(12), 3052–3068. DOI: [10.1162/neco.2006.18.12.3052](https://doi.org/10.1162/neco.2006.18.12.3052)

See also the [Zetterberg–Jansen](zetterberg-jansen.md) and
[Wilson–Cowan](wilson-cowan.md) model cards, the
[TVB demo notebook](../../demos/simulate_region_jansen_rit.ipynb), and
[neural mass models](../../explanation/neural-mass-models.md).
