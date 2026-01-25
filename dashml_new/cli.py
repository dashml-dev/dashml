#!/usr/bin/env python3
"""
DashML CLI - Command-line interface for DashML
"""
import sys
import argparse
import subprocess
import threading
import json
from pathlib import Path
from core import DashMLEngine, ValidationError, DashMLWatcher
from transformers import TransformerRegistry
from transformers.streamlit import StreamlitTransformer
from transformers.plotly import PlotlyTransformer
from transformers.observable import ObservablePlotTransformer
from transformers.superset import SupersetTransformer


def register_builtin_transformers():
    """Register built-in transformers"""
    TransformerRegistry.register(StreamlitTransformer)
    TransformerRegistry.register(PlotlyTransformer)
    TransformerRegistry.register(ObservablePlotTransformer)
    TransformerRegistry.register(SupersetTransformer)


def build_command(args):
    """Handle the build command

    TODO: [SRP] This function does too much - file validation, loading, transformation, writing, AND running
    Consider splitting into: load_and_validate_spec(), generate_code(), write_output(), run_dashboard()
    """
    dashml_path = args.input
    target = args.target
    output_path = args.output

    # Check if input file exists
    # TODO: [Pythonic] Use pathlib consistently - Path.exists() over os.path.exists()
    # This is good! But also consider Path(dashml_path).is_file() for clarity
    if not Path(dashml_path).exists():
        print(f"Error: DashML file not found: {dashml_path}", file=sys.stderr)
        return 1

    # Load and validate spec
    print(f"Loading {dashml_path}...")
    engine = DashMLEngine()

    try:
        spec = engine.load(dashml_path)
    except ValidationError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading DashML file: {e}", file=sys.stderr)
        return 1

    print(f"✓ DashML spec validated successfully")

    # Get transformer
    try:
        # Special handling for Superset transformer - pass credentials
        if target == "superset":
            from transformers.superset import SupersetTransformer
            transformer = SupersetTransformer(
                superset_url=args.superset_url,
                username=args.superset_user,
                password=args.superset_password
            )
        else:
            transformer = TransformerRegistry.get(target)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Using transformer: {transformer.description}")

    # Handle database configuration for SQL datasources
    if spec["data"]["type"] == "sql":
        # Validate database arguments are provided
        required_db_args = ["db_type", "db_host", "db_port", "db_name", "db_user", "db_password"]
        missing_args = [arg for arg in required_db_args if not getattr(args, arg, None)]

        if missing_args:
            print(f"Error: SQL datasource requires database configuration arguments:", file=sys.stderr)
            for arg in missing_args:
                print(f"  --{arg.replace('_', '-')}", file=sys.stderr)
            return 1

        # Create database config
        db_config = {
            "type": args.db_type,
            "host": args.db_host,
            "port": args.db_port,
            "database": args.db_name,
            "user": args.db_user,
            "password": args.db_password
        }

        # Pass to transformer (if it has set_db_config method)
        if hasattr(transformer, "set_db_config"):
            transformer.set_db_config(db_config)
            print(f"✓ Database configuration set")

    # Handle BigQuery configuration
    elif spec["data"]["type"] == "bigquery":
        # Validate BigQuery arguments are provided
        if not getattr(args, "bq_project", None):
            print(f"Error: BigQuery datasource requires --bq-project argument", file=sys.stderr)
            return 1

        # Create BigQuery config
        bq_config = {
            "type": "bigquery",
            "project": args.bq_project,
            "credentials_path": getattr(args, "bq_credentials", None)
        }

        # Pass to transformer (if it has set_db_config method)
        if hasattr(transformer, "set_db_config"):
            transformer.set_db_config(bq_config)
            print(f"✓ BigQuery configuration set (project: {args.bq_project})")

    # Generate code
    try:
        code = transformer.build(spec)
    except Exception as e:
        print(f"Error generating code: {e}", file=sys.stderr)
        return 1

    print(f"✓ Code generated successfully")

    # Display warnings if any
    warnings = transformer.get_warnings()
    if warnings:
        print(f"\n⚠ Transformer warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    # Check if output is multi-file (JSON-encoded structure)
    is_multi_file = False
    try:
        output_data = json.loads(code)
        if isinstance(output_data, dict) and output_data.get("type") == "multi-file":
            is_multi_file = True
    except (json.JSONDecodeError, TypeError):
        # Not JSON or not multi-file - treat as regular single-file output
        pass

    # Write output (skip for Superset - it doesn't generate code)
    if target != "superset":
        if output_path:
            try:
                if is_multi_file:
                    # Multi-file output - create directory and write multiple files
                    output_dir = Path(output_path)
                    output_dir.mkdir(parents=True, exist_ok=True)

                    files = output_data.get("files", {})
                    for filename, content in files.items():
                        file_path = output_dir / filename
                        file_path.write_text(content, encoding="utf-8")
                        print(f"✓ Written: {file_path}")

                    print(f"\n✓ Multi-file output created in: {output_dir}")
                else:
                    # Single-file output - write normally
                    Path(output_path).write_text(code, encoding="utf-8")
                    print(f"✓ Output written to: {output_path}")
            except Exception as e:
                print(f"Error writing output: {e}", file=sys.stderr)
                return 1
        else:
            # Print to stdout
            if is_multi_file:
                print("\n⚠ Multi-file output cannot be printed to stdout. Use --output to specify a directory.")
                return 1
            else:
                print("\n--- Generated Code ---")
                print(code)

    # Run the dashboard if --run flag is set
    if args.run and output_path:
        print(f"\n🚀 Running dashboard...")
        run_command = transformer.get_run_command(output_path)
        print(f"Command: {run_command}\n")

        try:
            subprocess.run(run_command, shell=True, check=True)
        except KeyboardInterrupt:
            print("\n✓ Stopped")
            return 0
        except subprocess.CalledProcessError as e:
            print(f"Error: Command failed with exit code {e.returncode}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error running dashboard: {e}", file=sys.stderr)
            return 1

    return 0


def list_command(args):
    """Handle the list command"""
    transformers = TransformerRegistry.list_detailed()

    if not transformers:
        print("No transformers registered")
        return 0

    print("Available transformers:")
    for t in transformers:
        print(f"  {t['name']:15} - {t['description']}")

    return 0


def watch_command(args):
    """Handle the watch command"""
    dashml_path = args.input
    target = args.target
    output_path = args.output
    should_run = args.run

    # TODO: [DRY] This file validation logic is duplicated from build_command
    # Extract to: _validate_input_file(path: str) -> bool
    # Validate paths
    if not Path(dashml_path).exists():
        print(f"Error: DashML file not found: {dashml_path}", file=sys.stderr)
        return 1

    if not output_path:
        print("Error: --output is required for watch mode", file=sys.stderr)
        return 1

    # Get transformer
    try:
        transformer = TransformerRegistry.get(target)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"👀 Watch mode: {transformer.description}")
    print(f"📄 Input:  {dashml_path}")
    print(f"📝 Output: {output_path}")
    if should_run:
        print(f"🚀 Run: {transformer.get_run_command(output_path)}")
    print()

    # Define rebuild function
    # TODO: [Code Organization] Nested function - extract to module-level
    # This makes testing harder and duplicates logic from build_command
    # Fix: Extract common logic into _build_and_write(engine, transformer, dashml_path, output_path)
    def rebuild():
        """Rebuild the output file"""
        engine = DashMLEngine()

        try:
            # Load and validate
            spec = engine.load(dashml_path)
            print(f"✓ Spec validated")

            # Generate code
            code = transformer.build(spec)
            print(f"✓ Code generated ({len(code)} chars)")

            # Display warnings if any
            warnings = transformer.get_warnings()
            if warnings:
                print(f"⚠ Transformer warnings:")
                for warning in warnings:
                    print(f"  - {warning}")

            # Write output
            Path(output_path).write_text(code, encoding="utf-8")
            print(f"✓ Written to {output_path}")

        except ValidationError as e:
            print(f"✗ Validation Error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"✗ Error: {e}", file=sys.stderr)

    # Initial build
    print("Building initial version...")
    rebuild()
    print()

    # If --run flag, start watcher in background and run command
    if should_run:
        # Start watcher in background thread
        watcher = DashMLWatcher(dashml_path, rebuild, poll_interval=1.0)
        watcher_thread = threading.Thread(target=watcher.watch, daemon=True)
        watcher_thread.start()

        # Run the dashboard in foreground
        run_command = transformer.get_run_command(output_path)
        print(f"🚀 Running: {run_command}\n")

        try:
            subprocess.run(run_command, shell=True, check=True)
        except KeyboardInterrupt:
            print("\n✓ Stopped")
            return 0
        except subprocess.CalledProcessError as e:
            print(f"\nError: Command failed with exit code {e.returncode}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"\nError running dashboard: {e}", file=sys.stderr)
            return 1
    else:
        # Just watch (no run)
        try:
            watcher = DashMLWatcher(dashml_path, rebuild, poll_interval=1.0)
            watcher.watch()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"\nError: {e}", file=sys.stderr)
            return 1

    return 0


def main():
    """Main CLI entry point"""
    # Register built-in transformers
    register_builtin_transformers()

    # Create parser
    parser = argparse.ArgumentParser(
        description="DashML - Declarative dashboard language compiler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate Streamlit app
  dashml build dashboard.dashml --target streamlit --output app.py

  # Generate and run in one command
  dashml build dashboard.dashml --target streamlit --output app.py --run

  # Watch mode - auto-rebuild on changes
  dashml watch dashboard.dashml --target streamlit --output app.py

  # Watch AND run - the ultimate dev experience!
  dashml watch dashboard.dashml --target streamlit --output app.py --run

  # List available transformers
  dashml list
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build dashboard from DashML spec")
    build_parser.add_argument("input", help="Path to .dashml file")
    build_parser.add_argument(
        "--target", "-t",
        required=True,
        help="Target platform (e.g., streamlit, plotly)"
    )
    build_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: print to stdout)"
    )
    build_parser.add_argument(
        "--run", "-r",
        action="store_true",
        help="Run the dashboard after building (requires --output)"
    )
    build_parser.add_argument(
        "--superset-url",
        default="http://localhost:8088",
        help="Superset instance URL (for superset backend only)"
    )
    build_parser.add_argument(
        "--superset-user",
        help="Superset username (for superset backend only)"
    )
    build_parser.add_argument(
        "--superset-password",
        help="Superset password (for superset backend only)"
    )

    # Database arguments (for SQL datasources)
    build_parser.add_argument(
        "--db-type",
        choices=["postgresql", "mysql", "sqlite"],
        help="Database type (required for SQL datasources)"
    )
    build_parser.add_argument(
        "--db-host",
        help="Database host (required for SQL datasources)"
    )
    build_parser.add_argument(
        "--db-port",
        type=int,
        help="Database port (required for SQL datasources)"
    )
    build_parser.add_argument(
        "--db-name",
        help="Database name (required for SQL datasources)"
    )
    build_parser.add_argument(
        "--db-user",
        help="Database username (required for SQL datasources)"
    )
    build_parser.add_argument(
        "--db-password",
        help="Database password (required for SQL datasources)"
    )

    # BigQuery arguments (for BigQuery datasources)
    build_parser.add_argument(
        "--bq-project",
        help="Google Cloud project ID (required for BigQuery datasources)"
    )
    build_parser.add_argument(
        "--bq-credentials",
        help="Path to service account JSON credentials file (optional, uses default credentials if not provided)"
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List available transformers")

    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch .dashml file and rebuild on changes")
    watch_parser.add_argument("input", help="Path to .dashml file")
    watch_parser.add_argument(
        "--target", "-t",
        required=True,
        help="Target platform (e.g., streamlit, plotly)"
    )
    watch_parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output file path"
    )
    watch_parser.add_argument(
        "--run", "-r",
        action="store_true",
        help="Run the dashboard after building (watch continues in background)"
    )

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Execute command
    if args.command == "build":
        return build_command(args)
    elif args.command == "list":
        return list_command(args)
    elif args.command == "watch":
        return watch_command(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
