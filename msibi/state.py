import os

import mdtraj as md


HOOMD_HEADER = """
from hoomd_script import *

system = init.read_xml(filename="{0}", wrap_coordinates=True)
T_final = {1:.1f}

pot_width = {2:d}
table = pair.table(width=pot_width)

"""
HOOMD_TABLE_ENTRY = """
table.set_from_file('{type1}', '{type2}', filename='{potential_file}')
"""

LAMMPS_TABLE_ENTRY = """
pair_style table linear 1500
pair_coeff 1 1 {potential_file} POT
"""

class State(object):
    """A single state used as part of a multistate optimization.

    Attributes
    ----------
    k : float
        Boltzmann's  constant in specified units.
    T : float
        Temperature in kelvin.
    traj : md.Trajectory
        The trajectory associated with this state.
    backup_trajectory : bool
        True if each query trajectory is backed up (default=False)

    """
    def __init__(self, k, T, state_dir='', traj_file=None, top_file=None,
                 name=None, backup_trajectory=False):
        self.kT = k * T
        self.state_dir = state_dir

        if not traj_file:
            self.traj_path = os.path.join(state_dir, 'query.dcd')
        else:
            self.traj_path = os.path.join(state_dir, traj_file)
        if top_file:
            self.top_path = os.path.join(state_dir, top_file)

        self.traj = None  # Will be set after first iteration.
        if not name:
            name = 'state-{0:.3f}'.format(self.kT)
        self.name = name

        self.backup_trajectory = backup_trajectory  # save trajectories?

    def reload_query_trajectory(self):
        """Reload the query trajectory. """
        if self.top_path:
            self.traj = md.load(self.traj_path, top=self.top_path)
        else:
            self.traj = md.load(self.traj_path)

    def save_runscript(self, table_potentials, table_width, engine='hoomd',
                       runscript='hoomd_run_template.py'):
        """Save the input script for the MD engine. """

        # TODO: Factor out for separate engines.

        if engine == 'hoomd':
            header = list()
            header.append(HOOMD_HEADER.format('start.xml', self.kT, table_width))
            for type1, type2, potential_file in table_potentials:
                header.append(HOOMD_TABLE_ENTRY.format(**locals()))
            header = ''.join(header)
            with open(os.path.join(self.state_dir, runscript)) as fh:
                body = ''.join(fh.readlines())

            runscript_file = os.path.join(self.state_dir, 'run.py')
            with open(runscript_file, 'w') as fh:
                fh.write(header)
                fh.write(body)

        elif engine == 'lammps':
            table_entry = list()
            for type1, type2, potential_file in table_potentials:
                table_entry.append(LAMMPS_TABLE_ENTRY.format(**locals()))
                table_entry = ''.join(table_entry)
            with open(os.path.join(self.state_dir, 'in.header')) as fh:
                header = ''.join(fh.readlines())
            with open(os.path.join(self.state_dir, 'in.tail')) as fh:
                tail = ''.join(fh.readlines())
            runscript_file = os.path.join(self.state_dir, 'in.run')
            with open(runscript_file, 'w') as fh:
                fh.write(header)
                fh.write(table_entry)
                fh.write(tail)
