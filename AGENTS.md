# AGENTS.md — IOR Material List (Blender extension)

Compact guide for AI coding assistants. Human-oriented detail: [HANDOVER.md](HANDOVER.md).

## Facts
- Blender extension, id `ior_material_list`, GPL-3.0-or-later. Supports **Blender 5.3 only** (manifest min 5.3.0, max 5.4.0 exclusive).
- Repo `github.com/mttfntn/ior-material-list-blender` (public), branch `main`. Not a fork.
- Ships only `ior_material_list/` (manifest, `__init__.py`, `ior_data.py`, `LICENSE`). Root docs/tests/tools are not packed.

## Commands (run from repo root)
```bash
# tests (always with a scratch profile)
BLENDER_USER_RESOURCES="$PWD/.scratch-profile" blender -b --factory-startup --python-exit-code 1 --python tests/run.py
# expect last line: RESULT tests=34 failures=0 errors=0 ; exit 0
blender --factory-startup --command extension validate ior_material_list
blender --factory-startup --command extension build --source-dir ior_material_list --output-dir dist
# behaviour diff old vs new (must be byte-identical for refactors)
git archive HEAD ior_material_list | tar -x -C /tmp/old
blender -b --factory-startup --python tests/behaviour_dump.py -- --addon /tmp/old/ior_material_list --out /tmp/old.json
blender -b --factory-startup --python tests/behaviour_dump.py -- --addon ior_material_list --out /tmp/new.json
cmp /tmp/old.json /tmp/new.json
# data refresh (python 3.11+, network)
python tools/update_ior_data.py --check ; python tools/update_ior_data.py
```
Windows Blender: `C:\Program Files\Blender Foundation\Blender 5.3\blender.exe`.

## Architecture / data flow
`ior_data.py` (generated tuples) → `register()` adds `WindowManager` props → timer `_populate_fresh` (0.1 s) and `load_post` `_on_load` fill `wm.ior_items` / `wm.ior_metals` → `IOR_UL_materials.filter_items` (search/source/sort, every redraw) → `IOR_OT_copy` writes `wm.clipboard` (3 decimals; Min/Mid/Max for ranges) / `IOR_OT_apply_metal` writes n,k to Metallic BSDF (PHYSICAL_CONDUCTOR) or F0 color + Metallic=1 to Principled, else adds a Metallic BSDF.
- `MATERIALS` row: `(name, ior, max_ior|None, category, source)`; `METALS` row: `(name, n_rgb, k_rgb)`.
- Source ids: `balyberdin`, `pixelandpoly`, `blenderit` — must exist in `SOURCE_SITES` and the `ior_source` enum (tested).

## Rules
- Never edit `ior_data.py` by hand; change `tools/update_ior_data.py` (`NAME_FIXES`, `BLENDERIT_EXTRA`, parsers) and regenerate.
- Operator/Panel docstrings are user tooltips: put developer notes in `#` comments.
- No `bl_info`; metadata lives in `blender_manifest.toml` only. Bump `version` there for releases.
- `unregister()` must undo everything `register()` does, including the pending timer.
- Keep text files LF (`.gitattributes`). Keep `ior_material_list/LICENSE` identical to `LICENSE`.
- Test with `BLENDER_USER_RESOURCES` (and `TEMP`/`TMP` for windowed runs) pointing at scratch dirs; never the user's profile or running Blender.

## Pitfalls found here
- Headless `-b`: timers never fire (call `_populate_all()`), `wm.clipboard` always `''`, no areas/UI. Tests use `tests/helpers.py` stand-ins (`WMProxy`, `fake_context`, `FakeOp`, `FakeLayout`) and call `execute`/`draw`/`filter_items` unbound.
- Blender 5.3: `node.inputs["Name"]` misses hidden sockets (Metallic BSDF IOR/Extinction while not PHYSICAL_CONDUCTOR). Set mode first or match `socket.identifier`.
- `bpy.types.UIList` has no `bitflag_filter_item` attribute outside a real list; tests use `1 << 30`.
- Release workflow must `git fetch` the tag explicitly; `actions/checkout` drops the annotated tag message. Lightweight tags are rejected.

## How changes were verified (1.2.0 → 1.3.0)
- Baseline 1.2.0: 33 tests, 32 pass (timer bug failing). After: 34/34 pass.
- Behaviour dump old vs new byte-identical; mutation check (tolerance 0.05→0.051, reversed sort, label text) each detected.
- Generator reproduces previous `MATERIALS`/`METALS` exactly from saved pages.
- Built zip installed into a scratch profile; windowed smoke test: list filled by timer, real clipboard `2.422`, metal applied, no pending timer after unregister.

## Release checklist
1. Bump `version` in `ior_material_list/blender_manifest.toml`; update the static Release badge in `README.md`.
2. Tests pass locally and on CI (`tests.yml`).
3. `git tag -a vX.Y.Z -m "vX.Y.Z" -m "notes"` → `git push origin vX.Y.Z`.
4. `release.yml`: tests → checks tag == manifest version → builds → `gh release create` with zip and tag message.
5. Check the release page has `ior_material_list-X.Y.Z.zip`.

## Git setup
- `main` only; remote `origin` = `https://github.com/mttfntn/ior-material-list-blender.git`.
- Small commits; message trailer `Co-Authored-By` when written by an assistant.
- `.gitignore`: `*.zip`, `dist/`, `__pycache__/`; `.scratch-profile/` is also ignored.
