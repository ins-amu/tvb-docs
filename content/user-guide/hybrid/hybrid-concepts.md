---
title: Conceptual model
bibliography:
  - ../../references.bib
---

# Conceptual Model

The TVB Hybrid Simulator extends classic region-based TVB by allowing different brain regions or subnetworks to obey distinct local equations, state dimensions, integration steps, and coupling pathways. This page outlines the conceptual motivation, core building blocks, architectural ownership, time-stepping mechanics, and partition equivalence criteria for hybrid simulations.

## Why hybrid simulation?

Classic TVB models large-scale brain dynamics by coupling identical local neural mass or neural field models across a structural connectome [@sanzleon2013]. While powerful and computationally efficient, classic TVB assumes uniform local equations across all network nodes. In practice, distinct brain subsystems—such as sensory cortex, deep cerebellar nuclei, thalamic relay circuits, or striatum—exhibit specialized cytoarchitecture, local connectivity, and population compositions [@jansenRit1995; @stefanescu2008].

Researchers generally approach large-scale brain heterogeneity along two distinct axes:
1. **Spatial parameter variation within a shared model family:** Keeping a single local model family (e.g., Wilson-Cowan or Kuramoto) while allowing parameters, external drives, or structural connectivity weights to vary continuously or regionally across the cortex.
2. **Heterogeneous multi-subnetwork modeling:** Assigning structurally distinct local model families (e.g., Jansen--Rit cortical columns versus reduced-set FitzHugh--Nagumo or thalamic population models) to distinct functional subnetworks.

The hybrid simulator provides a unified framework for the second approach. It allows neuroinformatics users to assemble multi-model architectures within a single simulation framework while preserving rigorous control over structural connectivity, delays, and state routing.

---

## Core building blocks and ownership seams

The hybrid architecture decomposes large-scale simulations into explicit hierarchical building blocks. Ownership is strictly stratified to prevent state corruption and race conditions:

- **`Simulator`:** The global master orchestrator. It owns the overall `NetworkSet` and any global `Monitor`s (e.g., `TemporalAverage`, `Bold`, `Raw`), and maintains the master integration clock $\Delta t_0 = \min_b \Delta t_b$.
- **`NetworkSet`:** The container owning the collection of `Subnetwork` instances and all `InterProjection`s that route activity between distinct subnetworks.
- **`Subnetwork`:** A homogeneous population block representing a subset of nodes (e.g., a cortical region or thalamic nucleus). A `Subnetwork` exclusively owns its local `model`, integration `scheme` (`Integrator`), internal `IntraProjection`s, optional `Stim`s, and local per-subnetwork `Recorder`s.
- **`IntraProjection`:** Encapsulates recurrent or internal structural connectivity and coupling computations *within* a single `Subnetwork`.
- **`InterProjection`:** Routes source state variables from one `Subnetwork` to target input slots in another `Subnetwork` across the `NetworkSet` boundary, applying sparse weights, tract lengths (conduction delays), coupling functions, and mode mappings (`mode_map`).
- **`Stim`:** Applied directly to designated subnetwork coupling slots or derivative state coordinates.
- **`Recorder`:** Local per-subnetwork data capture utility that records model observations directly before mode summation.

---

## Architecture diagram

The following C4-styled flowchart illustrates a concrete two-subnetwork topology (`cortex` running `JansenRit` and `thalamus` running `ReducedSetFitzHughNagumo`) orchestrated by a global `Simulator` and `NetworkSet`:

```{mermaid}
flowchart TB
    classDef simulator fill:#f5f5f5,stroke:#333,stroke-width:2px,color:#111;
    classDef netset fill:#e8f4f8,stroke:#2980b9,stroke-width:2px,color:#111;
    classDef subnet fill:#eafaf1,stroke:#27ae60,stroke-width:2px,color:#111;
    classDef component fill:#fff,stroke:#7f8c8d,stroke-width:1px,color:#111;

    subgraph Simulator ["Simulator (Master Clock Δt₀, Global Monitors)"]
        subgraph NetworkSet ["NetworkSet"]
            subgraph SubnetworkA ["Subnetwork A: cortex"]
                ModelA["Model: JansenRit (n=6, M=1)"]:::component
                SchemeA["Scheme: HeunDeterministic (dt_a)"]:::component
                IntraA["IntraProjection"]:::component
                StimA["Optional Stim"]:::component
                RecA["Local Recorder"]:::component
            end
            subgraph SubnetworkB ["Subnetwork B: thalamus"]
                ModelB["Model: ReducedSetFitzHughNagumo (n=4, M=3)"]:::component
                SchemeB["Scheme: HeunDeterministic (dt_b = k × dt_a)"]:::component
                IntraB["IntraProjection"]:::component
                RecB["Local Recorder"]:::component
            end
            InterProj["InterProjection (weights, delays, coupling, mode_map)<br/>y1 → xi"]:::component
        end
    end

    SubnetworkA -- "Source state y1" --> InterProj
    InterProj -- "Target input xi" --> SubnetworkB

    class Simulator simulator;
    class NetworkSet netset;
    class SubnetworkA,SubnetworkB subnet;
```

---

## Time stepping: Single-rate and multirate clocks

Hybrid simulations support two temporal execution modes:

1. **Synchronous Single-Rate Stepping:** All subnetworks share a common integration time step $\Delta t$. At every tick, states are integrated, inter- and intra-projection histories are updated, and global monitors record state snapshots.
2. **Integer-Multiple Multirate Stepping:** When subnetworks operate on disparate timescales (e.g., fast cortical spiking vs. slower metabolic or thalamic dynamics), subnetworks can declare integer-multiple time steps $\Delta t_b = \kappa_b \Delta t_0$, where $\Delta t_0 = \min_a \Delta t_a$ is the master clock interval.
   - **Due Ticks:** Subnetworks advance only on their designated due ticks ($t \bmod \kappa_b = 0$).
   - **Inter-Projection Interpolation:** 
     - *Zero-delay edges ($d = 0$):* Uses zero-order hold (clamped blend factor) to prevent future extrapolation.
     - *Delayed edges ($d \ge 1$):* Applies causal linear interpolation between consecutive committed source states across the source subnetwork's circular history ring.
   - **Monitors & Stimuli:** Global monitors and master-grid stimuli advance deterministically on the shared master $\Delta t_0$ clock grid.

---

## When does a hybrid partition match classic TVB?

A hybrid network partition reproduces classic TVB dynamics **in exact arithmetic** when:
- All subnetworks use the same local model family, parameters, integrators, initial states, and connectome blocks.
- Post-summation coupling $g$ is strictly **linear** ($g\left(\sum_p z_p\right) = \sum_p g(z_p)$).

If coupling functions are nonlinear or include affine intercepts, splitting a connectome into separate subnetworks alters the order of operations (summing before vs. after transformation), changing effective multi-subnetwork dynamics even when anatomical weights and delays are identical.

---

## Next steps

- Review [API contracts and pitfalls](hybrid-contracts.md) for strict matrix shapes, slot indexing conventions, and numerical precision notes.
- Explore [Backends and parameter sweeps](hybrid-backends-and-sweeps.md) for executing Numba and C++ accelerated simulations.
- Try out [Hands-on tutorials](hybrid-tutorials.md) for complete Python scripts implementing multi-model networks.
