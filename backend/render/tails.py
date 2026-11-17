"""Pointed bubble tails (``tailTip``), shared geometry.

Mirrored line for line by frontend/src/components/composer/tailGeometry.ts;
both are checked against backend/tests/fixtures/tail_cases.json, so change
the two together and regenerate the fixture.

The algorithm follows the Comics letterer (Comics lib/page.js): the tail
aims from the bubble centre at the tip; its root is two points on the
ellipse at ``atan2(...) ± TAIL_SPREAD``, pulled a little inside the body so
the body's fill hides the seam; the first edge bends slightly through the
midpoint between the ellipse boundary and the tip. Thought bubbles get three
shrinking circles instead. Shout uses the star's outer radius (the box) for
the direction and roots the tail inside the star's inner radius.

All coordinates are element-local pixels, unrotated: (0, 0) is the element
box's top-left, ``tip`` may lie outside the box.
"""
import math
from typing import List, Optional, Tuple

TAIL_SPREAD = 0.22          # half-angle of the tail root, radians
ROOT_K = 0.94               # root radius factor (inside the ellipse)
ROOT_K_SHOUT = 0.72         # inside the star's 0.78 inner radius
THOUGHT_R = (0.16, 0.11, 0.07)   # circle radii × min(rx, ry), base → tip
CURVE_STEPS = 12

Pt = Tuple[float, float]


def tail_geometry(bubble_type: str, w: float, h: float, tip: Pt,
                  inset: float) -> Optional[dict]:
    """Tail shape for a bubble of ``w × h`` whose body ellipse is inset by
    ``inset`` px, or None (narration, or a tip inside the body).

    ``{"kind": "wedge", "p1", "p2", "ctrl", "tip"}`` — path
    p1 →(quadratic via ctrl)→ tip → p2; or
    ``{"kind": "circles", "circles": [(x, y, r), ...]}``."""
    if bubble_type == "narration":
        return None
    cx, cy = w / 2, h / 2
    rx, ry = max(1.0, w / 2 - inset), max(1.0, h / 2 - inset)
    tx, ty = float(tip[0]), float(tip[1])
    nx, ny = (tx - cx) / rx, (ty - cy) / ry
    if nx * nx + ny * ny <= 1.0:
        return None
    t = math.atan2(ny, nx)
    bx, by = cx + rx * math.cos(t), cy + ry * math.sin(t)
    if bubble_type == "thought":
        s = min(rx, ry)
        circles = []
        for i, f in enumerate(THOUGHT_R, start=1):
            circles.append((bx + (tx - bx) * i / 3, by + (ty - by) * i / 3,
                            max(1.5, s * f)))
        return {"kind": "circles", "circles": circles}
    k = ROOT_K_SHOUT if bubble_type == "shout" else ROOT_K
    p1 = (cx + rx * k * math.cos(t - TAIL_SPREAD), cy + ry * k * math.sin(t - TAIL_SPREAD))
    p2 = (cx + rx * k * math.cos(t + TAIL_SPREAD), cy + ry * k * math.sin(t + TAIL_SPREAD))
    ctrl = (bx + (tx - bx) * 0.5, by + (ty - by) * 0.5)
    return {"kind": "wedge", "p1": p1, "p2": p2, "ctrl": ctrl, "tip": (tx, ty)}


def wedge_edge(g: dict, steps: int = CURVE_STEPS) -> List[Pt]:
    """The visible outline p1 → tip → p2 as a polyline (curve flattened)."""
    (x0, y0), (qx, qy), (x1, y1) = g["p1"], g["ctrl"], g["tip"]
    pts = []
    for i in range(steps + 1):
        u = i / steps
        a, b, c = (1 - u) ** 2, 2 * (1 - u) * u, u * u
        pts.append((a * x0 + b * qx + c * x1, a * y0 + b * qy + c * y1))
    pts.append(g["p2"])
    return pts


def tail_bounds(g: dict) -> Tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of everything the tail draws (before stroke)."""
    if g["kind"] == "circles":
        xs0 = [x - r for x, _, r in g["circles"]]
        xs1 = [x + r for x, _, r in g["circles"]]
        ys0 = [y - r for _, y, r in g["circles"]]
        ys1 = [y + r for _, y, r in g["circles"]]
        return min(xs0), min(ys0), max(xs1), max(ys1)
    pts = wedge_edge(g)
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))
