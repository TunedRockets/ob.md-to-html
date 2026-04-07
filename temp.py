import re
import matplotlib.pyplot as plt
import numpy as np

points = np.array([
    [36, 49],
    [29,62],
    [42,47],
    [29,36],
    [69,29],
    [31,62],
    [42,38],
    [33,62],
    [33,44],
    [13,78],
    [42,29]
]).T

plt.scatter(*points)
plt.xlim(0,100)
plt.ylim(0,100)
plt.grid()
plt.xlabel("German")
plt.ylabel("Autistic")
plt.show()