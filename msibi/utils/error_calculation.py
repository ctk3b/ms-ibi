import numpy as np


def calc_similarity(arr1, arr2):
    """F-fit score used in MSIBI paper."""
    f_fit = np.sum(np.absolute(arr1 - arr2))
    f_fit /= np.sum((np.absolute(arr1) + np.absolute(arr2)))
    return 1.0 - f_fit
