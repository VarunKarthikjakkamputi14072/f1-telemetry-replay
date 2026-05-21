import numpy as np

def dtw_distance(s, t, window=50):
    n, m = len(s), len(t)
    # create distance matrix
    dtw_matrix = np.full((n + 1, m + 1), np.inf)
    dtw_matrix[0, 0] = 0
    
    # Sakoe-Chiba band window adjustment
    w = max(window, abs(n - m))
    
    for i in range(1, n + 1):
        for j in range(max(1, i - w), min(m + 1, i + w + 1)):
            cost = abs(s[i - 1] - t[j - 1])
            dtw_matrix[i, j] = cost + min(
                dtw_matrix[i - 1, j],    # insertion
                dtw_matrix[i, j - 1],    # deletion
                dtw_matrix[i - 1, j - 1] # match
            )
            
    # Calculate path (backtracking)
    path = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        min_val = min(
            dtw_matrix[i - 1, j - 1],
            dtw_matrix[i - 1, j],
            dtw_matrix[i, j - 1]
        )
        if min_val == dtw_matrix[i - 1, j - 1]:
            i -= 1
            j -= 1
        elif min_val == dtw_matrix[i - 1, j]:
            i -= 1
        else:
            j -= 1
    path.append((0, 0))
    path.reverse()
    
    normalized_distance = dtw_matrix[n, m] / len(path)
    return normalized_distance, path
