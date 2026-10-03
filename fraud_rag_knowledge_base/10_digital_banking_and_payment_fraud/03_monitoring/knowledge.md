---
kb_version: kb_v2
topic: 10_digital_banking_and_payment_fraud
subtopic: 03_monitoring
source_type: primary_regulatory
source_file: RBI-FRAUD-RISK-MANAGEMENT-15-07-24.pdf
source_pages: [7, 8, 13, 14]
synthetic: false
---

# 03 Monitoring

## Purpose

Electronic banking, digital payment transactions, digital channels and monitoring.

## RAG role

This document is a source-grounded knowledge unit intended for semantic retrieval. It provides context for investigation and explanation. It does not replace the bank's own policies, competent investigation, or current legal/compliance review.

## Relevant terminology

digital, electronic banking, payment, UPI, wallet, real-time

## Source-grounded material

3.4.2 The design and specification of EWS system shall be robust and resilient 
to ensure that integrity of system is maintained, personal and financial data of 
customers are secure and transaction monitoring for prevention / detection of 
potential fraud is on real-time basis13.

3.4.3 The Data Analytics & MI Unit or other dedicated analytics set up in banks 
shall extensively monitor and analyse other banking / non- credit related 
transactions, more specifically the transactions through digital platforms and 
applications, in order to identify unusual patterns and activities which could alert 
the bank timely in initiating appropriate measures towards prevention of 
fraudulent activities.

CHAPTER VI26 
6.1 Reporting of Incidents of Fraud to Reserve Bank of India (RBI) 
To ensure uniformity and consistency while reporting incidents of fraud to RBI through 
Fraud Monitoring Returns (FMRs) using online portal, banks shall choose the most 
appropriate category from any one of the following: 
(i) Misappropriation of funds and criminal breach of trust; 
(ii) Fraudulent encashment through forged instruments; 
(iii) Manipulation of books of account s or through fictitious accounts, and 
conversion of property; 
(iv) Cheating by concealment of facts with the intention to deceive any person 
and cheating by impersonation; 
(v) Forgery with the intention to commit fraud by making any false 
documents/electronic records; 
(vi) Wilful falsification, destruction, alteration, mutilations of any book, 
electronic record, paper, writing, valuable security or account with intent 
to defraud; 
(vii) Fraudulent credit facilities extended for illegal gratification; 
(viii) Cash shortages on account of frauds; 
(ix) Fraudulent transactions involving foreign exchange; 
(x) Fraudulent electronic banking / digital payment related transactions 
committed on banks; and 
(xi) Other type of fraudulent activity not covered under any of the above.

[Page 14]
13 
 
6.2.2 Banks are required to report payment system related disputed / suspected 
or attempted fraudulent transactions to Central Payments Fraud Information 
Registry (CPFIR) 28, maintained by RBI .

## Data boundary

Do not store individual customer/account transaction history here. In this project, live account history is retrieved from Cassandra. This knowledge-base unit represents regulatory/domain knowledge.

## Retrieval questions this unit can support

- What does 03 monitoring mean in the RBI 2024 framework?
- What requirements or concepts are associated with 03 monitoring?
- What terminology should an investigation service use for this topic?
- What source-backed context should be supplied to an investigator or future LLM?

## Authority

The source is the RBI Master Direction dated 15 July 2024. Validate against later regulatory amendments before production use.
