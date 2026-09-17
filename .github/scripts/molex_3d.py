#!/usr/bin/env python3
"""Place and colour the TraceParts CLIK-Mate STEP models for APRL_Connector_Molex.

TraceParts ships these as one fused, colourless solid, in whatever orientation
the source CAD happened to use. For each model this:

  1. finds the rotation that puts the solder tails pointing down, by trying the
     axis-aligned rotations and fitting the tail cross-sections against the
     matching footprint's own pads (and peg holes, where it has them);
  2. moves it so pad 1 is at the footprint origin and the housing seats at z=0;
  3. splits housing from contacts -- contacts are the faces narrow in X that sit
     on a pad column -- and writes a two-colour .wrl for KiCad's 3D viewer;
  4. writes the placed geometry as a same-named .step, which KiCad substitutes
     for the .wrl on STEP export (kicad-cli pcb export step --subst-models);
  5. points the footprint at the .wrl with zero offset and rotation.

A model whose tails do not land within MAX_RESIDUAL of the footprint's pads is
refused, not written.

Run under FreeCAD (plain python segfaults in Part):

    freecadcmd tools/molex_3d.py <PN>.stp [more.stp ...]

Input files must be named by the 10-digit Molex order number, as TraceParts
names them.

Contacts: every interior contact resolves to the same face count, which is the
signal the split is right. The two end columns pick up about a dozen faces of
housing end-wall, so a little plastic at each end renders metallic; tightening
the tolerance to fix that starts eating real contact faces.
"""
import math, os, re, sys

import Part
from FreeCAD import Vector

# Repo root from this script, not from the input file -- the input is
# normally a download sitting outside the repo entirely.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "kicadlibs", "aprl", "APRL_Connector_Molex.pretty")
MODELS = os.path.join(ROOT, "kicadlibs", "models")

MAX_RESIDUAL = 0.20              # mm, tail or peg vs its pad
TAIL_PROBE = 0.40                # mm above the tail tips to slice
SEAT_AREA = 3.0                  # mm^2 cross-section that counts as housing
PIN_TOL = 0.35                   # face centre to pad column
PIN_MAX_WIDTH = 0.80             # contacts are much narrower than housing
VRML_SCALE = 1.0 / 2.54          # KiCad reads .wrl in 0.1 inch units

TIN = (0.78, 0.78, 0.80)
HOUSING = {"Black": (0.09, 0.09, 0.10), "Natural": (0.87, 0.81, 0.67)}

X, Y, Z = Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1)
# Rotations taking each of the six axis directions to -Z.
TO_DOWN = {"-Z": [], "+Z": [(X, 180)], "+X": [(Y, 90)], "-X": [(Y, -90)],
           "+Y": [(X, -90)], "-Y": [(X, 90)]}


def footprint(pn):
    for name in sorted(os.listdir(LIB)):
        path = os.path.join(LIB, name)
        text = open(path).read()
        if f"part-detail-pdf/{pn}" in text:
            return path, text
    raise SystemExit(f"{pn}: no footprint in {LIB}")


def pads(text):
    """Signal and peg pad centres, in the model frame (Y up)."""
    sig, peg = [], []
    for m in re.finditer(r'\(pad "([^"]*)" (\w+) \w+\s*\(at (-?[\d.]+) (-?[\d.]+)', text):
        p = (float(m.group(3)), -float(m.group(4)))
        # Pegs are plated "MP" pads so KiCad's pin-count filter sees them.
        (peg if m.group(2) == "np_thru_hole" or m.group(1) == "MP" else sig).append(p)
    return sig, peg


def loops(shape, z):
    try:
        return shape.slice(Z, z)
    except Exception:
        return []


def tail_tips(shape):
    z = shape.BoundBox.ZMin + TAIL_PROBE
    return [w.BoundBox.Center for w in loops(shape, z)
            if w.BoundBox.XLength < 1 and w.BoundBox.YLength < 1]


def seat(shape):
    b = shape.BoundBox
    z = b.ZMin
    while z < b.ZMax:
        if any(w.BoundBox.XLength * w.BoundBox.YLength > SEAT_AREA for w in loops(shape, z)):
            return z
        z += 0.05
    return None


def fab_centre(text):
    """Centre of the F.Fab outline, in the model frame (Y up)."""
    # Works whether the fp_line is on one line (vendor export) or KiCad's
    # multi-line layout: each block's single (layer ...) follows its start/end.
    pts = []
    for m in re.finditer(r'\(fp_line\s*\(start (-?[\d.]+) (-?[\d.]+)\)\s*'
                         r'\(end (-?[\d.]+) (-?[\d.]+)\).*?\(layer "([^"]+)"\)', text, re.S):
        if m.group(5) == "F.Fab":
            pts += [(float(m.group(1)), -float(m.group(2))), (float(m.group(3)), -float(m.group(4)))]
    if not pts:
        raise SystemExit("footprint has no F.Fab outline to place the body against")
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def residual(points, targets, dx, dy):
    return max(min(math.hypot(p.x + dx - t[0], p.y + dy - t[1]) for t in targets)
               for p in points)


def rotated(shape, steps):
    s = shape.copy()
    for axis, deg in steps:
        s.rotate(Vector(0, 0, 0), axis, deg)
    return s


def place(shape, sig, peg, centre):
    """Best rotation and translation, judged against the footprint pads.

    With an even pin count the staggered tails -- and the right-angle pegs --
    look the same turned 180 degrees, so the pads alone cannot pick. Among fits
    that are equally good, take the one whose body sits over the F.Fab outline.
    """
    fits = []
    for steps in TO_DOWN.values():
        for spin in (0, 90, 180, 270):
            trial = steps + [(Z, spin)]
            s = rotated(shape, trial)
            tips = tail_tips(s)
            if len(tips) != len(sig):
                continue
            dx = sum(p[0] for p in sig) / len(sig) - sum(t.x for t in tips) / len(tips)
            dy = sum(p[1] for p in sig) / len(sig) - sum(t.y for t in tips) / len(tips)
            err = max(residual(tips, sig, dx, dy),
                      max(math.hypot(p[0] - t.x - dx, p[1] - t.y - dy)
                          for p in sig for t in [min(tips, key=lambda t: math.hypot(
                              p[0] - t.x - dx, p[1] - t.y - dy))]))
            z0 = seat(s)
            if z0 is None:
                continue
            peg_err = 0.0
            if peg:
                holes = [w.BoundBox.Center for w in loops(s, z0 - 0.25)
                         if 0.4 < w.BoundBox.XLength < 1.6 and 0.4 < w.BoundBox.YLength < 1.6]
                peg_err = (max(min(math.hypot(h.x + dx - p[0], h.y + dy - p[1]) for h in holes)
                               for p in peg) if holes else float("inf"))
            score = max(err, peg_err if math.isfinite(peg_err) else 0.0)
            b = s.BoundBox
            off = math.hypot(b.Center.x + dx - centre[0], b.Center.y + dy - centre[1])
            fits.append((score, err, peg_err, trial, dx, dy, z0, off))
    if not fits:
        return None
    floor = min(f[0] for f in fits)
    return min((f for f in fits if f[0] <= floor + 0.05), key=lambda f: f[7])[:7]


def is_pin(face, columns):
    bb = face.BoundBox
    return bb.XLength < PIN_MAX_WIDTH and any(abs(bb.Center.x - c) < PIN_TOL for c in columns)


def write_vrml(path, groups, title):
    with open(path, "w") as out:
        out.write(f"#VRML V2.0 utf8\n# {title}\n# Generated by tools/molex_3d.py from the TraceParts STEP\n\n")
        for name, faces, (r, g, b) in groups:
            verts, tris = [], []
            for f in faces:
                vs, ts = f.tessellate(0.05)
                base = len(verts)
                verts.extend(vs)
                tris.extend((a + base, c + base, d + base) for a, c, d in ts)
            if not tris:
                continue
            out.write(f"Shape {{ # {name}\n  appearance Appearance {{ material Material {{\n"
                      f"    diffuseColor {r:.3f} {g:.3f} {b:.3f}\n"
                      f"    specularColor {min(r+.25,1):.3f} {min(g+.25,1):.3f} {min(b+.25,1):.3f}\n"
                      "    shininess 0.4\n    ambientIntensity 0.3\n  } }\n"
                      "  geometry IndexedFaceSet {\n    coord Coordinate { point [\n")
            out.write("".join(f"{v.x*VRML_SCALE:.4f} {v.y*VRML_SCALE:.4f} {v.z*VRML_SCALE:.4f},\n"
                              for v in verts))
            out.write("    ] }\n    coordIndex [\n")
            out.write("".join(f"{a},{c},{d},-1,\n" for a, c, d in tris))
            out.write("    ]\n    creaseAngle 0.5\n  }\n}\n")


MODEL_BLOCK = ('\t(model "${{KIPRJMOD}}/../../kicadlibs/models/{name}.wrl"\n'
               '\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n'
               '\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n'
               '\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n')


def set_model(path, text, name):
    text = re.sub(r'\t\(model "[^"]*"\n(?:\t\t.*\n)*?\t\)\n', "", text)
    block = MODEL_BLOCK.format(name=name)
    if "\t(embedded_fonts" in text:
        text = text.replace("\t(embedded_fonts", block + "\t(embedded_fonts", 1)
    else:
        text = text.rstrip()[:-1] + block + ")\n"
    open(path, "w").write(text)


def convert(stp):
    pn = os.path.splitext(os.path.basename(stp))[0]
    fp_path, text = footprint(pn)
    name = os.path.splitext(os.path.basename(fp_path))[0]
    m = re.search(r"Circuits, (\w+)", text)
    if not m or m.group(1) not in HOUSING:
        raise SystemExit(f"{pn}: footprint descr does not name a housing colour")
    colour = m.group(1)
    sig, peg = pads(text)

    shape = Part.Shape()
    shape.read(stp)
    best = place(shape, sig, peg, fab_centre(text))
    if best is None:
        print(f"  {pn}: REFUSED - no rotation puts {len(sig)} tails down")
        return False
    score, err, peg_err, steps, dx, dy, z0 = best
    if score > MAX_RESIDUAL:
        print(f"  {pn}: REFUSED - best fit {score:.3f} mm > {MAX_RESIDUAL} mm")
        return False

    placed = rotated(shape, steps)
    placed.translate(Vector(dx, dy, -z0))

    columns = sorted({round(p[0], 3) for p in sig})
    pins = [f for f in placed.Faces if is_pin(f, columns)]
    housing = [f for f in placed.Faces if not is_pin(f, columns)]

    os.makedirs(MODELS, exist_ok=True)
    write_vrml(os.path.join(MODELS, name + ".wrl"),
               [("housing", housing, HOUSING[colour]), ("contacts", pins, TIN)],
               f"{name} - {colour} housing")
    placed.exportStep(os.path.join(MODELS, name + ".step"))
    set_model(fp_path, text, name)

    b = placed.BoundBox
    peg_txt = f"{peg_err:.3f}" if peg and math.isfinite(peg_err) else "n/a"
    print(f"  {pn}: tails {err:.3f} mm, pegs {peg_txt}, height {b.ZMax:.2f}, "
          f"tails {-b.ZMin:.2f} below, contacts {len(pins)}/{len(placed.Faces)} faces -> {name}")
    return True


# freecadcmd does not set __name__ to "__main__", so just run.
_args = [a for a in sys.argv[2:] if a.lower().endswith((".stp", ".step"))]
if not _args:
    raise SystemExit(__doc__)
_ok = sum(convert(a) for a in sorted(_args))
print(f"\n{_ok}/{len(_args)} placed")
