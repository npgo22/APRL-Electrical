# ALI2Proposal

APRL ALI-2 instrumentation and control monorepo

## Design
The exigence of this endeavour is twofold:
1. To test the analog frontend designs of our proposed boards for DPF
2. To replace the confusing and elaborate ALI electronics with something that is far better documented and easier to use

The ALI itself can continue to be used for years to come and this reworking of the electronics will not impact it at all. In fact, while some of the electronics designs on the ALI are used for this one, this is going to be its own separate electrical box altogether. The ALI has the following additional limitations, too:
1. Limited I/O
2. Bonded grounds between +24/12/5V power supplies
3. Unknown board-level design decisions/trade-offs made in off-the-shelf components leading to strange artifacts in various measurements
4. Is generally really difficult to understand
5. Mixes bodge-wired custom electronics, off-the-shelf parts, and protoboards
6. Generally has fairly poor mounting
7. Makes use of fairly terrible connectors which are partially damaged and/or have shields which are not properly tied to case GND
8. Is completely full, thus making it impossible to add more electronics
9. Has no methods of cooling, sans the empty hold in the side of the box which completely negate the weather rating of the box itself
10. Uses heterogenous embedded computing ecosystems, requiring cross-domain knowledge of embassy, STM32Cube, and Arduino while doing every single one of them somewhat wrong in one way or another
11. Lacks feedback in many places (error logging namely)
12. Is generally just really hard to work with


Therefore, we propose this repository. Each of the modules serve a specific task, and are hooked to a common ethernet-based network which is far more performant than the original layout while simultaneously being easier to understand and expand. If you want more I/O, you can just simply add another board within a few minutes. Likewise, by opting for cutouts in the enclosure over dedicated port holes, it is also far easier to revise significant parts of the design. 

#### Power
This system is +5V and +24V only, with +3.3V regulated on each board.

### CANBUS vs Ethernet
On the ground station, we are planning to use Ethernet instead of CANBUS. While this means our session protocol will not be tested in a real-world hotfire scenario, it does mean we can fully exploit each of the features offered by ethernet:
- Higher bandwidth (upwards of ~50x) means we don't have to throttle anything including error logging
- The potential for PTP could eventually mean timestamped samples directly from data acquisition (DAQ) boards
- Natural isolation means we don't need any special tricks to get the MAX31856 working with our grounded thermocouples
- Is just generally far more pleasant to work with
- Does not limit future design decisions should we decide to reuse anything

Each of the modules will have a CAN transceiver anyway available for testing.

### Board Statuses
#### Built
<!-- oh no -->

#### Pending (Awaiting Review, etc.)
`chickenstick-locator-1A`
`flight-computer-gps-1A`
`injector-accelerometer-1A`
`ground-station-valve-driver-1A`
`ground-station-pressure-transducers-1B`
`ground-station-loadcells-1A`
`ground-station-io-frontend-1A`
`flight-level-sensor-1A`
`ground-station-thermocouples-2A`

#### Under Development
`flight-BMS-1A`
`flight-accelerometer-1A`

#### On ALI
`ground-station-thermocouples-1A` - Currently hot glued

#### Will Not Be Manufactured
`ground-station-thermocouples-1B` - Not cost effective/superseded by `ground-station-thermocouples-2A`
`ground-station-pressure-transducers-1A` - 4 PT design for testing was unsuitable. Superseded by `ground-station-pressure-transducers-1B`

## Repository layout

```
lib/                                       Shared KiCad libraries
  aprl/                                      APRL-drawn symbols and footprints
  aprl/*-noct.pretty                         Generated. Do not edit
  vendor/                                    Third-party, vendored in-repo
  kicad/                                     Subset of the stock KiCad libraries
models/                                    3D models, flat, one copy each
tools/strip.py                             Generates the -noct libraries
tools/vendor_kicad.py                      Refreshes lib/kicad after a KiCad upgrade
tools/molex_3d.py                          Places and colours the CLIK-Mate 3D models

ground-station-valve-driver-1A/            IPS4140HQ valve driver board
ground-station-thermocouples-1A/           Legacy TC board (the hot glued one)
ground-station-thermocouples-1B/           Legacy TC board (will not be manufactured)
ground-station-thermocouples-2A/           TC board
ground-station-loadcells-1A/               Load cell DAQ
ground-station-pressure-transducers-1A/    4-PT design, superseded by 1B
ground-station-pressure-transducers-1B/    Pressure transducer DAQ
flight-computer-gps-1A/                    FC GPS add-on board
chickenstick-locator-1A/                   Early LoRa locator prototype
injector-accelerometer-1A/                 Accelerometer / vibration board (incomplete)
```

Libraries used to be a submodule plus a copy of `external/` in every board. They
are now shared out of `lib/` and `models/`. Every board sits one level below the
root, so all of them reach the shared trees with the same relative path:
`${KIPRJMOD}/../lib/...` and `${KIPRJMOD}/../models/...`. Nothing to configure -
no submodule init, no KiCad path variables, no CI setup. See `lib/README.md`.

The stock KiCad symbols, footprints and 3D models the boards use are vendored
too, so a board does not depend on which KiCad version happens to be installed.
That is also what makes the 3D renders in `kibot.yaml` reproducible.

Firmware crates and the datasheets live in their own repositories.

## Quick start

Tasks run through [`just`](https://github.com/casey/just).

```sh
# KiBot gerber/BOM output for one board
just kibot ground-station-valve-driver-1A

# Run all KiBot jobs
just kibot-all

# Regenerate the -noct footprints after editing a source footprint
just noct

# Refresh lib/kicad from the local KiCad install (after a KiCad upgrade)
just vendor-kicad

# Netlist + gerber + drill dump of every board, for diffing a change
just snapshot /tmp/before
```

`just snapshot` is the one worth knowing. Take a dump before a library change and
another after, diff them, and any unintended change to a net or to copper shows
up immediately.

## TODO
- Update .ioc files for several projects
- Import other boards
- Standardize KiCad layouts
- Generally clean things up
- CAD models for the actual enclosure
- Calculations (especially regarding caps)
- Documentation for standard components
- Documentation in general for each part
- Fixing the Moore FSM (is way too complex atm) for the valve drivers
- Import prototype sources

## What's not in this repo
- Old code (incl thermocouple 1A's CubeMX and Embassy variants)
- Prototypes (pending ordering)
- ALI ADC hardware (pending import)

## AI Usage
You may use AI to research. Do *NOT* place AI generated anything in this repo. We evaluated it (as seen previously in this repo) and wasted hours troubleshooting things nobody fully understood because a person did not create it. It still needs about 5-10 years to bake before it can do actual electrical engineering. 

That being said, feel free to use it to automate really crappy, redundant tasks, such as making register maps in firmware and making pin maps to rapidly create symbols in KiCad 10+.