from rag.retrieval.paysim_retriever import PaySimRetriever


class Collection:
    def __init__(self):
        self.count_filter = None
        self.query_options = None

    def count(self):
        return 1

    def query(self, **kwargs):
        self.query_options = kwargs
        label = kwargs["where"]["label"]
        return {
            "ids": [[f"doc-{label}"]],
            "documents": [[f"PaySim {label} example"]],
            "metadatas": [[{
                "label": label,
                "source_row_id": f"row-{label}",
                "transaction_type": "TRANSFER",
                "amount": 25.0,
            }]],
            "distances": [[0.1]],
        }


class Embedder:
    def encode(self, values):
        return [[0.1, 0.2]]


def test_paysim_retriever_filters_each_label_separately():
    collection = Collection()
    retriever = PaySimRetriever(collection=collection, embedder=Embedder())

    result = retriever.retrieve(
        {"transaction_type": "TRANSFER", "amount": 25},
        query="historical comparison",
        label="fraud",
    )

    assert collection.query_options["where"] == {"label": "fraud"}
    assert result[0]["metadata"]["label"] == "fraud"
