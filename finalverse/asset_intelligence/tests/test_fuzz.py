"""Fuzz and property tests. FVA_FUZZ_ITERATIONS raises the in-suite budget."""

from __future__ import annotations

import json
import os
import unittest

from helpers import fuzz, inspect_bytes, report

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:  # optional dev dependency
    given = None


class MutationFuzz(unittest.TestCase):
    def test_no_crashes(self):
        n = int(os.environ.get("FVA_FUZZ_ITERATIONS", "1500"))
        res = fuzz.campaign(n, seed=20261104, quiet=True)
        self.assertEqual(res["crashes"], [], res["crashes"][:1])
        self.assertGreater(len(res["statuses"]), 1)


if given is not None:
    KEYS = [
        "asset",
        "version",
        "scenes",
        "scene",
        "nodes",
        "children",
        "mesh",
        "skin",
        "meshes",
        "primitives",
        "attributes",
        "POSITION",
        "NORMAL",
        "JOINTS_0",
        "WEIGHTS_0",
        "TEXCOORD_0",
        "indices",
        "material",
        "materials",
        "accessors",
        "bufferViews",
        "buffers",
        "byteLength",
        "byteOffset",
        "byteStride",
        "count",
        "componentType",
        "type",
        "min",
        "max",
        "sparse",
        "skins",
        "joints",
        "inverseBindMatrices",
        "animations",
        "channels",
        "samplers",
        "target",
        "path",
        "input",
        "output",
        "interpolation",
        "images",
        "textures",
        "source",
        "uri",
        "mimeType",
        "extensionsUsed",
        "extensionsRequired",
        "extensions",
        "translation",
        "rotation",
        "scale",
        "matrix",
        "targets",
        "weights",
        "alphaMode",
    ]
    scalars = st.one_of(
        st.none(),
        st.booleans(),
        st.integers(-(2**40), 2**40),
        st.floats(allow_nan=False, allow_infinity=False),
        st.sampled_from(KEYS + ["2.0", "VEC3"]),
    )
    values = st.recursive(
        scalars,
        lambda c: st.one_of(st.lists(c, max_size=6), st.dictionaries(st.sampled_from(KEYS), c, max_size=6)),
        max_leaves=40,
    )
    docs = st.dictionaries(st.sampled_from(KEYS), values, max_size=12).map(lambda d: {**d, "asset": {"version": "2.0"}})

    class Properties(unittest.TestCase):
        @settings(
            max_examples=int(os.environ.get("FVA_HYPOTHESIS_EXAMPLES", "300")),
            deadline=None,
            suppress_health_check=list(HealthCheck),
        )
        @given(docs)
        def test_any_document_yields_a_deterministic_report(self, doc):
            data = json.dumps(doc).encode()
            r1 = report(inspect_bytes(data, "h.gltf"), generated_at="x")
            r2 = report(inspect_bytes(data, "h.gltf"), generated_at="x")
            json.dumps(r1, allow_nan=False)
            self.assertEqual(r1["report_digest"], r2["report_digest"])
            self.assertIn(r1["validation"]["status"], {"valid", "valid_exceeds_limits", "invalid", "refused"})


if __name__ == "__main__":
    unittest.main()
