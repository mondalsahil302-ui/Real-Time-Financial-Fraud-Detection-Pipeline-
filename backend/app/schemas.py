from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=1, le=10_000)
    delay: float = Field(ge=0, le=5)
    source: Literal["frontend_simulator"] = "frontend_simulator"


class ManualTransaction(BaseModel):
    """A validated input event using the existing PaySim/Spark wire names."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    step: int = Field(ge=0, le=2_147_483_647)
    event_step: int | None = Field(default=None, ge=0, le=2_147_483_647)
    transaction_type: Literal["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"] = Field(alias="type")
    amount: float = Field(ge=0, le=1e15, allow_inf_nan=False)
    origin_account: str = Field(alias="nameOrig", min_length=1, max_length=128)
    old_balance_origin: float = Field(alias="oldbalanceOrg", ge=0, le=1e15, allow_inf_nan=False)
    new_balance_origin: float = Field(alias="newbalanceOrig", ge=0, le=1e15, allow_inf_nan=False)
    destination_account: str = Field(alias="nameDest", min_length=1, max_length=128)
    old_balance_destination: float = Field(alias="oldbalanceDest", ge=0, le=1e15, allow_inf_nan=False)
    new_balance_destination: float = Field(alias="newbalanceDest", ge=0, le=1e15, allow_inf_nan=False)

    def kafka_payload(self) -> dict:
        payload = self.model_dump(by_alias=True)
        payload["event_step"] = self.event_step if self.event_step is not None else self.step
        return payload


class AssistantChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=2000)
    transaction_id: str | None = Field(default=None, max_length=128)
    conversation_id: str | None = Field(default=None, max_length=128)
    include_cassandra: bool = True
    include_fraud_knowledge: bool = True
    include_paysim_cases: bool = True
