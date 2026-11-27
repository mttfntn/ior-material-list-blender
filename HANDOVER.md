# Handover: IOR Material List

This document is for whoever maintains the add-on next. It explains what the project is,
how it is built, and how to change, test and release it.

## What it is

A Blender extension (add-on) that adds an **IOR** tab to the Shader Editor sidebar with a
searchable list of 485 materials and their index of refraction. The main action is copying
an IOR value to the clipboard. A sub-panel holds 16 metals with complex IOR (n, k), which
can be applied to Metallic BSDF or Principled BSDF nodes.

- Repository: https://github.com/mttfntn/ior-material-list-blender (public), branch `main`
- Not a fork. The data comes from three public web pages (see [README](README.md#data-sources)).
- Supported: **Blender 5.3 only** (`blender_version_min = 5.3.0`, `blender_version_max = 5.4.0`).
- License: GPL-3.0-or-later.

## What you need

| For | Need |
|---|---|
| Running the tests, building, releasing | Blender 5.3 (on Windows: `C:\Program Files\Blender Foundation\Blender 5.3\blender.exe`) |
| Updating the data | Python 3.11 or newer (no packages), internet access |
| Publishing | `git`, push access to the repo; `gh` is optional |

## How the code is organised

| Path | What it is |
|---|---|
| `ior_material_list/` | **The add-on.** This folder is exactly what ships in the zip. |
| `ior_material_list/__init__.py` | All add-on code: data classes, list filtering, operators, panels, register/unregister. |
| `ior_material_list/ior_data.py` | The tables `MATERIALS` and `METALS`. **Generated**, don't edit by hand. |
| `ior_material_list/blender_manifest.toml` | Extension metadata: id, version, supported Blender versions, license, build exclusions. |
| `ior_material_list/LICENSE` | Copy of `LICENSE`, so it ships in the package (a test checks they match). |
| `tools/update_ior_data.py` | Re-scrapes the source sites and rewrites `ior_data.py`. |
| `tests/run.py` | Test entry point, run inside headless Blender. |
| `tests/test_addon.py` | The unit tests (34). |
| `tests/helpers.py` | Stand-ins for what headless Blender lacks: clipboard, editor context, UI layout. |
| `tests/behaviour_dump.py` | Records all observable behaviour to JSON, to compare two versions. |
| `.github/workflows/tests.yml` | CI: tests, manifest validation, build, install check on Blender 5.3. |
| `.github/workflows/release.yml` | On a `vX.Y.Z` tag: test, build, publish a GitHub release. |
| `.github/actions/setup-blender/` | Downloads Blender (with retries and mirrors), checks its SHA-256 and caches it. |
| `README.md`, `HANDOVER.md`, `AGENTS.md`, `LICENSE` | Docs. Not part of the package (only `ior_material_list/` is packed). |

## How it works

1. **Data**: `ior_data.py` holds plain tuples.
   `MATERIALS` rows are `(name, ior, max_ior or None, category, source)`.
   `METALS` rows are `(name, (n_r, n_g, n_b), (k_r, k_g, k_b))`.
2. **Register**: `register()` registers the classes and adds properties to `bpy.types.WindowManager`:
   two collections (`ior_items`, `ior_metals`), the list indices, the search text, and the source, sort
   and range settings. Add-ons can't write data while registering, so a 0.1 s timer
   (`_populate_fresh`) fills the collections afterwards. A `load_post` handler (`_on_load`) refills them
   after a file is opened if they're missing. The WindowManager properties are not saved into
   .blend files.
3. **Search**: `IOR_UL_materials.filter_items` runs on every redraw. A number shows materials
   whose value or range is within ±0.005 (two or more decimals typed) or ±0.05. Text shows materials
   whose name plus category contains every typed word. It also applies the source filter and returns
   the sort order.
4. **Copy**: `IOR_OT_copy` writes the value as text with 3 decimals to `wm.clipboard`. For ranges
   it uses the Min/Mid/Max setting.
5. **Metals**: `IOR_OT_apply_metal` acts on the selected nodes, or on the active node if none is
   selected:
   - **Metallic BSDF:** switched to *Physical Conductor* mode, then IOR = n and Extinction = k.
   - **Principled BSDF:** Base Color = the reflectance at head-on viewing, computed from n and k
     (`_metal_f0`), and Metallic = 1.
   - **Nothing usable selected:** it adds a Metallic BSDF at the editor cursor, if the checkbox is on.

## How to make a change

1. Edit `ior_material_list/__init__.py`. For data changes, edit `tools/update_ior_data.py`
   (`NAME_FIXES`, `BLENDERIT_EXTRA`, `RI_PAGES`, or the parsers), never `ior_data.py` directly.
2. Run the tests (below). For a change that shouldn't alter behaviour (refactoring, speed), also
   run the behaviour comparison.
3. Try it in Blender: build and install the zip (see *Release*, steps 2–3), or for a quick look
   install the folder in a scratch profile.
4. Commit in small steps and push to `main`. CI runs on every push.

## How to run the tests

Run them from the repository root. They never touch your own Blender settings when
`BLENDER_USER_RESOURCES` points at an empty folder.

```bash
export BLENDER_USER_RESOURCES="$PWD/.scratch-profile"
blender -b --factory-startup --python-exit-code 1 --python tests/run.py
```

On Windows PowerShell:

```powershell
$env:BLENDER_USER_RESOURCES = "$PWD\.scratch-profile"
& "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" -b --factory-startup --python-exit-code 1 --python tests/run.py
```

The last line printed is `RESULT tests=34 failures=0 errors=0`, and the exit code is 0 on success.
Add `-- --addon PATH` to test another copy of the add-on folder.

**Behaviour comparison** (old vs new): extract the last commit and dump both versions, then compare:

```bash
git archive HEAD ior_material_list | tar -x -C /tmp/old
blender -b --factory-startup --python tests/behaviour_dump.py -- --addon /tmp/old/ior_material_list --out /tmp/old.json
blender -b --factory-startup --python tests/behaviour_dump.py -- --addon ior_material_list --out /tmp/new.json
cmp /tmp/old.json /tmp/new.json && echo "no behaviour change"
```

The dump is deterministic: two runs of the same code give byte-identical files. A change as small
as 0.001 in the search tolerance shows up in it.

## How to release

1. Set `version` in `ior_material_list/blender_manifest.toml` (for example `1.3.1`).
2. Nothing to change in `README.md`: its release, license and language badges read GitHub, and the Blender badge reads the manifest.
3. Commit and push to `main`. Wait for the **Tests** workflow to pass.
4. Create an **annotated** tag whose message is the release notes, and push it:

   ```bash
   git tag -a v1.3.1 -m "v1.3.1" -m "- What changed, one line per item"
   git push origin v1.3.1
   ```

5. The **Release** workflow tests again and checks that the tag matches the manifest version. It
   then builds `ior_material_list-1.3.1.zip` and publishes the GitHub release with the tag message as
   notes. A lightweight tag (without `-a`) is rejected on purpose.

To build the zip locally: `blender --factory-startup --command extension build --source-dir ior_material_list --output-dir dist`.

## How to bring in updates from the sources

The add-on isn't a fork, so the "upstream" is the three web pages.

```bash
python tools/update_ior_data.py --check   # does anything differ?
python tools/update_ior_data.py           # rewrite ior_material_list/ior_data.py
git diff ior_material_list/ior_data.py    # review every change
```

- If a site changes its HTML, the script stops with an error instead of writing a half-empty file.
  In that case, fix the parser in `tools/update_ior_data.py`.
- The Blender Italia forum post has no usable structure. Its extra entries are kept by hand in
  `BLENDERIT_EXTRA`.
- refractiveindex.info entries come from its CC0 database on GitHub. `RI_PAGES` lists which data
  files to use (name, category, path, and a second path for a birefringent o/e range). The script
  evaluates each page's dispersion formula or table at 589.3 nm, never outside the page's own
  wavelength range, and stops if a page is missing, gives no value there, or absorbs strongly
  (k > 0.1, i.e. a metal). To add a material, browse refractiveindex.info, open the page's
  "data" link, and copy the path after `database/data/` into `RI_PAGES`.
- `--save DIR` keeps every downloaded page; `--html DIR` regenerates from them offline.
- If a new source id is added, also add it to `SOURCE_SITES` and to the `ior_source` enum in
  `__init__.py`. The tests check this.

## Things to know

- **Headless Blender (`-b`) differs from the real app.** Timers never fire, so the lists stay empty
  until something calls `_populate_all()`. The clipboard is always empty, there are no editor areas,
  and panels can't be drawn. The tests work around all of this with the stand-ins in
  `tests/helpers.py`.
- **Hidden sockets:** in Blender 5.3, `node.inputs["IOR"]` doesn't find a socket that's hidden.
  Metallic BSDF hides IOR/Extinction until `fresnel_type` is `PHYSICAL_CONDUCTOR`, so set the mode
  first, or look sockets up by `identifier`.
- **Tooltips:** operator and panel docstrings are shown in Blender as tooltips, so developer notes
  on those classes are `#` comments.
- **No `bl_info`:** extensions take their metadata from `blender_manifest.toml`, and Blender
  creates `bl_info` itself from it.
- **Removing properties:** `unregister()` must cancel the start-up timer. Otherwise a quick
  disable or reinstall runs it after the properties are gone (that bug was fixed in 1.3.0).
- **Testing in isolation:** keep `BLENDER_USER_RESOURCES` (and, for windowed runs, `TEMP`/`TMP`)
  pointed at scratch folders, so your own preferences and add-ons aren't touched.

## Known limits

- Only Blender 5.3 is supported and tested. Other versions are refused by the manifest.
- Values are as published by the sources and aren't independently checked. The sources don't
  always say which wavelength or temperature a value is for. Duplicates across sources are kept, sometimes with different values. One
  forum value (Baby Wash 1.26) was left out as an obvious error.
- Copied values have 3 decimals.
- Metals on Principled BSDF are an approximation: only the head-on color is set, with no edge tint.
- Number search applies to materials only, not to metals.
- Drawing in a real window is checked by hand only. The automated tests check the draw calls
  against a recording stand-in.
- The repository is public: all README badges are live (release and license from GitHub, the
  Blender version from the manifest).
