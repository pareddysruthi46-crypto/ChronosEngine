
import argparse

from chronosengine.production_pipeline import ProductionPipeline
from chronosengine.ui.terminal_ui import (
    launch_dashboard,
    parse_args as parse_dashboard_args,
)


def main():
    parser = argparse.ArgumentParser(
        description="ChronosEngine production-style pipeline dashboard"
    )

    # Pipeline configuration
    parser.add_argument("--orders", type=int, default=1000)
    parser.add_argument("--rate", type=int, default=1000)
    parser.add_argument("--order-capacity", type=int, default=1000)
    parser.add_argument("--trade-capacity", type=int, default=1000)

    parser.add_argument(
        "--database",
        default="trade_ledger.db",
    )

    # News simulation configuration
    parser.add_argument(
        "--news-profile",
        choices=("none", "earnings"),
        default="none",
    )

    parser.add_argument("--burst-rate", type=int, default=None)
    parser.add_argument("--burst-duration", type=float, default=5.0)
    parser.add_argument("--news-delay", type=float, default=1.0)

    args = parser.parse_args()

    # Validate arguments before creating pipeline resources.
    if args.orders < 0:
        parser.error("--orders must be >= 0")

    if args.rate <= 0:
        parser.error("--rate must be > 0")

    if args.order_capacity <= 0:
        parser.error("--order-capacity must be > 0")

    if args.trade_capacity <= 0:
        parser.error("--trade-capacity must be > 0")

    if args.burst_rate is not None and args.burst_rate <= 0:
        parser.error("--burst-rate must be > 0")

    if args.burst_duration <= 0:
        parser.error("--burst-duration must be > 0")

    if args.news_delay < 0:
        parser.error("--news-delay must be >= 0")

    # Create the integrated production pipeline.
    pipeline = ProductionPipeline(
        count=args.orders,
        rate=args.rate,
        order_capacity=args.order_capacity,
        trade_capacity=args.trade_capacity,
        database_path=args.database,
        news_profile=args.news_profile,
        burst_rate=args.burst_rate,
        burst_duration=args.burst_duration,
        news_delay=args.news_delay,
    )

    # Use the existing terminal dashboard configuration.
    dashboard_options = parse_dashboard_args([])

    try:
        pipeline.start()

        print(
            "Starting ChronosEngine production-style pipeline..."
        )
        print("Press Q in the dashboard to stop.")

        # Share the actual pipeline objects with the dashboard.
        launch_dashboard(
            dashboard_options,
            engine=pipeline.engine,
            order_buffer=pipeline.order_buffer,
            trade_buffer=pipeline.trade_buffer,
        )

    finally:
        # Drain and stop all pipeline workers.
        pipeline.stop()

    print("\nPipeline stopped.")
    print("Orders processed:", pipeline.finished_orders)
    print(
        "Trades submitted for persistence:",
        pipeline.finished_trades,
    )
    print("Database:", args.database)


if __name__ == "__main__":
    main()
