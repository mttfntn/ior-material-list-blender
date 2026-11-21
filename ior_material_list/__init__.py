"""IOR Material List — searchable index-of-refraction table in the Shader Editor.

Shader Editor > Sidebar (N) > IOR tab.
Data: https://balyberdin.com/tools/ior-list/, https://pixelandpoly.com/ior.html,
https://community.blender.it/forums/topic/indice-ior-per-materiale/
"""

bl_info = {
    "name": "IOR Material List",
    "author": "Matteo Fontana",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "Shader Editor > Sidebar > IOR",
    "description": "Searchable list of material IOR values; copy them to the clipboard",
    "category": "Material",
}

import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, StringProperty)

from .ior_data import MATERIALS, METALS

SOURCE_SITES = {
    "balyberdin": "balyberdin.com",
    "pixelandpoly": "pixelandpoly.com",
    "blenderit": "community.blender.it",
}

# --------------------------------------------------------------------------- data

class IORItem(bpy.types.PropertyGroup):
    # `name` is inherited
    ior: FloatProperty(precision=3)
    ior_max: FloatProperty(precision=3)  # 0 = no range
    category: StringProperty()
    source: StringProperty()


class IORMetal(bpy.types.PropertyGroup):
    n: FloatVectorProperty(size=3, precision=3)
    k: FloatVectorProperty(size=3, precision=3)


def _populate(wm, force=False):
    if (not force and len(wm.ior_items) == len(MATERIALS) and len(wm.ior_metals) == len(METALS)):
        return
    wm.ior_items.clear()
    for name, ior, ior_max, cat, src in MATERIALS:
        it = wm.ior_items.add()
        it.name, it.ior, it.ior_max = name, ior, ior_max or 0.0
        it.category = cat or "Misc"
        it.source = src
    wm.ior_metals.clear()
    for name, n, k in METALS:
        m = wm.ior_metals.add()
        m.name, m.n, m.k = name, n, k


def _populate_all(force=False):
    for wm in bpy.data.window_managers:
        _populate(wm, force)
    return None  # one-shot timer


def _populate_fresh():
    # after (re)install the list may hold stale data from an older version
    return _populate_all(force=True)


@persistent
def _on_load(_):
    _populate_all()


# --------------------------------------------------------------------------- helpers

def _value_for(item, mode):
    if item.ior_max <= 0 or mode == "MIN":
        return item.ior
    if mode == "MAX":
        return item.ior_max
    return round((item.ior + item.ior_max) / 2.0, 4)


def _target_nodes(context):
    tree = getattr(context.space_data, "edit_tree", None)
    if tree is None:
        return None, []
    nodes = [n for n in tree.nodes if n.select]
    if not nodes and tree.nodes.active:
        nodes = [tree.nodes.active]
    return tree, nodes


def _metal_f0(n, k):
    """Normal-incidence reflectance of a conductor (used as Principled base color)."""
    return tuple(((a - 1) ** 2 + b ** 2) / ((a + 1) ** 2 + b ** 2) for a, b in zip(n, k))


# --------------------------------------------------------------------------- UI lists

class IOR_UL_materials(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        split = row.split(factor=0.58)
        split.label(text=item.name)
        val = f"{item.ior:.3f}" if item.ior_max <= 0 else f"{item.ior:.3f}–{item.ior_max:.3f}"
        split.label(text=val)
        op = row.operator(IOR_OT_copy.bl_idname, text="", icon="COPYDOWN", emboss=False)
        op.index = index

    def draw_filter(self, context, layout):
        wm = context.window_manager
        row = layout.row(align=True)
        row.prop(wm, "ior_source", text="")
        row.prop(wm, "ior_sort", text="")

    def filter_items(self, context, data, propname):
        wm = context.window_manager
        items = getattr(data, propname)
        query = wm.ior_search.strip().lower()
        num = None
        try:
            num = float(query)
        except ValueError:
            pass
        src = wm.ior_source

        flags = []
        for it in items:
            ok = src == "ALL" or it.source == src
            if ok and query:
                if num is not None:
                    hi = it.ior_max if it.ior_max > 0 else it.ior
                    tol = 0.005 if "." in query and len(query.split(".")[1]) >= 2 else 0.05
                    ok = it.ior - tol <= num <= hi + tol
                else:
                    hay = f"{it.name} {it.category}".lower()
                    ok = all(w in hay for w in query.split())
            flags.append(self.bitflag_filter_item if ok else 0)

        if wm.ior_sort == "NAME":
            order = bpy.types.UI_UL_list.sort_items_by_name(items, "name")
        elif wm.ior_sort == "IOR":
            srt = sorted(range(len(items)), key=lambda i: items[i].ior)
            order = [0] * len(items)
            for pos, i in enumerate(srt):
                order[i] = pos
        else:
            order = []
        return flags, order


class IOR_UL_metals(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name, icon="SHADING_RENDERED")
        op = row.operator(IOR_OT_apply_metal.bl_idname, text="", icon="CHECKMARK", emboss=False)
        op.index = index

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        query = context.window_manager.ior_search.strip().lower()
        try:
            float(query)
            query = ""  # numeric search only applies to dielectrics
        except ValueError:
            pass
        flags = [self.bitflag_filter_item if (not query or all(w in it.name.lower() for w in query.split())) else 0
                 for it in items]
        return flags, []


# --------------------------------------------------------------------------- operators

class IOR_OT_copy(bpy.types.Operator):
    """Copy the selected IOR value to the clipboard"""
    bl_idname = "node.ior_copy"
    bl_label = "Copy IOR"

    index: IntProperty(default=-1)

    def execute(self, context):
        wm = context.window_manager
        idx = self.index if self.index >= 0 else wm.ior_index
        if not 0 <= idx < len(wm.ior_items):
            return {"CANCELLED"}
        wm.ior_index = idx
        item = wm.ior_items[idx]
        value = _value_for(item, wm.ior_range_mode)
        wm.clipboard = f"{value:.3f}"
        self.report({"INFO"}, f"Copied {item.name}: {value:.3f}")
        return {"FINISHED"}


class IOR_OT_apply_metal(bpy.types.Operator):
    """Apply this metal: Metallic BSDF gets physical-conductor n/k, Principled BSDF gets the matching F0 color"""
    bl_idname = "node.ior_apply_metal"
    bl_label = "Apply Metal"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == "NODE_EDITOR"

    def execute(self, context):
        wm = context.window_manager
        idx = self.index if self.index >= 0 else wm.ior_metal_index
        if not 0 <= idx < len(wm.ior_metals):
            return {"CANCELLED"}
        wm.ior_metal_index = idx
        metal = wm.ior_metals[idx]
        n, k = tuple(metal.n), tuple(metal.k)

        tree, nodes = _target_nodes(context)
        if tree is None:
            return {"CANCELLED"}
        count = 0
        for node in nodes:
            if node.bl_idname == "ShaderNodeBsdfMetallic":
                node.fresnel_type = "PHYSICAL_CONDUCTOR"
                node.inputs["IOR"].default_value[:3] = n
                node.inputs["Extinction"].default_value[:3] = k
                count += 1
            elif node.bl_idname == "ShaderNodeBsdfPrincipled":
                node.inputs["Base Color"].default_value[:3] = _metal_f0(n, k)
                node.inputs["Metallic"].default_value = 1.0
                count += 1
        if not count and wm.ior_metal_add_node:
            node = tree.nodes.new("ShaderNodeBsdfMetallic")
            node.label = metal.name
            node.fresnel_type = "PHYSICAL_CONDUCTOR"
            node.inputs["IOR"].default_value[:3] = n
            node.inputs["Extinction"].default_value[:3] = k
            node.location = context.space_data.cursor_location
            for x in tree.nodes:
                x.select = False
            node.select = True
            tree.nodes.active = node
            count = 1
        if not count:
            self.report({"WARNING"}, "Select a Metallic BSDF or Principled BSDF node")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Applied {metal.name}")
        return {"FINISHED"}


# --------------------------------------------------------------------------- panels

class IOR_PT_base:
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "IOR"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == "ShaderNodeTree"


class IOR_PT_panel(IOR_PT_base, bpy.types.Panel):
    bl_label = "IOR Material List"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        layout.prop(wm, "ior_search", text="", icon="VIEWZOOM")
        if not wm.ior_items:
            layout.label(text="Loading list…", icon="INFO")
            return

        layout.template_list("IOR_UL_materials", "", wm, "ior_items", wm, "ior_index", rows=12)

        if 0 <= wm.ior_index < len(wm.ior_items):
            item = wm.ior_items[wm.ior_index]
            box = layout.box()
            col = box.column(align=True)
            col.label(text=item.name, icon="MATERIAL")
            if item.ior_max > 0:
                col.label(text=f"IOR {item.ior:.3f} – {item.ior_max:.3f}")
                box.row().prop(wm, "ior_range_mode", expand=True)
            else:
                col.label(text=f"IOR {item.ior:.3f}")
            src = SOURCE_SITES.get(item.source, item.source)
            col.label(text=f"{item.category} · {src}")
            box.operator(IOR_OT_copy.bl_idname, text="Copy to Clipboard", icon="COPYDOWN").index = -1


class IOR_PT_metals(IOR_PT_base, bpy.types.Panel):
    bl_label = "Metals (n, k)"
    bl_parent_id = "IOR_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        layout.template_list("IOR_UL_metals", "", wm, "ior_metals", wm, "ior_metal_index", rows=6)
        if 0 <= wm.ior_metal_index < len(wm.ior_metals):
            m = wm.ior_metals[wm.ior_metal_index]
            col = layout.column(align=True)
            col.label(text="n  " + "  ".join(f"{v:.3f}" for v in m.n))
            col.label(text="k  " + "  ".join(f"{v:.3f}" for v in m.k))
        layout.prop(wm, "ior_metal_add_node")
        layout.operator(IOR_OT_apply_metal.bl_idname, icon="CHECKMARK").index = -1


# --------------------------------------------------------------------------- register

classes = (IORItem, IORMetal, IOR_UL_materials, IOR_UL_metals, IOR_OT_copy,
           IOR_OT_apply_metal, IOR_PT_panel, IOR_PT_metals)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    WM = bpy.types.WindowManager
    WM.ior_items = CollectionProperty(type=IORItem)
    WM.ior_metals = CollectionProperty(type=IORMetal)
    WM.ior_index = IntProperty(default=-1)
    WM.ior_metal_index = IntProperty(default=0)
    WM.ior_search = StringProperty(name="Search", description="Search by name/category, or type a number to find materials with that IOR",
                                   options={"TEXTEDIT_UPDATE"})
    WM.ior_source = EnumProperty(name="Source", items=[
        ("ALL", "All Sources", ""),
        ("balyberdin", "Balyberdin (curated)", "balyberdin.com/tools/ior-list"),
        ("pixelandpoly", "Pixel & Poly (A–Z)", "pixelandpoly.com/ior.html"),
        ("blenderit", "Blender Italia (extra)", "community.blender.it/forums/topic/indice-ior-per-materiale"),
    ])
    WM.ior_sort = EnumProperty(name="Sort", items=[
        ("NONE", "Default Order", ""), ("NAME", "Sort by Name", ""), ("IOR", "Sort by IOR", "")])
    WM.ior_range_mode = EnumProperty(name="Range", items=[
        ("MIN", "Min", "Use the lower value"), ("MID", "Mid", "Use the midpoint"), ("MAX", "Max", "Use the upper value")])
    WM.ior_metal_add_node = BoolProperty(name="Add Metallic BSDF if none selected", default=True)

    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_populate_fresh, first_interval=0.1)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    WM = bpy.types.WindowManager
    for p in ("ior_items", "ior_metals", "ior_index", "ior_metal_index", "ior_search",
              "ior_source", "ior_sort", "ior_range_mode", "ior_metal_add_node"):
        delattr(WM, p)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
