import sys
import types

from rag.embedder import LocalEmbedder


def test_embedding_dimension_detected_from_model(monkeypatch):
    class FakeModel:
        def __init__(self, name, **kwargs):
            self.name = name
        def get_sentence_embedding_dimension(self):
            return 3
        def encode(self, texts, **kwargs):
            return [[1.0, 0.0, 0.0] for _ in texts]
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    embedder = LocalEmbedder("local-test")
    assert embedder.dimension == 3
    assert len(embedder.encode(["test"])[0]) == 3
