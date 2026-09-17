#!/usr/bin/env python3
"""Apply the JLCPCB board constraints to every board's .kicad_pro.

Board Setup -> Design Rules -> Constraints is a hard floor DRC applies to
everything, and a rule in the .kicad_dru cannot relax it. So the floor is set to
the loosest the process allows and the rules file carries the per-case numbers;
otherwise the floor silently masks them.

    python3 tools/set_constraints.py [--dry-run]

Skips any project KiCad currently has open, because saving from the GUI would
write the old values straight back.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# mm, matching kicadlibs/jlcpcb-4layer.kicad_dru. Key -> Board Setup label.
RULES = {
    "min_clearance":             (0.09, "Minimum clearance"),
    "min_track_width":           (0.09, "Minimum track width"),
    "min_connection":            (0.09, "Minimum connection width"),
    "min_via_annular_width":     (0.1,  "Minimum annular width"),
    "min_via_diameter":          (0.5,  "Minimum via diameter"),
    "min_through_hole_diameter": (0.3,  "Minimum drill size"),
    "min_hole_to_hole":          (0.2,  "Hole to hole clearance"),
    "min_hole_clearance":        (0.2,  "Copper to hole clearance"),
    "min_copper_edge_clearance": (0.2,  "Copper to edge clearance"),
    "min_silk_clearance":        (0.15, "Minimum item clearance (silkscreen)"),
    "min_text_height":           (1.0,  "Minimum text height"),
    "min_text_thickness":        (0.15, "Minimum text thickness"),
    "min_resolved_spokes":       (2,    "Minimum thermal relief spoke count"),
}

# These live one level up, on design_settings rather than in "rules".
SETTINGS = {
    "solder_mask_clearance":   0.0,   # expansion is 1:1
    "solder_mask_min_width":   0.1,   # soldermask bridge
    "allow_blind_buried_vias": False,
    "allow_microvias":         False,
}


def locked(project: Path) -> bool:
    stem = project.stem
    return any((project.parent / f"~{stem}{ext}.lck").exists()
               for ext in (".kicad_pro", ".kicad_pcb", ".kicad_sch"))


def main():
    dry = "--dry-run" in sys.argv
    changed = skipped = 0

    for pro in sorted(ROOT.glob("*/*/*.kicad_pro")):
        board = pro.parent.name
        if locked(pro):
            print(f"  SKIP {board}: open in KiCad")
            skipped += 1
            continue

        data = json.loads(pro.read_text())
        ds = data.setdefault("board", {}).setdefault("design_settings", {})
        rules = ds.setdefault("rules", {})

        diffs = []
        for key, (want, _label) in RULES.items():
            if rules.get(key) != want:
                diffs.append(f"{key} {rules.get(key)} -> {want}")
                rules[key] = want
        for key, want in SETTINGS.items():
            if ds.get(key) != want:
                diffs.append(f"{key} {ds.get(key)} -> {want}")
                ds[key] = want

        if not diffs:
            print(f"  ok   {board}: already correct")
            continue

        changed += 1
        print(f"  set  {board}: {len(diffs)} changed")
        for d in diffs:
            print(f"         {d}")
        if not dry:
            pro.write_text(json.dumps(data, indent=2) + "\n")

    print(f"\n{changed} project(s) {'would be ' if dry else ''}updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
