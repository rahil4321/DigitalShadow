"""Outcome accounting; deposits are liabilities until applied or refunded."""
from models import WorldState


def calculate_operating_profit(state: WorldState) -> float:
    """Recognized operating result, excluding procurement of unsold inventory assets."""
    return round(
        state.metrics.revenue_recognized
        - state.metrics.cogs
        - state.metrics.penalties_incurred
        - state.metrics.shipment_losses
        - state.metrics.supplier_fees_incurred,
        2,
    )


def evaluate_scenario(state: WorldState) -> dict:
    ending_inventory = {
        sku: item.qty for sku, item in state.inventory.items()
    }
    outstanding_deposits = round(sum(o.deposit_received for o in state.active_orders), 2)
    ending_cash = round(state.cash, 2)
    ending_inventory_assets = round(state.inventory_asset_value, 2)
    return {
        "final_cash": ending_cash,
        "operating_profit": calculate_operating_profit(state),
        "sla_compliance_pct": (
            round(state.metrics.sla_compliance_pct, 1)
            if state.metrics.sla_compliance_pct is not None else None
        ),
        "penalties": round(state.metrics.penalties_incurred, 2),
        "shipment_losses": round(state.metrics.shipment_losses, 2),
        "supplier_fees_incurred": round(state.metrics.supplier_fees_incurred, 2),
        "customer_deposits_received": round(state.metrics.customer_deposits_received, 2),
        "customer_deposits_applied": round(state.metrics.customer_deposits_applied, 2),
        "customer_deposits_refunded": round(state.metrics.customer_deposits_refunded, 2),
        "outstanding_customer_deposits": outstanding_deposits,
        "ending_inventory_asset_value": ending_inventory_assets,
        "ending_inventory_units": ending_inventory,
        "cash_plus_inventory_assets": round(ending_cash + ending_inventory_assets, 2),
        "net_assets_after_customer_advances": round(
            ending_cash + ending_inventory_assets - outstanding_deposits, 2
        ),
        "is_solvent": state.cash >= 0,
        # Current demo scenario always has at least one order; all() is retained for multi-order cases.
        "sla_met": all(o.status == "fulfilled" for o in state.active_orders),
    }
