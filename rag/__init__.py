"""Retrieval augmented generation vector database utilities."""
import numpy as np

# Ensure NumPy 2.x backward compatibility for dependencies like chromadb 0.4.x
for _alias, _target in [("float_", np.float64), ("int_", np.int64), ("uint", np.uint64)]:
    if not hasattr(np, _alias):
        setattr(np, _alias, _target)
