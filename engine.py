"""Deterministic business rules for a single-action procurement scenario."""
import random
import uuid
from typing import Optional
from models import WorldState, IncomingShipment

ORDER_ACTIONS = {"place_supplier_order", "request_customer_deposit_and_order"}
CENT = 2


def _money(value: float) -> float:
    """Round monetary state transitions to cents to avoid floating-point drift."""
    return round(float(value) + 1e-9, CENT)


def _pending_orders_for_sku(state: WorldState, sku: str):
    return [o for o in state.active_orders if o.status == "pending" and o.sku == sku]


def _required_qty(state: WorldState, sku: str) -> int:
    """Demand not covered by on-hand stock or a live inbound shipment."""
    pending = sum(o.qty for o in _pending_orders_for_sku(state, sku))
    available = state.inventory[sku].qty if sku in state.inventory else 0
    inbound = sum(
        shipment.qty for shipment in state.incoming_shipments
        if shipment.sku == sku and shipment.status in ("in_transit", "delayed")
    )
    return max(0, pending - available - inbound)


def _available_deposit(state: WorldState, sku: str, qty: int) -> float:
    """The same capped advance amount used by validation and execution."""
    if sku not in state.inventory:
        return 0.0
    pending_due = sum(
        max(0.0, order.qty * state.inventory[sku].unit_price - order.deposit_received)
        for order in _pending_orders_for_sku(state, sku)
    )
    return _money(min(state.customer_deposit_amount, qty * state.inventory[sku].unit_price, pending_due))


def validate_action(state: WorldState, action: Optional[str], args: list) -> tuple[bool, str]:
    if action is None:
        if not isinstance(args, list) or args:
            return False, "Wait strategy must have no arguments."
        return True, "Valid no-op strategy."
    if not isinstance(action, str) or action not in ORDER_ACTIONS:
        return False, "Unsupported action."
    if not isinstance(args, list) or len(args) != 3:
        return False, "Order action requires [sku, quantity, supplier_id]."
    sku, qty, supplier_id = args
    if not isinstance(sku, str) or sku not in state.inventory:
        return False, "Unknown SKU."
    if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 1000:
        return False, "Quantity must be an integer from 1 to 1000."
    if not isinstance(supplier_id, str) or supplier_id not in state.suppliers:
        return False, "Unknown supplier."
    supplier = state.suppliers[supplier_id]
    if supplier.status == "offline":
        return False, "Supplier is offline."

    required_qty = _required_qty(state, sku)
    if required_qty <= 0:
        return False, f"There is no uncovered pending demand for {sku}; duplicate restocking is not allowed."
    if qty < required_qty:
        return False, (
            f"Quantity {qty} cannot satisfy uncovered demand of {required_qty} {sku}; "
            "partial fulfilment is not implemented."
        )
    if qty > required_qty:
        return False, (
            f"Quantity {qty} exceeds current pending demand available to procure (uncovered demand {required_qty} {sku}); "
            "future demand is not modelled in this scenario."
        )

    supplier_fee = _money(qty * supplier.per_unit_fee)
    cost = _money(qty * state.inventory[sku].unit_cost + supplier_fee)
    available_cash = state.cash
    if action == "request_customer_deposit_and_order":
        # An advance is a contingent financing strategy, not a way to inflate a
        # recommendation when ordinary procurement is already affordable.
        if state.cash >= cost:
            return False, "Customer advance is only available when existing cash cannot fund the full procurement."
        deposit = _available_deposit(state, sku, qty)
        if deposit <= 0:
            return False, "No collectible customer advance is configured for this scenario."
        available_cash = _money(available_cash + deposit)
    if cost > available_cash:
        return False, f"Unaffordable: order costs ${cost:.2f}, available funding is ${available_cash:.2f}."
    return True, "Valid action."


def place_supplier_order(state: WorldState, sku: str, qty: int, supplier_id: str) -> WorldState:
    ok, reason = validate_action(state, "place_supplier_order", [sku, qty, supplier_id])
    if not ok:
        state.action_log.append(f"REJECTED: {reason}")
        return state
    supplier = state.suppliers[supplier_id]
    sku_data = state.inventory[sku]
    inventory_cost = _money(qty * sku_data.unit_cost)
    supplier_fee = _money(qty * supplier.per_unit_fee)
    total_outflow = _money(inventory_cost + supplier_fee)
    state.cash = _money(state.cash - total_outflow)
    state.metrics.supplier_fees_incurred = _money(state.metrics.supplier_fees_incurred + supplier_fee)
    # Append the shipment before changing its asset basis so the WorldState invariant
    # sees a consistent in-transit asset balance during assignment validation.
    state.incoming_shipments.append(IncomingShipment(
        id=str(uuid.uuid4())[:8], sku=sku, qty=qty, unit_cost=sku_data.unit_cost,
        expected_arrival_tick=state.current_tick + supplier.lead_time_days,
        supplier_id=supplier_id,
    ))
    state.inventory_asset_value = _money(state.inventory_asset_value + inventory_cost)
    state.action_log.append(
        f"SIMULATED ORDER: {qty} {sku} from {supplier_id}; inventory asset basis ${inventory_cost:.2f}, "
        f"supplier fee ${supplier_fee:.2f}, total cash outflow ${total_outflow:.2f}."
    )
    return state


def _credit_deposit_to_orders(state: WorldState, sku: str, amount: float) -> None:
    """Allocate one accepted advance across pending orders without over-crediting any order."""
    remaining = _money(amount)
    sku_price = state.inventory[sku].unit_price
    orders = sorted(
        _pending_orders_for_sku(state, sku),
        key=lambda order: (order.created_tick, order.deadline_tick, order.id),
    )
    for order in orders:
        if remaining <= 0:
            break
        order_value = _money(order.qty * sku_price)
        capacity = max(0.0, _money(order_value - order.deposit_received))
        credit = _money(min(capacity, remaining))
        order.deposit_received = _money(order.deposit_received + credit)
        remaining = _money(remaining - credit)
    if remaining > 0.01:
        raise ValueError("Deposit allocation exceeded pending customer balances.")


def apply_strategy(state: WorldState, action: Optional[str], args: list, rng: random.Random) -> WorldState:
    ok, reason = validate_action(state, action, args)
    if not ok:
        state.action_log.append(f"REJECTED: {reason}")
        return state
    if action is None:
        state.action_log.append("DECISION: Preserve cash; no procurement was initiated.")
        return state

    sku, qty, supplier_id = args
    if action == "request_customer_deposit_and_order":
        accepted = rng.random() < state.customer_deposit_acceptance_probability
        if not accepted:
            state.action_log.append(
                "SIMULATED NEGOTIATION: Customer declined the advance; no order was placed."
            )
            return state
        deposit = _available_deposit(state, sku, qty)
        _credit_deposit_to_orders(state, sku, deposit)
        state.cash = _money(state.cash + deposit)
        state.metrics.customer_deposits_received = _money(
            state.metrics.customer_deposits_received + deposit
        )
        state.action_log.append(
            f"SIMULATED NEGOTIATION: Customer advance accepted (${deposit:.2f}); it is not recognized as revenue yet."
        )
    return place_supplier_order(state, sku, qty, supplier_id)


def _write_off_shipment(state: WorldState, shipment: IncomingShipment, reason: str) -> None:
    shipment.status = "failed"
    loss = _money(shipment.qty * shipment.unit_cost)
    state.inventory_asset_value = _money(max(0.0, state.inventory_asset_value - loss))
    state.metrics.shipment_losses = _money(state.metrics.shipment_losses + loss)
    state.action_log.append(f"SHIPMENT LOSS: {reason}; recognized loss ${loss:.2f}.")


def process_shipments(state: WorldState, rng: random.Random) -> WorldState:
    remaining = []
    for shipment in state.incoming_shipments:
        if shipment.status in ("arrived", "failed"):
            continue
        if state.current_tick < shipment.expected_arrival_tick:
            remaining.append(shipment)
            continue
        supplier = state.suppliers.get(shipment.supplier_id)
        sku_data = state.inventory.get(shipment.sku)
        if supplier is None:
            _write_off_shipment(state, shipment, "supplier missing")
            continue
        if sku_data is None:
            _write_off_shipment(state, shipment, "SKU missing")
            continue

        # Every scheduled attempt succeeds with supplier.reliability. If it fails,
        # there is a 10% conditional chance of permanent non-refundable loss; otherwise retry later.
        if rng.random() < supplier.reliability:
            shipment.status = "arrived"
            sku_data.qty += shipment.qty
            state.action_log.append(f"SHIPMENT ARRIVED: {shipment.id} on Day {state.current_tick}.")
        elif rng.random() < 0.10:
            _write_off_shipment(state, shipment, "non-refundable delivery failure")
        else:
            shipment.status = "delayed"
            shipment.expected_arrival_tick = state.current_tick + rng.randint(1, supplier.delay_variance_days)
            remaining.append(shipment)
            state.action_log.append(
                f"SHIPMENT DELAYED: {shipment.id}; revised expected arrival Day {shipment.expected_arrival_tick}."
            )
    state.incoming_shipments = remaining
    return state


def fulfill_orders(state: WorldState) -> WorldState:
    # Stable priority order prevents list order from deciding which VIP-like order gets stock first.
    priority_rank = {"high": 0, "normal": 1, "low": 2}
    for order in sorted(state.active_orders, key=lambda o: (priority_rank[o.priority], o.deadline_tick, o.created_tick, o.id)):
        if order.status != "pending":
            continue
        sku_data = state.inventory.get(order.sku)
        # The deadline day is inclusive, and arrivals are processed before fulfilment.
        if sku_data and sku_data.qty >= order.qty and state.current_tick <= order.deadline_tick:
            sku_data.qty -= order.qty
            cogs = _money(order.qty * sku_data.unit_cost)
            revenue = _money(order.qty * sku_data.unit_price)
            state.inventory_asset_value = _money(max(0.0, state.inventory_asset_value - cogs))
            state.metrics.cogs = _money(state.metrics.cogs + cogs)
            # Advance cash came in earlier: only collect the remaining sale balance now.
            balance_due = _money(revenue - order.deposit_received)
            if balance_due < -0.01:
                raise ValueError(f"Customer advance exceeds sale value for order {order.id}.")
            state.cash = _money(state.cash + max(0.0, balance_due))
            state.metrics.revenue_recognized = _money(state.metrics.revenue_recognized + revenue)
            state.metrics.customer_deposits_applied = _money(
                state.metrics.customer_deposits_applied + order.deposit_received
            )
            order.deposit_received = 0.0
            state.metrics.total_orders_processed += 1
            order.status = "fulfilled"
            state.action_log.append(
                f"CUSTOMER ORDER FULFILLED: revenue ${revenue:.2f}; COGS ${cogs:.2f}."
            )
        elif state.current_tick > order.deadline_tick:
            order.status = "cancelled"
            state.metrics.sla_breaches += 1
            state.metrics.total_orders_processed += 1
            # Cancel at the first tick after the SLA deadline in normal time progression.
            # If callers skip ticks, charge penalty_per_day times the elapsed late days.
            if order.deposit_received:
                refund = _money(order.deposit_received)
                state.cash = _money(state.cash - refund)
                state.metrics.customer_deposits_refunded = _money(
                    state.metrics.customer_deposits_refunded + refund
                )
                order.deposit_received = 0.0
                state.action_log.append(f"CUSTOMER ADVANCE REFUNDED: ${refund:.2f}.")
            late_days = state.current_tick - order.deadline_tick
            penalty = _money(order.penalty_per_day * late_days)
            state.cash = _money(state.cash - penalty)
            state.metrics.penalties_incurred = _money(state.metrics.penalties_incurred + penalty)
            state.action_log.append(f"SLA BREACH: ${penalty:.2f} penalty charged at cancellation.")
    if state.metrics.total_orders_processed:
        state.metrics.sla_compliance_pct = round(
            100.0 * (1.0 - state.metrics.sla_breaches / state.metrics.total_orders_processed), 1
        )
    return state


def advance_time(state: WorldState, ticks: int = 1, seed: int = 42) -> WorldState:
    if isinstance(ticks, bool) or not isinstance(ticks, int) or not 0 <= ticks <= 365:
        raise ValueError("ticks must be an integer between 0 and 365")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    for _ in range(ticks):
        state.current_tick += 1
        process_shipments(state, rng)
        fulfill_orders(state)
    return state
