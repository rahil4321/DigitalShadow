"""CLI smoke demonstration; does not call any external service."""
from api import create_base_state
from simulator import simulate_strategy


def run_cli_simulation():
    for disruption in (False, True):
        state = create_base_state(scenario_delay_days=6, disruption=disruption)
        if state.cash >= 5_000:
            options = [
                ("Preserve Cash", None, []),
                ("Fast Supplier", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"]),
                ("Standard Supplier", "place_supplier_order", ["LAPTOP", 10, "SLOW_SUPPLIER"]),
            ]
        else:
            options = [
                ("Preserve Cash", None, []),
                ("Customer Advance + Fast", "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"]),
                ("Customer Advance + Standard", "request_customer_deposit_and_order", ["LAPTOP", 10, "SLOW_SUPPLIER"]),
            ]
        print(f"\nScenario: {'budget crisis' if disruption else 'baseline'}, starting cash=${state.cash:.2f}")
        for name, action, args in options:
            result = simulate_strategy(state, name, action, args, num_runs=1000)
            print(
                f"{name}: feasible={result['feasible']}, "
                f"expected operating profit=${result['expected_profit']}, "
                f"SLA success={result['sla_success_probability']}% "
                f"(95% Wilson CI {result['sla_success_ci95']['lower']}–{result['sla_success_ci95']['upper']}%), "
                f"ending cash >= $0={result['solvency_probability']}% "
                f"(95% Wilson lower bound {result['solvency_ci95']['lower']}%), "
                f"p05 ending cash=${result['p05_cash']}, "
                f"worst observed cash=${result['worst_case_cash']}"
            )


if __name__ == "__main__":
    run_cli_simulation()
