#!/usr/bin/env python3
"""Hide an LCSC logo that is painted on, not modelled.

  debrand_colour.py <model.step> [--write] [--rgb R,G,B]

These models draw the logo as ordinary faces on a flat wall, coloured with
DRAUGHTING_PRE_DEFINED_COLOUR('black') while the wall around them uses a
COLOUR_RGB. Repointing those faces at the wall's own style makes the lettering
disappear with no geometry change -- and, unlike a boolean, without discarding
every other colour in the file.

Only faces whose style resolves to a predefined colour are touched, and only
when the wall they sit on can be identified, so nothing else is disturbed.
Some models instead paint the (slightly raised) logo with a plain RGB colour;
pass that colour with --rgb (e.g. --rgb 1,1,1 for white lettering).
"""
import collections
import re
import sys

path = sys.argv[1]
write = "--write" in sys.argv
logo_rgb = next((tuple(float(x) for x in a.split(",")) for a in sys.argv[2:] if a.count(",") == 2), None)
text = open(path, encoding="latin-1", errors="replace").read()

ents = {int(m.group(1)): m.group(2)
        for m in re.finditer(r"#(\d+)\s*=\s*(.*?);\s*(?=#\d+\s*=|ENDSEC)", text, re.S)}
refs = lambda i: [int(x) for x in re.findall(r"#(\d+)", ents.get(i, ""))]
kind = lambda i: (re.match(r"\s*([A-Z_0-9]+)", ents.get(i, "")) or [None, ""])[1]
predef = {i for i in ents if kind(i) == "DRAUGHTING_PRE_DEFINED_COLOUR"}


def walk(start, want):
    seen, stack = set(), [start]
    while stack:
        j = stack.pop()
        if j in seen or j not in ents:
            continue
        seen.add(j)
        if want(j):
            return j
        stack.extend(refs(j))


def verts(face):
    seen, stack, pts = set(), [face], []
    while stack:
        i = stack.pop()
        if i in seen or i not in ents:
            continue
        seen.add(i)
        if kind(i) == "CARTESIAN_POINT":
            v = re.findall(r"[-\d.eE+]+", ents[i].split("(", 2)[-1])
            if len(v) >= 3:
                pts.append([float(x) for x in v[:3]])
            continue
        stack.extend(refs(i))
    return pts


logo, rgb = [], []
for i in list(ents):
    if kind(i) != "STYLED_ITEM":
        continue
    r = refs(i)
    if not r or kind(r[-1]) != "ADVANCED_FACE":
        continue
    pts = verts(r[-1])
    if not pts:
        continue
    lo = [min(c) for c in zip(*pts)]
    hi = [max(c) for c in zip(*pts)]
    d = [hi[k] - lo[k] for k in range(3)]
    ax = d.index(min(d))
    plane = round((lo[ax] + hi[ax]) / 2, 3)
    c = walk(r[0], lambda j: kind(j) in ("COLOUR_RGB", "COLOR_RGB"))
    is_logo_rgb = c and logo_rgb and all(
        abs(float(v) - w) < 1e-3 for v, w in zip(re.findall(r"[-\d.eE+]+", ents[c])[-3:], logo_rgb))
    if walk(r[0], lambda j: j in predef) or is_logo_rgb:
        logo.append((i, ax, plane))
    elif c:
        rgb.append((r[0], ax, plane, max(d)))

print(f"DB {path.split('/')[-1]}: {len(logo)} logo faces")
if not logo:
    sys.exit("DB nothing to do")

planes = collections.Counter((ax, pl) for _, ax, pl in logo)
if logo_rgb:
    # raised lettering: its tops and (tiny) side walls all take the colour of the
    # surface it stands on -- the plane most of the logo's faces lie in.
    ax0, pl0 = collections.Counter((ax, round(pl, 2)) for _, ax, pl in logo).most_common(1)[0][0]
    logo = [(i, ax0, pl0) for i, _, _ in logo]
    planes = collections.Counter({(ax0, pl0): len(logo)})
fixed = 0
out = text
for (ax, plane), n in planes.items():
    # the wall: largest RGB-coloured face flat in the same axis, nearest that plane
    near = [c for c in rgb if c[1] == ax and abs(c[2] - plane) < 0.2]
    if not near:
        print(f"DB   {'xyz'[ax]}={plane}: {n} faces, no wall found -- left alone")
        continue
    style = max(near, key=lambda c: c[3])[0]
    print(f"DB   {'xyz'[ax]}={plane}: {n} faces -> wall style #{style}")
    for i, a, p in logo:
        if (a, p) != (ax, plane):
            continue
        old = ents[i]
        new = re.sub(r"\(\s*#\d+\s*\)", f"(#{style})", old, count=1)
        for a1, b1 in ((f"#{i} = {old};", f"#{i} = {new};"), (f"#{i}={old};", f"#{i}={new};")):
            out = out.replace(a1, b1)
        fixed += 1

print(f"DB repainted {fixed} faces; colours {len(re.findall('COLOUR_RGB', out))}, "
      f"styled items {len(re.findall('STYLED_ITEM', out))}")
if write and fixed:
    open(path, "w", encoding="latin-1").write(out)
    print("DB written")
