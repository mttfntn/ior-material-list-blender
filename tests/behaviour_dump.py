"""Record everything the add-on does into one JSON file, for before/after comparisons.

    blender -b --factory-startup --python tests/behaviour_dump.py -- --addon DIR --out FILE

Run it on two versions of the add-on (for example the last commit, extracted with
``git archive``, and the working tree) and compare the two files: any difference is
a change in behaviour. It covers the registered classes and properties, the loaded
data, search/sort results for many inputs, every copy and metal action, and the
UI calls made by every draw function.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

from helpers import (FILTER_FLAG, FakeLayout, FakeOp, WMProxy, _plain, draw_panel,  # noqa: E402
                     fake_context, load_addon, new_material, script_args)

QUERIES = ["", " ", "glass", "GLASS", "  Glass  ", "water", "honey water", "gem", "liquids", "misc",
           "metal", "oil, clove", "zzz", "%", "1", "1.", "1.3", "1.33", "1.333", "1.3333", "2.4", "2.42",
           "0.2", "4", "4.01", "-1", "1e0", "nan", "inf", ".5", "1,5", "garnet", "demantoid", "gold",
           "silver", "steel", "a", "e", "(liquid)", "20deg"]
SOURCES = ["ALL", "balyberdin", "pixelandpoly", "blenderit", "refractiveindex"]
SORTS = ["NONE", "NAME", "IOR"]


def sock(node, identifier):
    # inputs["Name"] does not find hidden sockets in Blender 5.3 (e.g. Metallic BSDF's IOR
    # while it is in F82 mode), so look sockets up by identifier.
    return next(s for s in node.inputs if s.identifier == identifier)


def rna_props(cls_rna, names):
    out = {}
    for n in names:
        p = cls_rna.properties[n]
        d = {"type": p.type, "name": p.name, "description": p.description,
             "options": sorted(p.is_never_none and ["NEVER_NONE"] or [])}
        if p.type == "ENUM":
            d["items"] = [[e.identifier, e.name, e.description] for e in p.enum_items]
            d["default"] = p.default
        elif p.type in {"INT", "FLOAT", "BOOLEAN", "STRING"}:
            d["default"] = _plain(p.default_array[:] if getattr(p, "is_array", False) else p.default)
        if p.type == "STRING":
            d["textedit_update"] = "TEXTEDIT_UPDATE" in getattr(p, "options", set())
        out[n] = d
    return out


def class_meta(cls):
    keys = ["bl_idname", "bl_label", "bl_options", "bl_space_type", "bl_region_type", "bl_category",
            "bl_parent_id", "bl_description"]
    meta = {k: _plain(getattr(cls, k)) for k in keys if hasattr(cls, k)}
    meta["tooltip"] = (cls.__doc__ or "").strip()
    meta["bases"] = [b.__name__ for b in cls.__mro__[1:4]]
    if hasattr(cls, "bl_rna"):
        meta["props"] = sorted(p.identifier for p in cls.bl_rna.properties if p.identifier != "rna_type")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addon", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(script_args())

    a = load_addon(args.addon)
    wm = bpy.context.window_manager
    S = type("S", (), {"bitflag_filter_item": FILTER_FLAG})()
    dump = {}

    dump["classes"] = {c.__name__: class_meta(c) for c in a.classes}
    wm_props = sorted(p for p in bpy.types.WindowManager.bl_rna.properties.keys() if p.startswith("ior_"))
    dump["wm_props"] = rna_props(bpy.types.WindowManager.bl_rna, wm_props)
    dump["handlers_load_post"] = [f.__name__ for f in bpy.app.handlers.load_post if f.__module__.startswith(a.__name__)]
    dump["source_sites"] = a.SOURCE_SITES

    dump["items"] = [[i.name, round(i.ior, 6), round(i.ior_max, 6), i.category, i.source] for i in wm.ior_items]
    dump["metals"] = [[m.name, [round(v, 6) for v in m.n], [round(v, 6) for v in m.k]] for m in wm.ior_metals]

    # search / sort
    flt = {}
    for q in QUERIES:
        for src in SOURCES:
            for srt in SORTS:
                wm.ior_search, wm.ior_source, wm.ior_sort = q, src, srt
                flags, order = a.IOR_UL_materials.filter_items(S, bpy.context, wm, "ior_items")
                flt[f"{q!r}|{src}|{srt}"] = [[i for i, f in enumerate(flags) if f], list(order)]
        wm.ior_search = q
        flags, order = a.IOR_UL_metals.filter_items(S, bpy.context, wm, "ior_metals")
        flt[f"metals|{q!r}"] = [[i for i, f in enumerate(flags) if f], list(order)]
    wm.ior_search, wm.ior_source, wm.ior_sort = "", "ALL", "NONE"
    dump["filter"] = flt

    # copy, every item x every range mode, plus "use the list selection" and bad indices
    copies = []
    for mode in ("MIN", "MID", "MAX"):
        for idx in list(range(len(wm.ior_items))) + [-1, len(wm.ior_items), 10 ** 6]:
            wm.ior_index = 3
            proxy = WMProxy(wm)
            proxy.ior_range_mode = mode
            op = FakeOp(idx)
            res = a.IOR_OT_copy.execute(op, fake_context(proxy))
            copies.append([mode, idx, sorted(res), proxy.clipboard, op.reports, wm.ior_index])
    wm.ior_range_mode = "MIN"
    wm.ior_index = -1
    proxy = WMProxy(wm)
    op = FakeOp(-1)
    copies.append(["no selection", sorted(a.IOR_OT_copy.execute(op, fake_context(proxy))), proxy.clipboard])
    dump["copy"] = copies

    # metals: every metal x every node-selection scenario
    metal_runs = []
    scenarios = ["metallic", "principled", "both", "output only", "nothing", "nothing no-add", "active only", "no tree"]
    for mi in list(range(len(wm.ior_metals))) + [-1, 99]:
        for sc in scenarios:
            mat = new_material()
            tree = mat.node_tree
            pr = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
            out = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
            me = tree.nodes.new("ShaderNodeBsdfMetallic")
            sel = {"metallic": [me], "principled": [pr], "both": [me, pr], "output only": [out]}.get(sc, [])
            for n in tree.nodes:
                n.select = n in sel
            tree.nodes.active = me if sc == "active only" else None
            wm.ior_metal_add_node = sc != "nothing no-add"
            wm.ior_metal_index = 2
            op = FakeOp(mi)
            res = a.IOR_OT_apply_metal.execute(op, fake_context(wm, None if sc == "no tree" else tree))
            nodes = []
            for n in sorted(tree.nodes, key=lambda n: n.name):
                rec = {"id": n.bl_idname, "label": n.label, "select": n.select, "loc": [round(v, 3) for v in n.location]}
                if n.bl_idname == "ShaderNodeBsdfMetallic":
                    rec["fresnel"] = n.fresnel_type
                    rec["ior"] = [round(v, 6) for v in sock(n, "IOR").default_value]
                    rec["ext"] = [round(v, 6) for v in sock(n, "Extinction").default_value]
                if n.bl_idname == "ShaderNodeBsdfPrincipled":
                    rec["base"] = [round(v, 6) for v in sock(n, "Base Color").default_value]
                    rec["metallic"] = round(sock(n, "Metallic").default_value, 6)
                nodes.append(rec)
            act = tree.nodes.active
            metal_runs.append([mi, sc, sorted(res), op.reports, wm.ior_metal_index, nodes, act.bl_idname if act else None])
            bpy.data.materials.remove(mat)
    wm.ior_metal_add_node = True
    dump["apply_metal"] = metal_runs

    # polls
    dump["polls"] = {
        "panel shader": bool(a.IOR_PT_panel.poll(fake_context(wm))),
        "panel geometry": bool(a.IOR_PT_panel.poll(fake_context(wm, tree_type="GeometryNodeTree"))),
        "metals panel shader": bool(a.IOR_PT_metals.poll(fake_context(wm))),
        "metal op node editor": bool(a.IOR_OT_apply_metal.poll(fake_context(wm))),
        "metal op 3d view": bool(a.IOR_OT_apply_metal.poll(fake_context(wm, space_type="VIEW_3D"))),
    }

    # drawing
    draws = {}
    ranged = next(i for i, it in enumerate(wm.ior_items) if it.ior_max > 0)
    for idx in [-1, 0, ranged, len(wm.ior_items) - 1, len(wm.ior_items)]:
        for mode in ("MIN", "MAX"):
            wm.ior_index, wm.ior_range_mode = idx, mode
            draws[f"panel idx={idx} {mode}"] = draw_panel(a.IOR_PT_panel, fake_context(wm))
    wm.ior_range_mode = "MIN"
    for idx in [-1, 0, len(wm.ior_metals) - 1, len(wm.ior_metals)]:
        for add in (True, False):
            wm.ior_metal_index, wm.ior_metal_add_node = idx, add
            draws[f"metals idx={idx} add={add}"] = draw_panel(a.IOR_PT_metals, fake_context(wm))
    wm.ior_metal_add_node = True
    rows = []
    for i, it in enumerate(wm.ior_items):
        lay = FakeLayout()
        a.IOR_UL_materials.draw_item(None, bpy.context, lay, wm, it, 0, wm, "ior_index", i)
        rows.append(lay.calls)
    draws["material rows"] = rows
    rows = []
    for i, m in enumerate(wm.ior_metals):
        lay = FakeLayout()
        a.IOR_UL_metals.draw_item(None, bpy.context, lay, wm, m, 0, wm, "ior_metal_index", i)
        rows.append(lay.calls)
    draws["metal rows"] = rows
    lay = FakeLayout()
    a.IOR_UL_materials.draw_filter(None, bpy.context, lay)
    draws["material filter"] = lay.calls
    draws["metal filter defined"] = "draw_filter" in a.IOR_UL_metals.__dict__
    saved = list(wm.ior_items)  # noqa: F841 (keep references alive while cleared)
    wm.ior_items.clear()
    draws["panel empty list"] = draw_panel(a.IOR_PT_panel, fake_context(wm))
    a._populate_all()
    dump["draw"] = draws

    # f0 helper over a grid
    dump["f0"] = [[round(v, 9) for v in a._metal_f0((n / 4, n / 3, n / 2), (k, k / 2, k / 3))]
                  for n in range(1, 9) for k in range(0, 9)]

    # load_post + register/unregister cycle
    wm.ior_items.clear()
    a._on_load(None)
    dump["after load_post"] = len(wm.ior_items)
    a.unregister()
    dump["after unregister"] = {
        "props left": sorted(p for p in bpy.types.WindowManager.bl_rna.properties.keys() if p.startswith("ior_")),
        "classes registered": [c.__name__ for c in a.classes if c.is_registered],
        "load_post left": [f.__name__ for f in bpy.app.handlers.load_post if f.__module__.startswith(a.__name__)],
    }
    a.register()
    a._populate_all()
    dump["after re-register"] = [len(wm.ior_items), len(wm.ior_metals)]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=1, ensure_ascii=False, sort_keys=True)
    print(f"DUMP written {args.out} ({os.path.getsize(args.out)} bytes)")


main()
