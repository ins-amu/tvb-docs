---
bibliography:
  - ../../references.bib
---
# SupHopf (supercritical Hopf, Stuart–Landau)

The SupHopf model is the normal form of a supercritical Hopf bifurcation
[@kuznetsov2004], also known as the Stuart–Landau oscillator. It is the local node of
the whole-brain Hopf model of resting-state fMRI [@deco2017]. This card
documents the TVB implementation in `tvb.simulator.models.SupHopf`, providing
the state equations, parameter ranges and coupling points.

## Model

The model describes one oscillator in Cartesian coordinates; in complex form,
with $z = x + iy$, it is $\dot z = (a + i\omega - |z|^2)\,z$ plus inputs.

$$
\begin{aligned}
\dot{x} &= \big(a - x^{2} - y^{2}\big)\,x - \omega\,y + C_x + \lambda\,x \\
\dot{y} &= \big(a - x^{2} - y^{2}\big)\,y + \omega\,x + C_y
\end{aligned}
$$

where $a$ is the bifurcation parameter, $\omega$ the angular frequency,
$C_x, C_y$ the network coupling and $\lambda$ the local coupling. In polar
coordinates the uncoupled node is $\dot r = (a - r^2)\,r$, $\dot\theta = \omega$,
so the amplitude and the phase evolve independently. These are the equations
executed by `SupHopf.dfun`.

### State variables

- $x$ (`x`): real part of the oscillation; in the whole-brain Hopf model it
  stands for the region's BOLD signal [@deco2017] [a.u.].
- $y$ (`y`): imaginary (quadrature) part of the oscillation [a.u.].

### Network coupling

- **Coupled variables (`cvar`):** `cvar = [0, 1]`; both variables pass through
  the coupling function.
- **Coupling input:** `coupling[0]` enters $\dot x$ and `coupling[1]` enters
  $\dot y$. With `coupling.Difference`, as used by Deco et al., the input is
  $G\sum_j w_{ij}(x_j - x_i)$, which vanishes when all nodes are in the same
  state. With `coupling.Linear` it is $G\sum_j w_{ij}x_j$, which does not. In
  the absence of delays and noise, a network of nodes with $a < 0$ therefore
  stays at rest under `Difference` coupling for any $G$. Under `Linear`
  coupling it starts to oscillate once $G\,\lambda_{max}(W) > -a$, where
  $\lambda_{max}(W)$ is the largest eigenvalue of the weight matrix.
- **Local coupling:** $\lambda x$, in the $\dot x$ equation only.

## Parameters

| name | range | default | description |
|------|-------|---------|-------------|
| `a` | -10.0 – 10.0 | -0.5 | Bifurcation parameter |
| `omega` | 0.05 – 630.0 | 1.0 | Angular frequency [rad per unit of simulation time] |

Ranges are the trait domains declared in `tvb.simulator.models.SupHopf`;
defaults are the shipped `NArray` defaults. `variables_of_interest` defaults to
`("x",)`. The model has no intrinsic time scale. In TVB's millisecond
convention the default `omega = 1.0` is about 159 Hz, whereas Deco et al. work
in seconds with $\omega = 2\pi \times$ 0.04–0.07 Hz [@deco2017].

## Typical Dynamics

- **$a < 0$, rest:** the origin is stable, with eigenvalues $a \pm i\omega$.
  Perturbations spiral back at rate $\lvert a\rvert$. Driven by noise, the node
  fluctuates around $\omega/2\pi$, in a band that widens as $\lvert a\rvert$
  grows.
- **$a = 0$, criticality:** the amplitude decays algebraically,
  $r(t) = r_0/\sqrt{1 + 2r_0^2 t}$, so relaxation is very slow.
- **$a > 0$, oscillation:** a stable limit cycle of radius $\sqrt{a}$ and
  angular frequency $\omega$. Its amplitude grows continuously from zero at
  onset, with no hysteresis.
- **Whole-brain fits:** in Deco et al., the network fitted resting-state fMRI
  best with its nodes at the edge of the bifurcation. With the same $a$ for
  every node, the optimum was $a = 0$ and $G = 2.85$ [@deco2017].

The Hopf bifurcation, and the effect of the coupling function on a network's
resting state, are explained on the
[bifurcation analysis](../../explanation/bifurcation-analysis.md#coupling-and-network-rest)
page. Running the whole-brain model is covered in
[Simulate the Hopf whole-brain model](../../howtos/hopf-whole-brain-model.md).

## Interactive Phase Plane

```{phaseplane} suphopf
```

## Paper Reference

- [@deco2017] — Deco, G., Kringelbach, M. L., Jirsa, V. K., & Ritter, P. (2017). The dynamics of resting fluctuations in the brain: metastability and its dynamical cortical core. *Scientific Reports*, 7, 3095. DOI: [10.1038/s41598-017-03073-5](https://doi.org/10.1038/s41598-017-03073-5)
- [@kuznetsov2004] — Kuznetsov, Y. A. (2004). *Elements of Applied Bifurcation Theory* (3rd ed.). Springer, Applied Mathematical Sciences, 112. DOI: [10.1007/978-1-4757-3978-7](https://doi.org/10.1007/978-1-4757-3978-7)

See also the [Generic 2D oscillator](generic-2d-oscillator.md) card, the
[TVB demo notebook](../../demos/exploring_supHopf_model.ipynb), and the
[phase-plane explanation](../../explanation/phase-plane-explanation.md).
