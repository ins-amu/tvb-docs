---
title: "The Virtual Brain: a first simulation"
subtitle: "A reusable introduction and hands-on tutorial"
---

# What is The Virtual Brain?

- An open-source ecosystem for whole-brain simulation
- Combines a structural connectome with regional dynamical models
- Produces simulated activity for comparison with brain recordings

::: notes
Introduce TVB as a way to ask how local neural dynamics and the brain's
anatomical network together shape activity. Simulated signals are model
predictions, not a direct measurement or a clinical diagnosis.
:::

# From anatomy to dynamics

- **Regions:** a parcellation of the brain
- **Connections:** weights and tract lengths from a structural connectome
- **Local model:** equations describing population activity in each region
- **Coupling:** signals exchanged over connections, with propagation delays

::: notes
The connectome can be a group template or derived from an individual's scans.
Weights and tract lengths are inputs, and their interpretation depends on how
the data were prepared. A neural mass model describes population-level
activity, rather than individual neurons.
:::

# Anatomy of a simulation

1. Choose connectivity and a local model.
2. Set coupling and an integrator.
3. Configure monitors and run the simulator.
4. Inspect the time series and compare with data.

::: notes
Explain the five building blocks: connectivity, model, coupling, integrator,
and monitors. The integrator advances the equations in time; monitors record
state variables or apply observation models. Parameter choices and numerical
time steps influence the result.
:::

# Hands-on: prepare

- Open the [first simulation in JupyterLite](https://ins-amu.github.io/tvb-docs/lite/lab/index.html?path=tutorials/first-simulation.ipynb).
- Or follow the [first simulation tutorial](https://ins-amu.github.io/tvb-docs/first-simulation).
- The example uses a 76-region connectome and `Generic2dOscillator`.

::: notes
Allow time for participants to open the notebook. The browser lab needs an
internet connection to load; alternatively use the installation guide and
the tutorial locally. The first run may take longer while the environment
starts. The tutorial contains the full executable code and plots.
:::

# Assemble the simulator

```python
sim = simulator.Simulator(
    model=oscillator,
    connectivity=white_matter,
    coupling=white_matter_coupling,
    integrator=heunint,
    monitors=(mon_raw, mon_tavg),
)
sim.configure()
```

::: notes
Walk through the corresponding cells in the tutorial, where these objects
are imported and configured. The example uses linear coupling and a
deterministic Heun integrator. The snippet illustrates assembly and depends
on the preceding tutorial cells; it is not a standalone script.
:::

# Run and observe

```python
for raw, tavg in sim(simulation_length=2 ** 10):
    # collect monitor batches when they are available
    ...
```

- Time is expressed in milliseconds.
- Raw and temporal-average monitors sample activity differently.
- Plot regional time series and compare their dynamics.

::: notes
Run the tutorial cells to collect time and data from each monitor and plot
them. This short run illustrates the workflow, not a validated research
result. Ask participants what changes when the temporal-average monitor
smooths the raw signal.
:::

# Try a controlled change

- Change one parameter or monitor in the notebook.
- Reconfigure and rerun the simulation.
- Compare the output with the original run.

::: notes
For example, vary the linear coupling strength while keeping the connectome,
model, integration step and simulation length fixed. Discuss transients,
numerical stability and why a short simulation alone cannot establish
agreement with empirical recordings.
:::

# Where to go next

- [TVB documentation](https://ins-amu.github.io/tvb-docs/)
- [Tutorials and examples](https://ins-amu.github.io/tvb-docs/index)
- [The Virtual Brain project](https://www.thevirtualbrain.org/)
- Cite: Sanz Leon et al., *Frontiers in Neuroinformatics* 7:10 (2013),
  [doi:10.3389/fninf.2013.00010](https://doi.org/10.3389/fninf.2013.00010).

::: notes
Point participants to the documentation for model choices, data preparation,
and more examples. Invite them to adapt the deck for their audience and
acknowledge the TVB project and the sources of any datasets used.
:::
