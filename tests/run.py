"""Entry point: run the test suite inside headless Blender.

    blender -b --factory-startup --python-exit-code 1 --python tests/run.py -- [--addon DIR]

Exits with a non-zero code when a test fails (thanks to --python-exit-code).
"""

import argparse
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402
import test_addon  # noqa: E402

parser = argparse.ArgumentParser(prog="run.py")
parser.add_argument("--addon", default=helpers.DEFAULT_ADDON_DIR, help="add-on folder to test")
args = parser.parse_args(helpers.script_args())

test_addon.load(args.addon)
suite = unittest.defaultTestLoader.loadTestsFromModule(test_addon)
result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
print(f"RESULT tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}")
if not result.wasSuccessful():
    raise SystemExit(1)
