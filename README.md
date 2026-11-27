# IOR Material List for Blender

[![Blender](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmttfntn%2Fior-material-list-blender%2Fmain%2Fior_material_list%2Fblender_manifest.toml&query=%24.blender_version_min&label=Blender&color=E87D0D&logo=blender&logoColor=white)](https://www.blender.org/download/)
[![Release](https://img.shields.io/github/v/release/mttfntn/ior-material-list-blender)](https://github.com/mttfntn/ior-material-list-blender/releases/latest)
[![Tests](https://github.com/mttfntn/ior-material-list-blender/actions/workflows/tests.yml/badge.svg)](https://github.com/mttfntn/ior-material-list-blender/actions/workflows/tests.yml)
[![License](https://img.shields.io/github/license/mttfntn/ior-material-list-blender)](LICENSE)
[![Language](https://img.shields.io/github/languages/top/mttfntn/ior-material-list-blender)](https://github.com/mttfntn/ior-material-list-blender)

A searchable list of index-of-refraction (IOR) values in Blender's Shader Editor.
Find a material, click once, and its IOR is on the clipboard, ready to paste into any IOR field.

- **485 materials** (glass, liquids, plastics, fabrics, stone, gems, minerals, gases …)
- **Search** by name or category (`glass`, `honey water`, `gem`), or type a number (`1.33`) to find materials with that IOR
- **Filter** by source and **sort** by name or IOR
- **Ranges**: for materials given as a min–max range, choose Min, Mid or Max before copying
- **16 metals** with measured complex IOR (n, k per RGB channel): one click sets a Metallic BSDF to physical-conductor mode with those values, or gives a Principled BSDF the matching color

## Install

Requires **Blender 5.3**.

1. Download `ior_material_list-<version>.zip` from the [latest release](https://github.com/mttfntn/ior-material-list-blender/releases/latest).
2. In Blender: **Edit → Preferences → Get Extensions → ⌄ (top right) → Install from Disk…** and pick the zip.
3. Open the **Shader Editor**, press **N**, and click the **IOR** tab.

## Use

| Do this | To |
|---|---|
| Type in the search box | filter by name/category, or by IOR value |
| Click the copy icon on a row | copy that material's IOR (e.g. `1.520`) |
| Select a row, pick Min / Mid / Max | choose which end of a range is copied |
| Hover an IOR field, **Ctrl+V** | paste the value |
| Open **Metals (n, k)**, click ✓ on a metal | apply it to the selected Metallic/Principled BSDF (or add a new Metallic BSDF) |

## Data sources

The values come from these public lists (credit to their authors):

- [balyberdin.com — IOR list](https://balyberdin.com/tools/ior-list/) (curated materials by category, and the metals)
- [Pixel and Poly — IOR list](https://pixelandpoly.com/ior.html) (A–Z list)
- [Blender Italia forum — Indice IOR per materiale](https://community.blender.it/forums/topic/indice-ior-per-materiale/) (a few entries missing from the other two)
- [RefractiveIndex.INFO](https://refractiveindex.info/) (measured data for common glasses, liquids, plastics and crystals, from its [CC0 database](https://github.com/polyanskiy/refractiveindex.info-database); n at 589.3 nm, birefringent crystals as an o/e range)

Some materials appear in more than one source with slightly different values; both are kept.

## For maintainers

- [HANDOVER.md](HANDOVER.md): how the project works, how to change it, test it and release it.
- [AGENTS.md](AGENTS.md): the same, compact, for AI coding assistants.

## License

[GPL-3.0-or-later](LICENSE), like Blender itself. © 2026 Matteo Fontana.
