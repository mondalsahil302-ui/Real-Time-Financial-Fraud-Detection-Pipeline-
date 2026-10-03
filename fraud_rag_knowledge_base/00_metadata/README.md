# Fraud RAG Knowledge Base v2

This knowledge base is built from the three supplied fraud-risk documents.

## Source hierarchy
1. RBI Master Direction on Fraud Risk Management, 15 July 2024 — primary regulatory source.
2. PwC August 2024 analysis — secondary explanatory source.
3. Older fraud classification/reporting guidance — historical reference.

## Data boundary
Customer/account transaction history is not stored here. It remains in Cassandra.

This knowledge base is for semantic regulatory and investigation knowledge that will later be embedded and stored in ChromaDB.

## Version warning
The RBI material in this build is a 2024 source snapshot. Before any production/legal/compliance use, validate against the latest applicable RBI rules.
