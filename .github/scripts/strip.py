#!/usr/bin/env python3
"""
Script to process KiCad footprint files by removing courtyards and/or designators.

This script processes .kicad_mod files and can:
  - Remove courtyard layers (F.CrtYd and B.CrtYd) - saves to APRLPrints-noct.pretty
  - Remove designator (reference) fields - saves to APRLPrints-nod.pretty
  - Remove both courtyards and designators - saves to APRLPrints-nodnofp.pretty

Output files are saved with appropriate suffixes:
  - '-noct' for footprints without courtyards
  - '-nod' for footprints without designators
  - '-nodnofp' for footprints without both designators and courtyards
"""

import os
import re
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def has_courtyard(content: str) -> bool:
    """
    Check if the KiCad file contains courtyard definitions.
    
    Args:
        content: The file content as a string
        
    Returns:
        True if courtyard layers are found, False otherwise
    """
    # Look for courtyard layer definitions
    courtyard_pattern = r'layer\s+"[FB]\.CrtYd"'
    return bool(re.search(courtyard_pattern, content))


def strip_courtyard_from_content(content: str, suffix: str = '') -> str:
    """
    Remove all courtyard-related elements from KiCad file content.
    
    This function removes complete geometric elements (fp_rect, fp_line, fp_poly, 
    fp_circle, fp_arc) that are on courtyard layers (F.CrtYd or B.CrtYd).
    
    Also renames the footprint by appending the suffix to the footprint name.
    
    Args:
        content: The file content as a string
        suffix: Suffix to append to the footprint name (e.g., '-noct')
        
    Returns:
        Content with courtyard elements removed and footprint renamed
    """
    lines = content.split('\n')
    result_lines = []
    i = 0
    removed_count = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if this line starts a geometric element
        # Common KiCad footprint geometric elements
        geom_match = re.match(r'^(\s*)\((fp_rect|fp_line|fp_poly|fp_circle|fp_arc)\b', line)
        
        if geom_match:
            # Find the complete element (up to its closing parenthesis)
            indent = geom_match.group(1)
            element_lines = [line]
            paren_count = line.count('(') - line.count(')')
            j = i + 1
            
            # Continue collecting lines until we balance parentheses
            while j < len(lines) and paren_count > 0:
                element_lines.append(lines[j])
                paren_count += lines[j].count('(') - lines[j].count(')')
                j += 1
            
            # Check if this element is on a courtyard layer
            element_content = '\n'.join(element_lines)
            if re.search(r'layer\s+"[FB]\.CrtYd"', element_content):
                # Skip this element (don't add to result)
                removed_count += 1
                i = j
                continue
            else:
                # Keep this element
                result_lines.extend(element_lines)
                i = j
                continue
        
        # If not a geometric element, keep the line
        result_lines.append(line)
        i += 1
    
    if removed_count > 0:
        logger.info(f"  Removed {removed_count} courtyard element(s)")
    
    result_content = '\n'.join(result_lines)
    
    # Rename the footprint by appending the suffix
    if suffix:
        # Match the footprint declaration at the beginning of the file
        # Format: (footprint "NAME"
        footprint_pattern = r'^(\(footprint\s+"[^"]+)(")'
        result_content = re.sub(footprint_pattern, rf'\1{suffix}\2', result_content, count=1, flags=re.MULTILINE)
    
    return result_content

# KiCAD will just re-add the designator.
# def remove_designator(content: str) -> str:
#     """
#     Remove the designator (reference) text field from the KiCad file content.
    
#     The designator is typically the 'REF**' or 'reference' field in KiCad footprints.
#     This function removes:
#     - Older format: (fp_text reference "REF**" ...)
#     - Newer format: (property "Reference" "REF**" ...)
    
#     Args:
#         content: The file content as a string
        
#     Returns:
#         Content with the designator (reference) field removed
#     """
#     lines = content.split('\n')
#     result_lines = []
#     i = 0
#     removed_count = 0
    
#     while i < len(lines):
#         line = lines[i]
        
#         # Check if this line starts a reference element (old or new format)
#         # Old format: (fp_text reference "REF**" ...
#         # New format: (property "Reference" "REF**" ...
#         fp_text_match = re.match(r'^(\s*)\(fp_text\s+reference\b', line)
#         property_match = re.match(r'^(\s*)\(property\s+"Reference"', line)
        
#         if fp_text_match or property_match:
#             # Find the complete element (up to its closing parenthesis)
#             element_lines = [line]
#             paren_count = line.count('(') - line.count(')')
#             j = i + 1
            
#             # Continue collecting lines until we balance parentheses
#             while j < len(lines) and paren_count > 0:
#                 element_lines.append(lines[j])
#                 paren_count += lines[j].count('(') - lines[j].count(')')
#                 j += 1
            
#             # Skip this element (don't add to result)
#             removed_count += 1
#             i = j
#             continue
        
#         # If not a reference element, keep the line
#         result_lines.append(line)
#         i += 1
    
#     if removed_count > 0:
#         logger.info(f"  Removed {removed_count} designator field(s)")
    
#     return '\n'.join(result_lines)


def process_file(input_path: Path, output_path: Path, strip_courtyard: bool = True, 
                 strip_designator: bool = False, suffix: str = '') -> bool:
    """
    Process a single KiCad footprint file.
    
    Args:
        input_path: Path to the input .kicad_mod file
        output_path: Path where the processed file should be saved
        strip_courtyard: If True, remove courtyard layers
        # strip_designator: If True, remove the reference designator field
        suffix: Suffix to append to the footprint name (e.g., '-noct')
        
    Returns:
        True if processing was successful, False otherwise
    """
    try:
        # Read the input file
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        processed_content = content
        modified = False
        
        # Strip courtyards if requested
        if strip_courtyard:
            if has_courtyard(content):
                logger.info(f"  Processing {input_path.name} (removing courtyards)...")
                processed_content = strip_courtyard_from_content(processed_content, suffix)
                modified = True
            else:
                logger.warning(f"  No courtyard found in {input_path.name}")
                # Still rename the footprint even if no courtyard found
                if suffix:
                    footprint_pattern = r'^(\(footprint\s+"[^"]+)(")'
                    processed_content = re.sub(footprint_pattern, rf'\1{suffix}\2', processed_content, count=1, flags=re.MULTILINE)
        
        # Strip designator if requested
        # if strip_designator:
        #     logger.info(f"  Processing {input_path.name} (removing designator)...")
        #     processed_content = remove_designator(processed_content)
        #     modified = True
        
        # Write the output file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(processed_content)
        
        if modified:
            logger.info(f"  Successfully created {output_path.name}")
        else:
            logger.info(f"  Copied {output_path.name} (no modifications needed)")
        return True
        
    except Exception as e:
        logger.error(f"  Error processing {input_path}: {e}")
        return False


def main():
    """Generate a -noct sibling for every .pretty library under kicadlibs/aprl/."""
    lib_dir = Path(__file__).resolve().parents[2] / 'kicadlibs' / 'aprl'
    libs = sorted(d for d in lib_dir.glob('*.pretty')
                  if not d.name.endswith('-noct.pretty'))

    if not libs:
        logger.error(f"No .pretty libraries found in {lib_dir}")
        sys.exit(1)

    overall_success = True

    for input_dir in libs:
        kicad_files = sorted(input_dir.glob('*.kicad_mod'))
        if not kicad_files:
            logger.warning(f"No .kicad_mod files in {input_dir.name}, skipping")
            continue

        output_dir = lib_dir / f"{input_dir.stem}-noct.pretty"
        output_dir.mkdir(exist_ok=True)

        # Drop stale outputs so a renamed or deleted source footprint does not
        # leave an orphan behind.
        expected = {f"{f.stem}-noct.kicad_mod" for f in kicad_files}
        for stale in output_dir.glob('*.kicad_mod'):
            if stale.name not in expected:
                logger.info(f"  Removing stale {stale.name}")
                stale.unlink()

        logger.info(f"\n{'='*50}")
        logger.info(f"{input_dir.name} -> {output_dir.name} ({len(kicad_files)} files)")
        logger.info(f"{'='*50}")

        success_count = 0
        for input_file in kicad_files:
            output_file = output_dir / f"{input_file.stem}-noct.kicad_mod"
            if process_file(input_file, output_file, True, False, '-noct'):
                success_count += 1

        logger.info(f"\n{input_dir.name}: {success_count}/{len(kicad_files)} processed")
        if success_count < len(kicad_files):
            overall_success = False

    logger.info(f"\n{'='*50}")
    logger.info("All processing complete")
    logger.info(f"{'='*50}")

    if not overall_success:
        sys.exit(1)


if __name__ == '__main__':
    main()
