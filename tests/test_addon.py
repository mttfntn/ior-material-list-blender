"""Unit tests for the IOR Material List add-on, run inside headless Blender.

Start them with ``tests/run.py`` (see HANDOVER.md). The add-on is loaded from the
folder given with ``--addon`` (default: ``ior_material_list/`` in this repo).
"""

import os
import re
import tomllib
import unittest

import bpy

from helpers import (FILTER_FLAG, FakeLayout, FakeOp, WMProxy, draw_panel, fake_context,
                     load_addon, new_material)

ADDON = None  # set by run.py before the tests start
ADDON_DIR = None


def wm():
    return bpy.context.window_manager


def filtered(query, source="ALL", sort="NONE", list_cls="IOR_UL_materials", prop="ior_items",
             indices=False):
    """Run a UIList's filter_items like Blender does; return (visible names or indices, order)."""
    w = wm()
    w.ior_search, w.ior_source, w.ior_sort = query, source, sort
    try:
        cls = getattr(ADDON, list_cls)
        flags, order = cls.filter_items(type("S", (), {"bitflag_filter_item": FILTER_FLAG})(),
                                        bpy.context, w, prop)
    finally:
        w.ior_search, w.ior_source, w.ior_sort = "", "ALL", "NONE"
    items = getattr(w, prop)
    shown = [i for i, f in enumerate(flags) if f]
    return (shown if indices else [items[i].name for i in shown]), order


class TestData(unittest.TestCase):
    def test_material_rows(self):
        sources = {"balyberdin", "pixelandpoly", "blenderit"}
        seen = set()
        for row in ADDON.MATERIALS:
            self.assertEqual(len(row), 5, row)
            name, ior, ior_max, cat, src = row
            self.assertTrue(name.strip(), row)
            self.assertGreater(ior, 0, row)
            if ior_max is not None:
                self.assertGreater(ior_max, ior, row)
            self.assertIsInstance(cat, str)
            self.assertIn(src, sources, row)
            self.assertNotIn((name, src), seen, f"duplicate {name} in {src}")
            seen.add((name, src))

    def test_metal_rows(self):
        for name, n, k in ADDON.METALS:
            self.assertEqual((len(n), len(k)), (3, 3), name)
            self.assertTrue(all(v > 0 for v in n + k), name)

    def test_sources_have_labels(self):
        used = {row[4] for row in ADDON.MATERIALS}
        self.assertTrue(used <= set(ADDON.SOURCE_SITES))
        enum = {e.identifier for e in bpy.types.WindowManager.bl_rna.properties["ior_source"].enum_items}
        self.assertTrue(used <= enum)


class TestManifest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ADDON_DIR, "blender_manifest.toml"), "rb") as f:
            self.manifest = tomllib.load(f)

    def test_fields(self):
        m = self.manifest
        self.assertEqual(m["id"], "ior_material_list")
        self.assertEqual(m["type"], "add-on")
        self.assertRegex(m["version"], r"^\d+\.\d+\.\d+$")

    def test_license_shipped(self):
        # The package must carry the license; it must match the repo's copy.
        packaged = os.path.join(ADDON_DIR, "LICENSE")
        self.assertTrue(os.path.isfile(packaged), "LICENSE missing from the add-on folder")
        root = os.path.join(os.path.dirname(os.path.abspath(ADDON_DIR)), "LICENSE")
        if os.path.isfile(root):
            with open(packaged, "rb") as a, open(root, "rb") as b:
                self.assertEqual(a.read(), b.read(), "ior_material_list/LICENSE differs from LICENSE")

    def test_running_blender_is_supported(self):
        def ver(s):
            return tuple(int(x) for x in s.split("."))
        lo = ver(self.manifest["blender_version_min"])
        self.assertGreaterEqual(bpy.app.version, lo)
        if "blender_version_max" in self.manifest:  # exclusive upper bound
            self.assertLess(bpy.app.version, ver(self.manifest["blender_version_max"]))


class TestRegistration(unittest.TestCase):
    PROPS = ("ior_items", "ior_metals", "ior_index", "ior_metal_index", "ior_search",
             "ior_source", "ior_sort", "ior_range_mode", "ior_metal_add_node")

    def test_registered(self):
        for cls in ADDON.classes:
            self.assertTrue(cls.is_registered, cls.__name__)
        for p in self.PROPS:
            self.assertIn(p, bpy.types.WindowManager.bl_rna.properties)
        self.assertIn(ADDON._on_load, bpy.app.handlers.load_post)

    def test_unregister_register_cycle(self):
        ADDON.unregister()
        try:
            for cls in ADDON.classes:
                self.assertFalse(cls.is_registered, cls.__name__)
            for p in self.PROPS:
                self.assertNotIn(p, bpy.types.WindowManager.bl_rna.properties)
            self.assertNotIn(ADDON._on_load, bpy.app.handlers.load_post)
        finally:
            ADDON.register()
            ADDON._populate_all()
        self.assertEqual(len(wm().ior_items), len(ADDON.MATERIALS))

    def test_no_pending_timer_after_unregister(self):
        # A timer left behind would run after unregister and touch removed properties.
        ADDON.unregister()
        try:
            pending = [f for f in (getattr(ADDON, n, None) for n in dir(ADDON))
                       if callable(f) and bpy.app.timers.is_registered(f)]
            self.assertEqual(pending, [])
        finally:
            ADDON.register()
            ADDON._populate_all()


class TestPopulate(unittest.TestCase):
    def test_counts_and_values(self):
        w = wm()
        self.assertEqual(len(w.ior_items), len(ADDON.MATERIALS))
        self.assertEqual(len(w.ior_metals), len(ADDON.METALS))
        for it, (name, ior, ior_max, cat, src) in zip(w.ior_items, ADDON.MATERIALS):
            self.assertEqual(it.name, name)
            self.assertAlmostEqual(it.ior, ior, places=5)
            self.assertAlmostEqual(it.ior_max, ior_max or 0.0, places=5)
            self.assertEqual(it.category, cat or "Misc")
            self.assertEqual(it.source, src)

    def test_repopulates_after_change(self):
        w = wm()
        w.ior_items.remove(0)
        ADDON._populate_all()
        self.assertEqual(len(w.ior_items), len(ADDON.MATERIALS))
        w.ior_items[0].name = "changed"
        ADDON._populate_all(force=True)
        self.assertEqual(w.ior_items[0].name, ADDON.MATERIALS[0][0])

    def test_load_post_handler(self):
        wm().ior_items.clear()
        ADDON._on_load(None)
        self.assertEqual(len(wm().ior_items), len(ADDON.MATERIALS))


class TestSearch(unittest.TestCase):
    def test_words(self):
        names, _ = filtered("glass")
        self.assertIn("Standard Glass", names)
        items = wm().ior_items
        for i in filtered("glass", indices=True)[0]:
            self.assertIn("glass", f"{items[i].name} {items[i].category}".lower())
        self.assertEqual(filtered("GLASS")[0], names)          # case-insensitive
        self.assertIn("Honey, 13% water content", filtered("honey water")[0])  # all words
        self.assertEqual(filtered("zzzz-nothing")[0], [])

    def test_category(self):
        names, _ = filtered("liquids")
        self.assertIn("Water", names)

    def test_number(self):
        names, _ = filtered("1.333")
        self.assertIn("Water", names)
        self.assertIn("Diamond", filtered("2.4")[0])
        self.assertIn("Optical Glass", filtered("1.7")[0])     # inside a min–max range

    def test_source(self):
        names, _ = filtered("", source="blenderit")
        self.assertEqual(len(names), sum(1 for r in ADDON.MATERIALS if r[4] == "blenderit"))

    def test_sort(self):
        items = wm().ior_items
        _, order = filtered("", sort="IOR")
        ranked = sorted(range(len(items)), key=lambda i: order[i])
        iors = [items[i].ior for i in ranked]
        self.assertEqual(iors, sorted(iors))
        _, order = filtered("", sort="NAME")
        self.assertEqual(sorted(order), list(range(len(items))))
        self.assertEqual(filtered("", sort="NONE")[1], [])

    def test_metals(self):
        names, _ = filtered("gold", list_cls="IOR_UL_metals", prop="ior_metals")
        self.assertEqual(names, ["Gold"])
        names, _ = filtered("1.5", list_cls="IOR_UL_metals", prop="ior_metals")
        self.assertEqual(len(names), len(ADDON.METALS))        # numbers don't filter metals


class TestCopy(unittest.TestCase):
    def run_copy(self, index, mode="MIN"):
        w = WMProxy(wm())
        w.ior_range_mode = mode
        op = FakeOp(index)
        try:
            result = ADDON.IOR_OT_copy.execute(op, fake_context(w))
        finally:
            wm().ior_range_mode = "MIN"
        return result, w.clipboard, op.reports

    def idx(self, name):
        return next(i for i, it in enumerate(wm().ior_items) if it.name == name)

    def test_single_value(self):
        i = self.idx("Diamond")
        result, clip, reports = self.run_copy(i)
        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(clip, f"{ADDON.MATERIALS[i][1]:.3f}")
        self.assertEqual(wm().ior_index, i)
        self.assertEqual(reports[0][0], ["INFO"])

    def test_range_modes(self):
        i = self.idx("Optical Glass")
        lo, hi = ADDON.MATERIALS[i][1], ADDON.MATERIALS[i][2]
        self.assertEqual(self.run_copy(i, "MIN")[1], f"{lo:.3f}")
        self.assertEqual(self.run_copy(i, "MAX")[1], f"{hi:.3f}")
        self.assertEqual(self.run_copy(i, "MID")[1], f"{(lo + hi) / 2:.3f}")

    def test_uses_list_selection(self):
        i = self.idx("Water")
        wm().ior_index = i
        self.assertEqual(self.run_copy(-1)[1], "1.333")

    def test_out_of_range(self):
        self.assertEqual(self.run_copy(10 ** 6)[0], {"CANCELLED"})
        wm().ior_index = -1
        self.assertEqual(self.run_copy(-1)[0], {"CANCELLED"})


class TestApplyMetal(unittest.TestCase):
    def setUp(self):
        self.mat = new_material()
        self.tree = self.mat.node_tree
        self.gold = next(i for i, m in enumerate(wm().ior_metals) if m.name == "Gold")
        self.n, self.k = ADDON.METALS[self.gold][1], ADDON.METALS[self.gold][2]

    def tearDown(self):
        wm().ior_metal_add_node = True
        bpy.data.materials.remove(self.mat)

    def apply(self, tree=None):
        op = FakeOp(self.gold)
        res = ADDON.IOR_OT_apply_metal.execute(op, fake_context(wm(), tree or self.tree))
        return res, op.reports

    def select_only(self, *nodes):
        for n in self.tree.nodes:
            n.select = n in nodes

    def test_metallic_node(self):
        node = self.tree.nodes.new("ShaderNodeBsdfMetallic")
        self.select_only(node)
        self.assertEqual(self.apply()[0], {"FINISHED"})
        self.assertEqual(node.fresnel_type, "PHYSICAL_CONDUCTOR")
        for got, want in zip(node.inputs["IOR"].default_value, self.n):
            self.assertAlmostEqual(got, want, places=5)
        for got, want in zip(node.inputs["Extinction"].default_value, self.k):
            self.assertAlmostEqual(got, want, places=5)

    def test_principled_node(self):
        node = next(n for n in self.tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        self.select_only(node)
        self.assertEqual(self.apply()[0], {"FINISHED"})
        self.assertEqual(node.inputs["Metallic"].default_value, 1.0)
        for got, want in zip(node.inputs["Base Color"].default_value, ADDON._metal_f0(self.n, self.k)):
            self.assertAlmostEqual(got, want, places=5)

    def test_adds_node_when_nothing_selected(self):
        self.select_only()
        self.tree.nodes.active = None
        before = len(self.tree.nodes)
        self.assertEqual(self.apply()[0], {"FINISHED"})
        self.assertEqual(len(self.tree.nodes), before + 1)
        new = self.tree.nodes.active
        self.assertEqual((new.bl_idname, new.label), ("ShaderNodeBsdfMetallic", "Gold"))
        self.assertEqual(tuple(new.location), (12.5, -40.0))

    def test_cancel_without_add(self):
        wm().ior_metal_add_node = False
        out = next(n for n in self.tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        self.select_only(out)
        res, reports = self.apply()
        self.assertEqual(res, {"CANCELLED"})
        self.assertEqual(reports[0][0], ["WARNING"])

    def test_no_tree(self):
        op = FakeOp(self.gold)
        ctx = fake_context(wm(), None)
        self.assertEqual(ADDON.IOR_OT_apply_metal.execute(op, ctx), {"CANCELLED"})

    def test_f0_formula(self):
        # Silver-like conductor reflects almost everything; a dielectric n=1.5 reflects 4 %.
        self.assertAlmostEqual(ADDON._metal_f0((1.5,), (0.0,))[0], 0.04, places=6)


class TestPolls(unittest.TestCase):
    def test_panel_poll(self):
        self.assertTrue(ADDON.IOR_PT_panel.poll(fake_context(wm())))
        self.assertFalse(ADDON.IOR_PT_panel.poll(fake_context(wm(), tree_type="GeometryNodeTree")))

    def test_metal_poll(self):
        self.assertTrue(ADDON.IOR_OT_apply_metal.poll(fake_context(wm())))
        self.assertFalse(ADDON.IOR_OT_apply_metal.poll(fake_context(wm(), space_type="VIEW_3D")))


class TestDraw(unittest.TestCase):
    """Draw code can't run headless, so it is run against a recording layout."""

    def test_main_panel(self):
        w = wm()
        w.ior_index = next(i for i, it in enumerate(w.ior_items) if it.name == "Optical Glass")
        calls = draw_panel(ADDON.IOR_PT_panel, fake_context(w))
        flat = repr(calls)
        self.assertIn("template_list", flat)
        self.assertIn("ior_range_mode", flat)                  # ranged item shows Min/Mid/Max
        self.assertIn(ADDON.IOR_OT_copy.bl_idname, flat)
        self.assertNotIn("ior_apply'", flat)

    def test_main_panel_empty(self):
        w = wm()
        w.ior_items.clear()
        try:
            calls = draw_panel(ADDON.IOR_PT_panel, fake_context(w))
            self.assertIn("Loading", repr(calls))
        finally:
            ADDON._populate_all()

    def test_metals_panel(self):
        calls = draw_panel(ADDON.IOR_PT_metals, fake_context(wm()))
        self.assertIn(ADDON.IOR_OT_apply_metal.bl_idname, repr(calls))

    def test_list_rows(self):
        for i, it in enumerate(list(wm().ior_items)[:50]):
            lay = FakeLayout()
            ADDON.IOR_UL_materials.draw_item(None, bpy.context, lay, wm(), it, 0, wm(), "ior_index", i)
            self.assertIn(it.name, repr(lay.calls))
            self.assertTrue(re.search(r"\d\.\d{3}", repr(lay.calls)))


def load(addon_dir):
    global ADDON, ADDON_DIR
    ADDON_DIR = addon_dir
    ADDON = load_addon(addon_dir)
    return ADDON
