#!/usr/bin/env python3
"""Vendor the stock KiCad symbol and footprint libraries, plus the 3D models the
boards use.

Every stock symbol and footprint library is copied whole into kicadlibs/kicad/,
and every board's lib tables list every library in kicadlibs/. Whole copies are
the point: a project table row shadows the global library of the same name, so
a partial copy hides the rest of that library from the chooser.

3D models are the exception -- the stock set is 3 GB. Only models for footprints
placed on a board are copied into kicadlibs/models/ and repointed; any other
footprint keeps ${KICAD10_3DMODEL_DIR} and renders from the local install until
it is placed and this is re-run.

Idempotent: safe to re-run after a KiCad upgrade.
"""
import re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KICAD = Path("/usr/local/share/kicad")
# The flatpak library runtime carries a few 3D models the /usr/local install
# lacks (and the reverse), so look in both before calling a model dangling.
MODEL_DIRS = [KICAD / "3dmodels", *sorted(Path.home().glob(
    ".local/share/flatpak/runtime/org.kicad.KiCad.Library.Packages3D/*/stable/*/files/3dmodels"))]
LIBS_DIR = "kicadlibs"          # repo-relative name of the library tree
LIBS = ROOT / LIBS_DIR
DEST = LIBS / "kicad"           # generated; everything in it is overwritten
MODELS = LIBS / "models"
# Boards sit at varying depths, so paths go through the APRL_LIBS path
# variable (KiCad: Preferences > Configure Paths; CI: the workflow env) rather
# than counting "../" hops from KIPRJMOD.
VAR = "${APRL_LIBS}"

# KiCad ships these footprints but not their 3D models. Where we already carry
# the same manufacturer part, point at ours; the rest stay dangling and are
# reported. Only exact part matches belong here -- a near-miss model renders a
# part that is not on the board, which is worse than no model at all.
SUBSTITUTE = {
    "Connector_RJ.3dshapes/RJ45_Hanrun_HR911105A_Horizontal.step": "RJ45-TH_HR911105A.step",
    "Connector_USB.3dshapes/USB_C_Receptacle_HRO_TYPE-C-31-M-12.step": "HRO_TYPE-C-31-M-12.step",
    "Fuse.3dshapes/FuseHolder_Blade_ATO_Littelfuse_FLR_178.6165.step": "178.6165.0001.step",
    "Package_DFN_QFN.3dshapes/DFN-8-1EP_3x2mm_P0.5mm_EP1.7x1.4mm.step": "DFN8_2x3MC_MCH.step",
    "Package_DFN_QFN.3dshapes/VQFN-24-1EP_4x4mm_P0.5mm_EP2.5x2.5mm.step":
        "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm.step",
    # KiCad's own model of the same body, terminals and pitch, differing only in
    # the exposed pad, which is hidden under the part.
    # TJA1462ATK (NXP SOT782-1): pad 0.05 mm narrower.
    "Package_SON.3dshapes/HVSON-8-1EP_3x3mm_P0.65mm_EP1.6x2.4mm.step":
        "DFN-8-1EP_3x3mm_P0.65mm_EP1.55x2.4mm.step",
    # STM32H563RIVx (VFQFPN68): pad 5.2 mm, not 6.4.
    "Package_DFN_QFN.3dshapes/QFN-68-1EP_8x8mm_P0.4mm_EP6.4x6.4mm.step":
        "QFN-68-1EP_8x8mm_P0.4mm_EP5.2x5.2mm.step",
    # ADS124S08 (VQFN-32 5x5): pad 3.3 mm, not 3.15.
    "Package_DFN_QFN.3dshapes/VQFN-32-1EP_5x5mm_P0.5mm_EP3.15x3.15mm.step":
        "QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm.step",
    # G-Switch GT-USB-7051A: KiCad ships the footprint but no model. This one is
    # the vendor's, fetched with JLC2KiCadLib and stripped of its LCSC logo.
    "Connector_USB.3dshapes/USB_C_Receptacle_G-Switch_GT-USB-7051x.step":
        "USB-C-SMD_GT-USB-7051A.step",
    # Also footprint-without-model, both fetched with JLC2KiCadLib.
    # Epson TG2520SMN 32 MHz (LCSC C6284791).
    "Oscillator.3dshapes/Oscillator_SMD_SeikoEpson_TG2520SMN-xxx-xxxxxx-4Pin_2.5x2.0mm.step":
        "OSC-SMD_4P-L2.5-W2.0-BL.step",
    # u-blox NEO-M8N (LCSC C6330769); matches the 24-pad NEO footprint.
    "RF_GPS.3dshapes/ublox_NEO.step": "GPSM-SMD_NEO-M8N.step",
}

# Models whose geometry does not sit on the footprint origin. Without these the
# part renders in the wrong place, and re-vendoring would silently undo a fix
# made by hand in the footprint. Millimetres, as KiCad's (offset (xyz ...)) wants.
MODEL_XFORM = {
    "USB-C-SMD_GT-USB-7051A.step": (0.0, 0.0, 5.775),
    "HRO_TYPE-C-31-M-12.step": (-4.475, -2.453, 0.0),
    # Model is centred on itself; the footprint origin is pin 1.
    "RJ45-TH_HR911105A.step": (4.44, -6.56, 0.0),
}

MODEL_REF = re.compile(r'\(model "\$\{KICAD10_3DMODEL_DIR\}/([^"]+)"')


# Directories that hold boards we do not maintain: archived designs, KiCad's
# generated template stub, and backup/history dumps.
SKIP = ("kicadlibs", "do-not-include", "-backups", ".history", "ali/v1", "ali/v2/default")


def boards():
    """Every live board, at whatever depth it sits."""
    return sorted({p.parent for p in ROOT.rglob("*.kicad_pro")
                   if not any(s in p.as_posix() for s in SKIP)})


def copy_libraries():
    """Mirror every stock symbol and footprint library into DEST."""
    stock = {d.name: d for sub, pattern in (("symbols", "*.kicad_symdir"),
                                            ("footprints", "*.pretty"))
             for d in (KICAD / sub).glob(pattern)}
    DEST.mkdir(parents=True, exist_ok=True)
    for d in DEST.iterdir():                  # libraries KiCad has since dropped
        if d.name not in stock:
            shutil.rmtree(d) if d.is_dir() else d.unlink()
    for name, src in sorted(stock.items()):
        shutil.rmtree(DEST / name, ignore_errors=True)
        shutil.copytree(src, DEST / name)
    n_sym = sum(n.endswith(".kicad_symdir") for n in stock)
    print(f"  libraries: {n_sym} symbol, {len(stock) - n_sym} footprint (whole)")


def uri_index():
    """(footprint, symbol): library name -> repo-relative path."""
    fp, sym = {}, {}
    for d in sorted(LIBS.glob("*/*.pretty")):
        fp[d.stem] = f"{LIBS_DIR}/{d.parent.name}/{d.name}"
    for d in sorted(LIBS.glob("*/*.kicad_symdir")):
        sym[d.stem] = f"{LIBS_DIR}/{d.parent.name}/{d.name}"
    for f in sorted(LIBS.glob("*/*.kicad_sym")):
        sym[f.stem] = f"{LIBS_DIR}/{f.parent.name}/{f.name}"
    return fp, sym


def model_targets():
    """Files whose model refs get vendored: boards, our own footprints, and the
    stock footprints actually placed on a board."""
    fp_uri, _ = uri_index()
    targets = {f for b in boards() for f in b.glob("*.kicad_pcb") if "autosave" not in f.name}
    targets |= {f for f in LIBS.rglob("*.kicad_mod") if DEST not in f.parents}
    for pcb in [f for b in boards() for f in b.glob("*.kicad_pcb")]:
        for lib, name in re.findall(r'\(footprint "([^":]+):([^"]+)"',
                                    pcb.read_text(errors="replace")):
            f = ROOT / fp_uri.get(lib, "-") / f"{name}.kicad_mod"
            if f.exists():
                targets.add(f)
    return sorted(targets)


def copy_models(targets):
    """Copy the stock models those files reference into MODELS, then repoint."""
    refs = set()
    for f in targets:
        refs |= set(MODEL_REF.findall(f.read_text(errors="replace")))

    copied, dangling = 0, []
    rename = {}
    for ref in sorted(refs):
        name = Path(ref).name
        src = next((d / ref for d in MODEL_DIRS if (d / ref).exists()), None)
        if src:
            if not (MODELS / name).exists():
                shutil.copy2(src, MODELS / name); copied += 1
            rename[ref] = name
        elif ref in SUBSTITUTE and (MODELS / SUBSTITUTE[ref]).exists():
            rename[ref] = SUBSTITUTE[ref]
        else:
            dangling.append(ref)

    # Older boards and footprints counted "../" hops from KIPRJMOD; normalise
    # those to the path variable so a moved board heals itself on the next run.
    LEGACY = re.compile(r"\$\{KIPRJMOD\}/(?:\.\./)+" + LIBS_DIR + "/")

    changed = 0
    for f in targets:
        orig = f.read_text(errors="replace")
        t = LEGACY.sub(VAR + "/", orig)
        for ref, name in rename.items():
            t = t.replace(f'${{KICAD10_3DMODEL_DIR}}/{ref}', f'{VAR}/models/{name}')
        for name, xyz in MODEL_XFORM.items():
            t = re.sub(r'(\(model "[^"]*' + re.escape(name) + r'"\s*\(offset\s*\(xyz )[^)]*',
                       lambda m, v=xyz: m.group(1) + "%g %g %g" % v, t)
        if t != orig:
            f.write_text(t); changed += 1

    subs = sum(1 for r in rename if r in SUBSTITUTE)
    print(f"  models: {copied} copied from KiCad, {subs} substituted from ours, "
          f"{changed} files repointed")
    for d in dangling:
        print(f"  DANGLING: KiCad ships no 3D model for {d}")


def update_tables():
    """Point every board's lib tables at every library in kicadlibs/.

    All boards get the same rows, so any stock or house part can be placed on
    any board without editing a table first.
    """
    fp_uri, sym_uri = uri_index()
    for b in boards():
        for tbl, kind, pattern_glob, pattern, uri in (
                ("fp-lib-table", "fp", "*.kicad_pcb", r'\(footprint "([^":]+):', fp_uri),
                ("sym-lib-table", "sym", "*.kicad_sch", r'\(lib_id "([^":]+):', sym_uri)):
            rows = "".join(
                f'\t(lib (name "{n}") (type "KiCad") '
                f'(uri "{VAR}/{p[len(LIBS_DIR) + 1:]}") (options "") (descr ""))\n'
                for n, p in sorted(uri.items()))
            # Rows for libraries that live with the board, not in kicadlibs/.
            if (b / tbl).exists():
                rows += "".join(l for l in (b / tbl).read_text().splitlines(keepends=True)
                                if "(lib " in l
                                and re.search(r'\(name "([^"]+)"', l).group(1) not in uri)
            (b / tbl).write_text(f"({kind}_lib_table\n\t(version 7)\n{rows})\n")
            used = set()
            for f in b.glob(pattern_glob):
                used |= set(re.findall(pattern, f.read_text(errors="replace")))
            unknown = sorted(used - set(uri))
            if unknown:
                print(f"  WARN: {b.relative_to(ROOT)}/{tbl}: no library in {LIBS_DIR}/ for {unknown}")


if __name__ == "__main__":
    if not KICAD.is_dir():
        sys.exit(f"KiCad share directory not found: {KICAD}")
    print("vendoring stock KiCad libraries:")
    copy_libraries()
    copy_models(model_targets())
    update_tables()
    print("  lib tables updated")
