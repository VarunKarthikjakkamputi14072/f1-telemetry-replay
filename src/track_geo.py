"""
Track geometry utilities — inner/outer boundaries, normals, rotation.
"""
import numpy as np
import math


def compute_circuit_rotation(drivers_data):
    """Use PCA on the longest driver's XY path to find the dominant axis
    and return a rotation angle (radians) that orients the track so the
    longest extent runs left-to-right."""
    best_df = None
    best_len = 0
    for df in drivers_data.values():
        if len(df) > best_len:
            best_df = df
            best_len = len(df)
    if best_df is None or len(best_df) < 10:
        return 0.0

    xs = best_df["X"].values
    ys = best_df["Y"].values
    cx, cy = np.mean(xs), np.mean(ys)
    dx, dy = xs - cx, ys - cy
    cov = np.array([[np.dot(dx, dx), np.dot(dx, dy)],
                     [np.dot(dy, dx), np.dot(dy, dy)]]) / len(dx)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # Dominant eigenvector (largest eigenvalue)
    principal = eigvecs[:, np.argmax(eigvals)]
    angle = math.atan2(principal[1], principal[0])
    return -angle


def compute_track_normals(points):
    """Compute unit perpendicular normals at each point of a polyline.

    Returns array of (nx, ny) pairs, one per point.  Normals point to the
    'left' of the travel direction.
    """
    n = len(points)
    if n < 2:
        return np.zeros((n, 2))

    pts = np.array(points, dtype=float)
    normals = np.zeros((n, 2))

    for i in range(n):
        if i == 0:
            dx, dy = pts[1] - pts[0]
        elif i == n - 1:
            dx, dy = pts[-1] - pts[-2]
        else:
            dx, dy = pts[i + 1] - pts[i - 1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        # Perpendicular (left-hand normal)
        normals[i] = (-dy / length, dx / length)

    return normals


def offset_polyline(points, normals, distance):
    """Offset a polyline by *distance* along its normals."""
    pts = np.array(points, dtype=float)
    norms = np.array(normals, dtype=float)
    return (pts + norms * distance).astype(int).tolist()


def build_track_edges(screen_points, track_half_width=7):
    """Given the center-line screen points, return (inner, outer) polylines."""
    normals = compute_track_normals(screen_points)
    inner = offset_polyline(screen_points, normals, -track_half_width)
    outer = offset_polyline(screen_points, normals, track_half_width)
    return inner, outer, normals


def rotate_point(x, y, cx, cy, cos_a, sin_a):
    """Rotate (x, y) around (cx, cy) by pre-computed cos/sin."""
    dx, dy = x - cx, y - cy
    return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a


def label_offset_from_normal(normal, base_offset=35):
    """Return (dx, dy) for a driver label positioned along the track normal."""
    nx, ny = normal
    length = math.hypot(nx, ny)
    if length < 1e-6:
        return (12, -12)
    return (int(nx / length * base_offset), int(ny / length * base_offset))
