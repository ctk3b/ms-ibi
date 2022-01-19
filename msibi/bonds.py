from cmeutils.structure import angle_distribution, bond_distribution
from msibi.utils.sorting import natural_sort


class Bond(object):
    def __init__(self, type1, type2, r_min, r_max):
        self.type1, self.type2 = sorted(
                    [type1, type2],
                    key=natural_sort
                )
        self.name = f"{self.type1}-{self.type2}"
        self.r_min = r_min
        self.r_max = r_max
        self._states = dict()
    
    def set_harmonic(self, k, r0):
        """
        """
        self.k = k
        self.r0 = r0
        self.bond_parms = {"k":self.k, "r0":self.r0}
        self.bond_type = "harmonic"
        self.script = ""
    
    def set_polynomial(self, r0, k_coeffs):
        """
        """
        self.bond_type = "polynomial"
        self.r0 = r0
        self.script = ""
        self.k_coeffs = {}
        for i in range(n_terms):
            self.k_coeffs[f"k{i}"] = 1

    def update_polynomail(self):



    def set_table(self, file=None, func=None):
        """
        """
        self.file = file
        self.bond_type = "table"
        self.script = ""

    def _add_state(self, state):
        target_distribution = self.get_distribution(state, query=False) 
        self._states[state] = {
                "target_distribution": target_distribution,
                "current_distribution": None,
                "alpha": state.alpha,
                "alpha_form": "linear",
                "f_fit": [],
                "path": state.dir
            }
        self._states[state].update(self.bond_params)

    def get_distribution(self, state, query=False):
        if query:
            traj = state.query_traj
        else:
            traj = state.traj_file
        bonds = bond_distribution(traj, self.type1, self.type2)  

    def compute_current_distribution(self, state):
        bond_distribution = self.get_distribution(state, query=False)
        self._states[state]["current_distribution"] = bond_distribution
        # TODO FINISH CALC SIM
        f_fit = calc_similarity()


class Angle(object):
    def __init__(self, type1, type2, type3, k, theta):
        self.type1 = type1
        self.type2 = type2
        self.type3 = type3
        self.name = f"{self.type1}-{self.type2}-{self.type3}"
        self.k = k
        self.theta = theta
        self._states = dict()

    def _add_state(self, state):
        self._states[state] = {
                "k": self.k,
                "theta": self.theta
            }
