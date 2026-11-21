"""Shared helpers for the headless test suite and the behaviour dump.

Both scripts run *inside* Blender (``blender -b --factory-startup --python ...``).
Headless Blender has no editor areas, no clipboard and no UI layouts, so this
module provides small stand-ins:

* ``load_addon(path)``   imports the add-on package from a folder and registers it.
* ``WMProxy``            wraps the real WindowManager but keeps ``clipboard`` in Python
                         (the real clipboard is always empty in background mode).
* ``fake_context``       a context with a Shader Editor ``space_data`` pointing at a node tree.
* ``FakeOp``             a stand-in ``self`` for calling ``Operator.execute`` directly.
* ``FakeLayout``         records every UI call a ``draw`` function makes, as plain data.
"""

import importlib
import os
import sys
from types import SimpleNamespace

import bpy

# Value Blender passes to UIList.filter_items as ``self.bitflag_filter_item`` (UILST_FLT_ITEM).
FILTER_FLAG = 1 << 30

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ADDON_DIR = os.path.join(REPO_ROOT, "ior_material_list")


def script_args():
    """Arguments after ``--`` on the Blender command line."""
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def load_addon(addon_dir=DEFAULT_ADDON_DIR):
    """Import the add-on package found at ``addon_dir``, register it and fill the lists."""
    addon_dir = os.path.abspath(addon_dir)
    parent, name = os.path.split(addon_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    mod = importlib.import_module(name)
    mod.register()
    # The add-on fills its lists from a timer, which never fires in background mode.
    mod._populate_all()
    return mod


class WMProxy:
    """WindowManager stand-in: forwards everything to the real one except ``clipboard``."""

    def __init__(self, wm):
        object.__setattr__(self, "_wm", wm)
        object.__setattr__(self, "clipboard", "")

    def __getattr__(self, name):
        return getattr(self._wm, name)

    def __setattr__(self, name, value):
        if name == "clipboard":
            object.__setattr__(self, name, value)
        else:
            setattr(self._wm, name, value)


def fake_context(wm, tree=None, space_type="NODE_EDITOR", tree_type="ShaderNodeTree"):
    space = SimpleNamespace(type=space_type, tree_type=tree_type, edit_tree=tree,
                            cursor_location=(12.5, -40.0))
    return SimpleNamespace(window_manager=wm, space_data=space)


class FakeOp:
    """Stand-in ``self`` for ``SomeOperator.execute(self, context)``."""

    def __init__(self, index=-1):
        self.index = index
        self.reports = []

    def report(self, level, msg):
        self.reports.append([sorted(level), msg])


def _plain(v):
    """Make a value JSON-friendly (bpy structs become their type and name)."""
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted(_plain(x) for x in v)
    if isinstance(v, bpy.types.bpy_struct):
        return f"<{type(v).__name__} {getattr(v, 'name', '')}>"
    return repr(v)


class _OpProps:
    def __init__(self, record):
        object.__setattr__(self, "_record", record)

    def __setattr__(self, name, value):
        self._record.append(["set", name, _plain(value)])


class FakeLayout:
    """Records the calls a Panel/UIList ``draw`` makes, as nested lists."""

    def __init__(self):
        self.calls = []

    def _child(self, kind, args, kw):
        child = FakeLayout()
        self.calls.append([kind, _plain(list(args)), {k: _plain(v) for k, v in sorted(kw.items())}, child.calls])
        return child

    def row(self, *a, **kw):
        return self._child("row", a, kw)

    def column(self, *a, **kw):
        return self._child("column", a, kw)

    def box(self, *a, **kw):
        return self._child("box", a, kw)

    def split(self, *a, **kw):
        return self._child("split", a, kw)

    def label(self, *a, **kw):
        self.calls.append(["label", _plain(list(a)), {k: _plain(v) for k, v in sorted(kw.items())}])

    def prop(self, data, prop, **kw):
        self.calls.append(["prop", _plain(data), prop, {k: _plain(v) for k, v in sorted(kw.items())}])

    def template_list(self, *a, **kw):
        self.calls.append(["template_list", _plain(list(a)), {k: _plain(v) for k, v in sorted(kw.items())}])

    def operator(self, idname, **kw):
        rec = []
        self.calls.append(["operator", idname, {k: _plain(v) for k, v in sorted(kw.items())}, rec])
        return _OpProps(rec)


def draw_panel(panel_cls, context):
    """Run a Panel class's ``draw`` against a FakeLayout and return the recorded calls."""
    layout = FakeLayout()
    panel_cls.draw(SimpleNamespace(layout=layout), context)
    return layout.calls


def new_material(name="IOR_TEST"):
    """A fresh material with a node tree (Principled BSDF + Material Output)."""
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    return mat
