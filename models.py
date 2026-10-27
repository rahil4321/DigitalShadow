"""Validated data models shared by the simulator and API."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    # Reject extra/unexpected keys and non-finite floats at every trust boundary.
    model_config = ConfigDict(
        validate_assignment=True,
        allow_inf_nan=False,
        extra="forbid",
    )


class Supplier(Model):
    id: str = Field(min_length=1, max_length=80)
    status: Literal["active", "delayed", "offline"] = "active"
    lead_time_days: int = Field(ge=1, le=30)
    # Probability that an individual delivery attempt succeeds; not an on-time guarantee.
    reliability: float = Field(ge=0.0, le=1.0)
    delay_variance_days: int = Field(default=2, ge=1, le=7)
    # Incremental per-unit supplier premium/fee. It is paid upfront and expensed immediately.
    per_unit_fee: float = Field(default=0, ge=0, le=10_000_000)


class SKU(Model):
    qty: int = Field(default=0, ge=0, le=1_000_000)
    unit_cost: float = Field(gt=0)
    unit_price: float = Field(gt=0)


class Order(Model):
    id: str = Field(min_length=1, max_length=80)
    sku: str = Field(min_length=1, max_length=80)
    qty: int = Field(gt=0, le=1_000_000)
    priority: Literal["high", "normal", "low"] = "normal"
    created_tick: int = Field(default=0, ge=0)
    deadline_tick: int = Field(gt=0)
    # In the current scenario this is charged when an order is cancelled after its deadline.
    penalty_per_day: float = Field(default=0, ge=0)
    status: Literal["pending", "fulfilled", "cancelled"] = "pending"
    # Outstanding advance credit against this order; cleared when applied/refunded.
    deposit_received: float = Field(default=0, ge=0)


class Metrics(Model):
    # Undefined until at least one order reaches a terminal outcome.
    sla_compliance_pct: Optional[float] = Field(default=None, ge=0, le=100)
    revenue_recognized: float = Field(default=0, ge=0)
    cogs: float = Field(default=0, ge=0)
    penalties_incurred: float = Field(default=0, ge=0)
    shipment_losses: float = Field(default=0, ge=0)
    customer_deposits_received: float = Field(default=0, ge=0)
    customer_deposits_applied: float = Field(default=0, ge=0)
    customer_deposits_refunded: float = Field(default=0, ge=0)
    # Supplier expedite/handling fee per unit, expensed immediately rather than capitalized into inventory.
    supplier_fees_incurred: float = Field(default=0, ge=0)
    total_orders_processed: int = Field(default=0, ge=0)
    sla_breaches: int = Field(default=0, ge=0)


class IncomingShipment(Model):
    id: str = Field(min_length=1, max_length=80)
    sku: str = Field(min_length=1, max_length=80)
    qty: int = Field(gt=0, le=1_000_000)
    unit_cost: float = Field(gt=0)
    expected_arrival_tick: int = Field(ge=0)
    supplier_id: str = Field(min_length=1, max_length=80)
    status: Literal["in_transit", "delayed", "arrived", "failed"] = "in_transit"


class WorldState(Model):
    current_tick: int = Field(default=0, ge=0)
    # Cash may be negative in a simulated outcome so solvency risk can be measured.
    cash: float
    inventory_asset_value: float = Field(default=0, ge=0)
    metrics: Metrics = Field(default_factory=Metrics)
    inventory: Dict[str, SKU]
    suppliers: Dict[str, Supplier]
    active_orders: List[Order]
    incoming_shipments: List[IncomingShipment] = Field(default_factory=list)
    action_log: List[str] = Field(default_factory=list)
    # Explicit hypothetical assumptions, never presented as observed customer behavior.
    customer_deposit_amount: float = Field(default=2000.0, ge=0)
    customer_deposit_acceptance_probability: float = Field(default=0.80, ge=0, le=1)

    @model_validator(mode="after")
    def initialize_or_check_inventory_asset_basis(self):
        # Assets include both units on hand and purchased goods still in transit.
        on_hand = sum(item.qty * item.unit_cost for item in self.inventory.values())
        in_transit = sum(
            shipment.qty * shipment.unit_cost for shipment in self.incoming_shipments
            if shipment.status in ("in_transit", "delayed")
        )
        expected_basis = round(on_hand + in_transit, 2)
        if "inventory_asset_value" not in self.model_fields_set:
            self.inventory_asset_value = expected_basis
        elif abs(self.inventory_asset_value - expected_basis) > 0.02:
            raise ValueError(
                "inventory_asset_value must match the cost basis of on-hand and in-transit inventory "
                f"(expected ${expected_basis:.2f}, received ${self.inventory_asset_value:.2f})."
            )
        return self


class Strategy(Model):
    name: str = Field(min_length=1, max_length=80)
    action: Optional[Literal["place_supplier_order", "request_customer_deposit_and_order"]] = None
    args: List[Any] = Field(default_factory=list)
