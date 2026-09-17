set shell := ["bash", "-euo", "pipefail", "-c"]

# Boards live two levels down: <group>/<board>/, e.g. ali/loadcells.

# List available recipes
default:
    @just --list

# Regenerate the -noct (no-courtyard) footprint variants from kicadlibs/aprl/*.pretty
noct:
    python3 .github/scripts/strip.py

# Vendor every stock KiCad symbol/footprint library into kicadlibs/kicad, plus the models boards use
vendor-kicad:
    python3 .github/scripts/vendor_kicad.py

# Apply the JLCPCB board constraints to every board's .kicad_pro
constraints *args:
    python3 .github/scripts/set_constraints.py {{args}}

# Copy the canonical JLCPCB design rules next to every board (KiCad only reads a
# .kicad_dru sitting beside the project)
rules:
    for pro in */*/*.kicad_pro; do \
      cp kicadlibs/jlcpcb-4layer.kicad_dru "${pro%.kicad_pro}.kicad_dru"; \
      echo "rules -> ${pro%.kicad_pro}.kicad_dru"; \
    done

# Place and colour TraceParts CLIK-Mate STEPs, e.g. `just molex-3d ~/Downloads/5031590801.stp`
molex-3d +files:
    freecadcmd .github/scripts/molex_3d.py {{files}}

# Repoint an LCSC logo's faces at the surrounding wall colour
debrand +models:
    python3 .github/scripts/debrand_colour.py {{models}} --write

# KiBot outputs for one board, e.g. `just kibot ali/valve-drivers`
kibot board:
    cd {{board}} && \
    pro=$(ls *.kicad_pro | head -1) && b=${pro%.kicad_pro} && \
    kibot -c "$(git rev-parse --show-toplevel)/kibot.yaml" -e "$b.kicad_sch" -b "$b.kicad_pcb"

# KiBot outputs for every board
kibot-all:
    for pro in */*/*.kicad_pro; do \
      d=$(dirname "$pro"); echo "=== $d"; just kibot "$d"; \
    done

# Netlist + gerber + drill snapshot of every board into DIR (for A/B diffing)
snapshot dir:
    mkdir -p {{dir}}
    out=$(realpath {{dir}}); \
    for pro in */*/*.kicad_pro; do \
      d=$(dirname "$pro"); b=$(basename "$pro" .kicad_pro); n=${d//\//-}; \
      [ -f "$d/$b.kicad_pcb" ] || continue; \
      ( cd "$d" && \
        kicad-cli sch export netlist -o "$out/$n.net" "$b.kicad_sch" >/dev/null && \
        kicad-cli pcb export gerbers -o "$out/$n.gbr/" "$b.kicad_pcb" >/dev/null && \
        kicad-cli pcb export drill   -o "$out/$n.drl/" "$b.kicad_pcb" >/dev/null ); \
      echo "snapshot $n"; \
    done

# Define the drawing-sheet fields (kicadlibs/APRL_*.kicad_wks) as
# empty project text variables, keeping any values already set. Skips projects
# KiCad has open -- close them and re-run.
textvars:
    #!/usr/bin/env python3
    import glob, json, os, re
    wks = "".join(open(f).read() for f in glob.glob("kicadlibs/APRL_*.kicad_wks"))
    names = sorted(set(re.findall(r"\$\{([A-Z0-9_]+)\}", wks)) - {"KICAD_VERSION", "SHEETPATH"})
    for pro in sorted(glob.glob("*/*/*.kicad_pro")):
        lock = os.path.join(os.path.dirname(pro), "~" + os.path.basename(pro) + ".lck")
        if os.path.exists(lock):
            print(f"skip (open in KiCad): {pro}"); continue
        d = json.load(open(pro))
        tv = d.setdefault("text_variables", {})
        added = [n for n in names if n not in tv]
        # Carry over what used to live in Page Settings (root sheet title block).
        sch = pro[:-len(".kicad_pro")] + ".kicad_sch"
        tb = re.search(r"\(title_block(.*?)\n\t\)", open(sch).read(), re.S) if os.path.exists(sch) else None
        tb = tb.group(1) if tb else ""
        old = {"REV": r'\(rev "([^"]*)"', "NOTE1": r'\(comment 1 "([^"]*)"', "NOTE2": r'\(comment 2 "([^"]*)"'}
        for n in added:
            m = re.search(old[n], tb) if n in old else None
            tv[n] = m.group(1) if m else ""
        if added:
            json.dump(d, open(pro, "w"), indent=2); open(pro, "a").write("\n")
        print(f"{pro}: +{len(added)}")
