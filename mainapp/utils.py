import numpy as np


def flatten_grid(grid):
    for line in grid:
        for coord in line:
            yield coord


def unique(list1):
    unique_list = list()
    for x in list1:
        if x not in unique_list:
            unique_list.append(x)
    return unique_list


def euclidean(x1, x2, y1, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)