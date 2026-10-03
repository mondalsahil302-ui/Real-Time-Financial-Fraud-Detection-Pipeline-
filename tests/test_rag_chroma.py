import chromadb


def test_chroma_collection_upsert_is_idempotent(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path / "db"))
    collection = client.get_or_create_collection("paysim_cases")
    for _ in range(2):
        collection.upsert(ids=["case_1"], documents=["historical transfer"], metadatas=[{"label": "fraud"}], embeddings=[[1.0, 0.0]])
    assert collection.count() == 1
    assert collection.get(ids=["case_1"])["metadatas"][0]["label"] == "fraud"
