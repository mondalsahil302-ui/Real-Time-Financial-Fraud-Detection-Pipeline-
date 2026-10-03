import pandas as pd

from rag.paysim_processor import iter_case_documents, paysim_id, row_document


def make_row(old_origin, new_origin, old_destination="10.00", new_destination="10.00"):
    return {
        "step": "3", "type": "TRANSFER", "amount": "200.00", "nameOrig": "C1",
        "oldbalanceOrg": old_origin, "newbalanceOrig": new_origin,
        "nameDest": "C2", "oldbalanceDest": old_destination, "newbalanceDest": new_destination,
        "isFraud": "1", "isFlaggedFraud": "0", "source_row_id": "10",
    }


def test_balance_depletion_is_derived_from_positive_to_zero():
    text, metadata = row_document(make_row("100.00", "0.00", "20.00", "220.00"), "fraud")
    assert "Origin account balance was depleted to zero after the transaction." in text
    assert "Origin balance before: 100.00" in text
    assert "Origin balance after: 0.00" in text
    assert metadata["origin_balance_depleted"] is True
    assert metadata["destination_balance_increased"] is True
    assert metadata["destination_balance_unchanged"] is False
    assert metadata["balance_change_amount"] == "-100.00"


def test_already_zero_balance_is_not_described_as_depleted():
    text, metadata = row_document(make_row("0.00", "0.00"), "fraud")
    assert "Origin account had zero balance before and after the transaction." in text
    assert "depleted to zero" not in text
    assert metadata["origin_balance_depleted"] is False
    assert metadata["origin_balance_unchanged"] is True
    assert metadata["balance_change_amount"] == "0.00"


def test_partial_balance_reduction_describes_actual_values_without_depletion():
    text, metadata = row_document(make_row("100.00", "40.00"), "fraud")
    assert "Origin account balance decreased from 100.00 to 40.00." in text
    assert "depleted to zero" not in text
    assert metadata["origin_balance_depleted"] is False
    assert metadata["origin_balance_unchanged"] is False
    assert metadata["balance_change_amount"] == "-60.00"


def test_unchanged_origin_and_destination_balances_are_reported():
    text, metadata = row_document(make_row("30.00", "30.00", "50.00", "50.00"), "fraud")
    assert "Origin account balance was unchanged at 30.00 before and after the transaction." in text
    assert "Destination account balance was unchanged at 50.00." in text
    assert metadata["origin_balance_unchanged"] is True
    assert metadata["destination_balance_unchanged"] is True
    assert metadata["destination_balance_increased"] is False


def test_document_values_and_ids_are_preserved_and_deterministic():
    text, metadata = row_document(make_row("100.00", "0.00"), "fraud")
    assert "Amount: 200.00" in text
    assert metadata["amount"] == "200.00"
    assert metadata["step"] == "3"
    assert metadata["transaction_type"] == "TRANSFER"
    assert paysim_id("fraud", "10") == paysim_id("fraud", "10")


def test_chunked_processing_creates_fraud_normal_and_profiles(tmp_path):
    path = tmp_path / "small.csv"
    pd.DataFrame([
        [1, "TRANSFER", 100.0, "C1", 100.0, 0.0, "C2", 0.0, 100.0, 1, 0],
        [1, "PAYMENT", 5.0, "C3", 20.0, 15.0, "M1", 0.0, 0.0, 0, 0],
        [2, "CASH_OUT", 10.0, "C2", 100.0, 90.0, "M2", 0.0, 0.0, 0, 0],
    ], columns=["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig", "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud", "isFlaggedFraud"]).to_csv(path, index=False)
    docs, counts = iter_case_documents(path, chunk_size=2, max_normal=1, max_profiles=10, progress=False)
    docs = list(docs)
    assert counts == {"rows_processed": 3, "fraud_documents": 1, "normal_documents": 1, "account_profiles": 2}
    assert len({doc[0] for doc in docs}) == len(docs)
    assert any(meta["document_type"] == "account_behavior_profile" for _, _, meta in docs)
