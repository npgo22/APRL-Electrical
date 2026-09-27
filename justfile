set shell := ["bash", "-euo", "pipefail", "-c"]

# Every live board directory, at whatever depth it sits (same list CI builds).
boards := `python3 -c 'import sys; sys.path.insert(0, ".github/scripts"); from vendor_kicad import ROOT, boards; print(" ".join(b.relative_to(ROOT).as_posix() for b in boards()))'`

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
    for d in {{boards}}; do pro=$(ls "$d"/*.kicad_pro); \
      cp kicadlibs/jlcpcb-4layer.kicad_dru "${pro%.kicad_pro}.kicad_dru"; \
      echo "rules -> ${pro%.kicad_pro}.kicad_dru"; \
    done

# KiBot outputs for one board, e.g. `just kibot ali/v2/valvedrivers`
kibot board:
    cd {{board}} && \
    pro=$(ls *.kicad_pro | head -1) && b=${pro%.kicad_pro} && \
    kibot -c "$(git rev-parse --show-toplevel)/kibot.yaml" -e "$b.kicad_sch" -b "$b.kicad_pcb"

# KiBot outputs for every board
kibot-all:
    for d in {{boards}}; do pro=$(ls "$d"/*.kicad_pro); \
      d=$(dirname "$pro"); echo "=== $d"; just kibot "$d"; \
    done

# Netlist + gerber + drill snapshot of every board into DIR (for A/B diffing)
snapshot dir:
    mkdir -p {{dir}}
    out=$(realpath {{dir}}); \
    for d in {{boards}}; do pro=$(ls "$d"/*.kicad_pro); \
      d=$(dirname "$pro"); b=$(basename "$pro" .kicad_pro); n=${d//\//-}; \
      [ -f "$d/$b.kicad_pcb" ] || continue; \
      ( cd "$d" && \
        kicad-cli sch export netlist -o "$out/$n.net" "$b.kicad_sch" >/dev/null && \
        kicad-cli pcb export gerbers -o "$out/$n.gbr/" "$b.kicad_pcb" >/dev/null && \
        kicad-cli pcb export drill   -o "$out/$n.drl/" "$b.kicad_pcb" >/dev/null ); \
      echo "snapshot $n"; \
    done
