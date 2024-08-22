import pickle

import hoomd

import msibi


class MSIBI(object):
    """Management class for orchestrating an MSIBI optimization.

    Notes
    -----
    This package is very object oriented. This class should be
    created first, followed by at least one `msibi.state.State`
    instance and at least one `msibi.forces.Force` instance.

    Then, use the methods `MSIBI.add_state()` and `MSIBI.add_force()`
    before beginning the optimization runs using `MSIBI.run_optimization()`.

    Parameters
    ----------
    nlist : hoomd.md.nlist.NeighborList, required
        The type of Hoomd neighbor list to use.
    integrator_method : hoomd.md.methods.Method, required
        The integrator method to use in the query simulation.
        The only supported options are ConstantVolume or ConstantPressure.
    integrator_kwargs : dict, required
        The arguments and their values required by the integrator chosen
    thermostat : hoomd.md.methods.thermostat.Thermostat, required
        The thermostat to be paired with the integrator method.
    thermostat_kwargs : dict, required
        The arguments and their values required by the thermostat chosen.
    dt : float, required
        The time step delta
    gsd_period : int, required
        The number of frames between snapshots written to query.gsd
    n_steps : int, required
        How many steps to run the query simulations
    nlist_exclusions : list of str, optional, default ["1-2", "1-3"]
        Sets the pair exclusions used during the optimization simulations
    seed : int, optional, default 42
        Random seed to use during the simulation
    """

    def __init__(
        self,
        nlist: hoomd.md.nlist.NeighborList,
        integrator_method: hoomd.md.methods.Method,
        thermostat: hoomd.md.methods.thermostats.Thermostat,
        method_kwargs: dict,
        thermostat_kwargs: dict,
        dt: float,
        gsd_period: int,
        nlist_exclusions: list[str] = ["bond", "angle"],
        seed: int = 42,
    ):
        if integrator_method not in [
            hoomd.md.methods.ConstantVolume,
            hoomd.md.methods.ConstantPressure,
        ]:
            raise ValueError(
                "MSIBI is only compatible with NVT "
                "(hoomd.md.methods.ConstantVolume), or NPT "
                "(hoomd.md.methods.ConstantPressure)"
            )
        self.nlist = nlist
        self.integrator_method = integrator_method
        self.thermostat = thermostat
        self.method_kwargs = method_kwargs
        self.thermostat_kwargs = thermostat_kwargs
        self.dt = dt
        self.gsd_period = gsd_period
        self.seed = seed
        self.nlist_exclusions = nlist_exclusions
        self.n_iterations = 0
        self.states = []
        self.forces = []
        self._optimize_forces = []

    def add_state(self, state: msibi.state.State) -> None:
        """Add a state point to MSIBI.states.

        Parameters
        ----------
        state : msibi.state.State, required
            Instance of msibi.state.State

        Notes
        -----
        At least 1 state point must be added before optimization can occur.
        """
        # TODO: Do we still need the ._opt attr?
        state._opt = self
        self.states.append(state)

    def add_force(self, force: msibi.forces.Force) -> None:
        """Add a force to be included in the query simulations.

        Parameters
        ----------
        force : msibi.forces.Force, required
            Instance of msibi.forces.Force

        Notes
        -----
        Only one type of force can be optimized at a time.
        Forces not set to be optimized are held fixed during query simulations.
        """
        self.forces.append(force)
        if force.optimize:
            self._add_optimize_force(force)
        for state in self.states:
            force._add_state(state)

    @property
    def bonds(self) -> list:
        """All instances of msibi.forces.Bond that have been added."""
        return [f for f in self.forces if isinstance(f, msibi.forces.Bond)]

    @property
    def angles(self) -> list:
        """All instances of msibi.forces.Angle that have been added."""
        return [f for f in self.forces if isinstance(f, msibi.forces.Angle)]

    @property
    def pairs(self) -> list:
        """All instances of msibi.forces.Pair that have been added."""
        return [f for f in self.forces if isinstance(f, msibi.forces.Pair)]

    @property
    def dihedrals(self) -> list:
        """All instances of msibi.forces.Dihedral that have been added."""
        return [f for f in self.forces if isinstance(f, msibi.forces.Dihedral)]

    def _add_optimize_force(self, force: msibi.forces.Force) -> None:
        """Check that all forces to be optimized are the same type."""
        if not all(
            [isinstance(force, f.__class__) for f in self._optimize_forces]
        ):
            raise RuntimeError(
                "Only one type of force (i.e. Bonds, Angles, Pairs, etc) "
                "can be set to optimize at a time."
            )
        self._optimize_forces.append(force)

    def run_optimization(
        self,
        n_steps: int,
        n_iterations: int,
        backup_trajectories: bool = False,
        _dir=None,
    ) -> None:
        """Runs query simulations and performs MSIBI
        on the potentials set to be optimized.

        Parameters
        ----------
        n_steps : int, required
            Number of simulation steps during each iteration.
        n_iterations : int, required
            Number of MSIBI update iterations.
        backup_trajectories : bool, optional default False
            If True, copies of the query simulation trajectories
            are saved in their respective msibi.state.State directory.
        """
        for n in range(n_iterations):
            print(f"---Optimization: {n+1} of {n_iterations}---")
            forces = self._build_force_objects()
            for state in self.states:
                state._run_simulation(
                    n_steps=n_steps,
                    forces=forces,
                    integrator_method=self.integrator_method,
                    method_kwargs=self.method_kwargs,
                    thermostat=self.thermostat,
                    thermostat_kwargs=self.thermostat_kwargs,
                    dt=self.dt,
                    seed=self.seed,
                    iteration=self.n_iterations,
                    gsd_period=self.gsd_period,
                    backup_trajectories=backup_trajectories,
                )
            self._update_potentials()
            self.n_iterations += 1

    def pickle_forces(self, file_path: str) -> None:
        """Save the Hoomd objects for all forces to a single pickle file.

        Parameters
        ----------
        file_path : str, required
            The path and file name for the pickle file.

        Notes
        -----
        Use this method as a convienent way to save and use the final
        set of forces in your own Hoomd-Blue script.
        """
        forces = self._build_force_objects()
        if len(forces) == 0:
            raise RuntimeError(
                "No forces have been created yet. See MSIBI.add_force()"
            )
        f = open(file_path, "wb")
        pickle.dump(forces, f)

    def _build_force_objects(self) -> list:
        """Creates force objects for query simulations."""
        # Create pair objects
        pair_force = None
        for pair in self.pairs:
            if not pair_force:  # Only create hoomd.md.pair obj once
                pair_force = hoomd.md.pair.Table(
                    nlist=self.nlist(
                        buffer=0.4,
                        exclusions=self.nlist_exclusions,
                        default_r_cut=0,
                    )
                )
            pair_force.params[pair._pair_name] = pair._table_entry()
            pair_force.r_cut[pair._pair_name] = pair.r_cut

        # Create bond objects
        bond_force = None
        for bond in self.bonds:
            if not bond_force:
                hoomd_bond_force = getattr(hoomd.md.bond, bond.force_init)
                if bond.force_init == "Table":
                    bond_force = hoomd_bond_force(width=bond.nbins + 1)
                else:
                    bond_force = hoomd_bond_force()
            if bond.format == "table":
                bond_force.params[bond.name] = bond._table_entry()
            else:
                bond_force.params[bond.name] = bond.force_entry

        # Create angle objects
        angle_force = None
        for angle in self.angles:
            if not angle_force:
                hoomd_angle_force = getattr(hoomd.md.angle, angle.force_init)
                if angle.force_init == "Table":
                    angle_force = hoomd_angle_force(width=angle.nbins + 1)
                else:
                    angle_force = hoomd_angle_force()
            if angle.format == "table":
                angle_force.params[angle.name] = angle._table_entry()
            else:
                angle_force.params[angle.name] = angle.force_entry
        # Create dihedral objects
        dihedral_force = None
        for dih in self.dihedrals:
            if not dihedral_force:
                hoomd_dihedral_force = getattr(
                    hoomd.md.dihedral, dih.force_init
                )
                if dih.force_init == "Table":
                    dihedral_force = hoomd_dihedral_force(width=dih.nbins + 1)
                else:
                    dihedral_force = hoomd_dihedral_force()
            if dih.format == "table":
                dihedral_force.params[dih.name] = dih._table_entry()
            else:
                dihedral_force.params[dih.name] = dih.force_entry
        forces = [pair_force, bond_force, angle_force, dihedral_force]
        return [f for f in forces if f]  # Filter out any None values

    def _update_potentials(self) -> None:
        """Update the potentials for the potentials to be optimized."""
        for force in self._optimize_forces:
            self._recompute_distribution(force)
            force._update_potential()

    def _recompute_distribution(self, force: msibi.forces.Force) -> None:
        """Recompute the current distribution of bond lengths or angles."""
        for state in self.states:
            force._compute_current_distribution(state)
            force._save_current_distribution(state, iteration=self.n_iterations)
            print(
                "Force: {0}, State: {1}, Iteration: {2}: {3:f}".format(
                    force.name,
                    state.name,
                    self.n_iterations,
                    force._states[state]["f_fit"][self.n_iterations],
                )
            )
            print()
