from __future__ import division

import logging
import os

import numpy as np

from msibi.potentials import tail_correction
from msibi.workers import run_query_simulations


class MSIBI(object):
    """Management class for orchestrating an MSIBI optimization.

    Parameters
    ----------
    rdf_cutoff : float
        The upper cutoff value for the RDF calculation.
    n_points : int
        The number of radius values.
    pot_cutoff : float, optional, default=rdf_cutoff
        The upper cutoff value for the potential.
    r_switch : float, optional, default=pot_r[-5]
        The radius after which a tail correction is applied.
    smooth_rdfs : bool, optional, default=False
        Use a smoothing function to reduce the noise in the RDF data.
    max_frames : int
        The maximum number of frames to include at once in RDF calculation

    Attributes
    ----------
    engine : str
        Simulation engine to run in.
    states : list of States
        All states to be used in the optimization procedure.
    pairs : list of Pairs
        All pairs to be used in the optimization procedure.
    n_iterations : int, optional, default=10
        The number of MSIBI iterations to perform.
    rdf_cutoff : float
        The upper cutoff value for the RDF calculation.
    n_rdf_points : int
        The number of radius values used in the RDF calculation.
    dr : float, default=rdf_cutoff / (n_points - 1)
        The spacing of radius values.
    pot_cutoff : float, optional, default=rdf_cutoff
        The upper cutoff value for the potential.
    pot_r : np.ndarray, shape=(int((rdf_cutoff + dr) / dr),)
        The radius values at which the potential is computed.
    r_switch : float, optional, default=pot_r[-1] - 5 * dr
        The radius after which a tail correction is applied.

    """

    def __init__(self, rdf_cutoff, n_rdf_points, pot_cutoff=None, r_switch=None,
                 smooth_rdfs=False, max_frames=1e3, engine='hoomd'):
        self.states = []
        self.pairs = []
        self.n_iterations = 10  # Can be overridden in optimize().
        self.max_frames = max_frames
        self.engine = engine.lower()

        self.rdf_cutoff = rdf_cutoff
        self.n_rdf_points = n_rdf_points
        if self.engine == 'hoomd':
            self.dr = rdf_cutoff / (n_rdf_points - 1)
            self.rdf_n_bins = self.n_rdf_points + 1
        if self.engine == 'lammps':
            self.dr = rdf_cutoff / (n_rdf_points - 1)
            self.rdf_n_bins = self.n_rdf_points + 1
        self.smooth_rdfs = smooth_rdfs
        self.rdf_r_range = np.array([0.0, self.rdf_cutoff + self.dr])
        #self.rdf_n_bins = self.n_rdf_points + 1

        # TODO: Description of use for pot vs rdf cutoff.
        if not pot_cutoff:
            pot_cutoff = rdf_cutoff
        self.pot_cutoff = pot_cutoff
        # TODO: Describe why potential needs to be messed with to match the RDF.
        if self.engine == 'hoomd': 
            self.pot_r = np.arange(0.0, self.pot_cutoff + self.dr, self.dr)
        elif self.engine == 'lammps': # LAMMPS starts potential files at dr, not 0
            self.pot_r = np.arange(self.dr, self.pot_cutoff + self.dr, self.dr)
        else:
            raise UnsupportedEngine(engine)

        if not r_switch:
            r_switch = self.pot_r[-5]
        self.r_switch = r_switch

    def optimize(self, states, pairs, n_iterations=10, start_iteration=0, engine='hoomd'):
        """
        """
        for pair in pairs:
            for state, data in pair.states.items():
                if len(data['target_rdf']) != self.n_rdf_points:
                    raise ValueError('Target RDF in {} of pair {} is not the '
                                     'same length as n_rdf_points; {} vs {}.'.format(
                        state.name, pair.name, len(data['target_rdf']), self.n_rdf_points))
        self.states = states
        self.pairs = pairs
        self.n_iterations = n_iterations
        self.initialize()

        for n in range(start_iteration + self.n_iterations):
            logging.info("-------- Iteration {n} --------".format(**locals()))
            run_query_simulations(self.states, engine=self.engine)
            self._update_potentials(n)

    def _update_potentials(self, iteration):
        """Update the potentials for each pair. """
        for pair in self.pairs:
            self._recompute_rdfs(pair, iteration)
            pair.update_potential(self.pot_r, self.r_switch)
            pair.save_table_potential(self.pot_r, self.dr, iteration=iteration,
                                      engine=self.engine)

    def _recompute_rdfs(self, pair, iteration):
        """Recompute the current RDFs for every state used for a given pair. """
        for state in pair.states:
            pair.compute_current_rdf(state, self.rdf_r_range,
                                     n_bins=self.rdf_n_bins,
                                     smooth=self.smooth_rdfs,
                                     max_frames=self.max_frames)
            pair.save_current_rdf(state, iteration=iteration, dr=self.dr)
            logging.info('pair {0}, state {1}, iteration {2}: {3:f}'.format(
                         pair.name, state.name, iteration,
                         pair.states[state]['f_fit'][iteration]))

    def initialize(self, potentials_dir=None):
        """Create initial table potentials and the simulation input scripts.

        Parameters
        ----------
        potentials_dir : path, optional, default="'working_dir'/potentials"

        """
        if not potentials_dir:
            self.potentials_dir = os.path.join(os.getcwd(), 'potentials')
        else:
            self.potentials_dir = potentials_dir
        if not os.path.isdir(self.potentials_dir):
            os.mkdir(self.potentials_dir)

        if not os.path.isdir('rdfs'):
            os.mkdir('rdfs')

        table_potentials = []
        for pair in self.pairs:
            potential_file = os.path.join(self.potentials_dir,
                                          'pot.{0}.txt'.format(pair.name))
            pair.potential_file = potential_file
            table_potentials.append((pair.type1, pair.type2, potential_file))

            V = tail_correction(self.pot_r, pair.potential, self.r_switch)
            pair.potential = V
            # This file is written for viewing of how the potential evolves.
            pair.save_table_potential(self.pot_r, self.dr, iteration=0,
                                      engine=self.engine)
            # This file is overwritten at each iteration and actually used for
            # performing the query simulations.
            pair.save_table_potential(self.pot_r, self.dr, engine=self.engine)

        for state in self.states:
            if self.engine == 'hoomd':
                state.save_runscript(table_potentials, table_width=len(self.pot_r),
                                    engine=self.engine)
            elif self.engine == 'lammps':
                state.save_runscript(table_potentials=table_potentials, table_width=0,
                                    engine=self.engine)
