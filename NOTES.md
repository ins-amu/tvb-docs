Model is the implementation of mathematical equations that the model consists of.

state variables represent a vector, the placement of a given node in the multidimensional space defined by the model.
- each model sets `state_variables = (...)` (names) and `_nvar = N` by hand.
- state array shape in classic sim: `(nvar, n_nodes, n_modes)`; history adds a time axis.

variables of interest are the ones we care about
- `variables_of_interest`: names the monitors see. `Model.configure` builds `observe(state)` dynamically (exec'd code in `_build_observer`); returns only those variables.
- empty voi -> `observe` returns an empty array; monitors fall back to `numpy.r_[:len(model.variables_of_interest)]`, so an empty model voi records nothing.

cvar is the coupling variable (or variables if the coupling function calls for it)
- int array of **indices** into `state_variables` (not names). Classic sim: history is queried at cvar indices; coupling fun output is handed back to `dfun` in that order.
- hybrid: first axis of the coupling array the model receives is cvar **slots**, not state indices (`cvar = [1, 2]` -> slot 0 = state 1, slot 1 = state 2). See `cvar_utils.resolve_source_cvar / resolve_target_cvar`.

number of modes (1 unless specified otherwise by these models)
- only `ReducedSetFitzHughNagumo` and `ReducedSetHindmarshRose` (both in `models/stefanescu_jirsa.py`, via `ReducedSetBase`) set `number_of_modes = 3`. Everything else, incl. all WIP models, is 1. Same in WIP and main.

stvar: **stimulus variables** — indices of state variables that the classic Simulator writes the stimulus into (`simulator.py: _loop_update_stimulus`: `stimulus[self.model.stvar, :, :] = ...`). Stimulus then enters the state through the integrator (`scheme` adds `dt * stimulus`), NOT through `dfun`.
- defaults to `cvar.copy()` in `Model.configure` (test `test_stvar_init` in models_test.py).
- overridden by `KIonEx`, `InfiniteTheta`, plus `Dody` (WIP only) / `GastSollaKennedy` (main only) with `[1]`.
- hybrid: **stvar is unused**. Stimuli are `hybrid.stimulus.Stim` objects that write into coupling slots: `internal_c[stim.target_cvar] += ...`, so a stimulus must target a `cvar` slot, and `dfun` does see it (inside `total_c`), unlike classic.

state variable boundaries (are they respected?)
- yes, but enforced by the **integrator**, not the model. `Simulator.configure` -> `integrator.configure_boundaries(model)`; after each step `integration_bound_and_clamp` clamps the state to `[lo, hi]`; initial history is bounded too (`History.from_simulator`).
- only models that declare a `state_variable_boundaries` dict get clamped: ReducedWongWang(-ExcInh), Zerlaut 1st/2nd order, MontbrioPazoRoxin, KIonEx, CerebellarMF, CoombesByrne(+2D), DecoBalancedExcInh, DumontGutkin, Gast* (and GastSollaKennedy in main). `None`/±inf bounds are replaced by ±float64 max.
- clamping is *post-hoc* (state is clipped after the step), not a constraint inside dfun.
- hybrid: `Subnetwork.configure` calls `scheme.configure_boundaries(model)` (+ recompute for integrated vars) and `scheme.bound_and_clamp(nx)` after each step — same in WIP and main; main additionally re-aligns `clamped_state_variable_indices/values` (WIP subnetwork.py lacks that fix).

state variable mask
- boolean array over `state_variables` marking which are **integrated by the integrator** (True) vs **non-integrated/derived** (False). Built in `Model.configure` from `model.non_integrated_variables`; drives `nintvar`, `nnonintvar`, `has_nonint_vars`.
- non-integrated variables are updated by the model itself in `update_state_variables_before/after_integration` (see `Integrator.integrate_with_update`); boundaries/clamping are re-indexed to the integrated subset (`reconfigure_boundaries_and_clamping_for_integration_state_variables`).
- no stock model in main or WIP sets `non_integrated_variables` — the machinery was added for the cosimulation models (ReducedWongWangExcIO family with derived firing-rate vars `R, Rin, I`).

initial (verified)
- `Model.initial(dt, history_shape, rng)` draws each state variable **uniformly from `state_variable_range`** (which bounds ICs, separate from `boundaries`) over shape `(nt, nvar, nnode, nmode)`; `rng` = integrator noise stream when stochastic (`initial_for_simulator`).
- `History.from_simulator` calls it when no user ICs (or to pad short ones) and keeps only the last time slice as the initial state.
- hybrid: `Subnetwork.initial_state` calls `model.initial` directly (always `numpy.random`, ignores integrator noise stream).

dfun is where the equations live
- signature `dfun(x, coupling, local_coupling=0.0)`. Classic: stimulus never reaches dfun (added by the scheme). Hybrid: called as `dfun(x, total_c)` with `local_coupling=0.0` — local (surface) coupling is not supported in hybrid; stimuli are folded into `total_c`.

am I missing something? — other Model surface:
- `state_variable_range` (lo/hi per state var; ICs only), distinct from boundaries.
- parameter spatialization: `spatial_parameter_names` / `global_parameter_names`; `_spatialize_model_parameters` maps region params onto surfaces via `region_mapping` and reshapes `(nodes, 1)` for modes.
- `stationary_trajectory` (phase-plane tool), `update_derived_parameters` (e.g. ReducedSetFitzHughNagumo).
- WIP vs main model inventory: WIP adds `Dody` (stvar=[1]), main adds `GastSollaKennedy` (stvar=[1]); model-specific diffs: `KIonEx` dfun (main adds `J*r*(E-V)` term), `ZerlautAdaptationSecondOrder` TF cross-terms swapped, `CerebellarMF` default params (`external_input_ex` 1.8 vs 5.0 etc., main adds `external_input_in_ex`). `Model` base class itself is identical in both.
- WIP hybrid vs main hybrid: main adds `validate_target_cvar_indices` + routes inter-projections to the **state** cvar (`target.model.cvar[target_cvar]`), integer-multiple multirate dt + `cpp` backend (WIP: uniform dt, python/numba only).
