from __future__ import print_function, division

from distutils.spawn import find_executable
import itertools
import logging
from math import ceil
from multiprocessing import cpu_count
from multiprocessing.dummy import Pool
import os
from subprocess import Popen

from msibi.utils.general import backup_file
from msibi.utils.exceptions import UnsupportedEngine

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')


def run_query_simulations(states, engine='hoomd'):
    """Run all query simulations for a single iteration. """

    # Gather hardware info.
    gpus = _get_gpu_info()
    if gpus is None:
        n_procs = cpu_count()
        gpus = []
        logging.info("Launching {n_procs} CPU threads...".format(**locals()))
    else:
        n_procs = len(gpus)
        logging.info("Launching {n_procs} GPU threads...".format(**locals()))

    if engine.lower() == 'hoomd':
        worker = _hoomd_worker
    if engine.lower() == 'lammps':
        worker = _lammps_worker
    else:
        raise UnsupportedEngine(engine)

    n_states = len(states)
    worker_args = zip(states, range(n_states), itertools.repeat(gpus))
    chunk_size = ceil(n_states / n_procs)

    pool = Pool(n_procs)
    pool.imap(worker, worker_args, chunk_size)
    pool.close()
    pool.join()
    for state in states:
        _post_query(state)

def _hoomd_worker(args):
    """Worker for managing a single HOOMD-blue simulation. """
    state, idx, gpus = args
    log_file = os.path.join(state.state_dir, 'log.txt')
    err_file = os.path.join(state.state_dir, 'err.txt')
    with open(log_file, 'w') as log, open(err_file, 'w') as err:
        if gpus:
            card = gpus[idx % len(gpus)]
            cmds = ['mpiexec', '-n', '1', 'hoomd', 'run.py', '--gpu={card}'.format(**locals())]
        else:
            logging.info('    Running state {state.name} on CPU'.format(**locals()))
            cmds = ['hoomd', 'run.py']

        proc = Popen(cmds, cwd=state.state_dir, stdout=log, stderr=err,
                     universal_newlines=True)
        logging.info("    Launched HOOMD in {state.state_dir}".format(**locals()))
        proc.communicate()
        logging.info("    Finished in {state.state_dir}.".format(**locals()))
    #_post_query(state)


def _lammps_worker(args):
    """Worker for managing a single LAMMPS simulation. """
    state, idx, gpus = args
    log_file = os.path.join(state.state_dir, 'log.txt')
    err_file = os.path.join(state.state_dir, 'err.txt')
    cmds = ['mpirun', '-n', '{}'.format(12+0*cpu_count()), 'lammps-31Mar17', '-i', 'in.run']
    with open(log_file, 'w') as log, open(err_file, 'w') as err:
        proc = Popen(cmds, cwd=state.state_dir, stdout=log, stderr=err,
                    universal_newlines=True)
        logging.info("    Launched LAMMPS in {state.state_dir}".format(**locals()))
        proc.communicate()
        logging.info("    Finished in {state.state_dir}.".format(**locals()))
    #_post_query(state)

def _post_query(state):
    """Reload the query trajectory and make backups. """

    state.reload_query_trajectory()
    backup_file(os.path.join(state.state_dir, 'log.txt'))
    backup_file(os.path.join(state.state_dir, 'err.txt'))
    if state.backup_trajectory:
        backup_file(state.traj_path)

def _get_gpu_info():
    """ """
    nvidia_smi = find_executable('nvidia-smi')
    if not nvidia_smi:
        return
    else:
        gpus = [line.split()[1].replace(':', '') for
                line in os.popen('nvidia-smi -L').readlines()]
        return gpus
