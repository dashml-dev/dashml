#!/usr/bin/env python3
"""
DashML CLI - Command-line interface for DashML
"""
import sys
import argparse
import subprocess
import threading
import json
import shutil
from pathlib import Path
from dashml_new.core import DashMLEngine, ValidationError, DashMLWatcher
from dashml_new.transformers import TransformerRegistry
from dashml_new.transformers.streamlit import StreamlitTransformer
from dashml_new.transformers.plotly import PlotlyTransformer
from dashml_new.transformers.observable import ObservablePlotTransformer
from dashml_new.transformers.superset import SupersetTransformer
from dashml_new.transformers.grafana import GrafanaTransformer
from dashml_new.transformers.vegalite import VegaLiteTransformer


def register_builtin_transformers():
    """Register built-in transformers"""
    TransformerRegistry.register(StreamlitTransformer)
    TransformerRegistry.register(PlotlyTransformer)
    TransformerRegistry.register(ObservablePlotTransformer)
    TransformerRegistry.register(SupersetTransformer)
    TransformerRegistry.register(GrafanaTransformer)
    TransformerRegistry.register(VegaLiteTransformer)


def _build_db_config(args, data_type: str, silent: bool = False):
    """Build database config from CLI args based on data type.

    Returns:
        dict: Database config, or None for CSV.
        Returns False if required args are missing (error printed unless silent).
    """
    if data_type == "sql":
        required_db_args = ["db_type", "db_host", "db_port", "db_name", "db_user", "db_password"]
        missing_args = [arg for arg in required_db_args if not getattr(args, arg, None)]

        if missing_args:
            if not silent:
                print(f"Error: SQL datasource requires database configuration arguments:", file=sys.stderr)
                for arg in missing_args:
                    print(f"  --{arg.replace('_', '-')}", file=sys.stderr)
            return False

        return {
            "type": args.db_type,
            "host": args.db_host,
            "port": args.db_port,
            "database": args.db_name,
            "user": args.db_user,
            "password": args.db_password,
        }

    elif data_type == "bigquery":
        if not getattr(args, "bq_project", None):
            if not silent:
                print(f"Error: BigQuery datasource requires --bq-project argument", file=sys.stderr)
            return False

        return {
            "type": "bigquery",
            "project": args.bq_project,
            "credentials_path": getattr(args, "bq_credentials", None),
        }

    return None


def build_command(args):
    """Handle the build command"""
    dashml_path = args.input
    target = args.target
    output_path = args.output

    if not Path(dashml_path).exists():
        print(f"Error: DashML file not found: {dashml_path}", file=sys.stderr)
        return 1

    print(f"Loading {dashml_path}...")
    engine = DashMLEngine()

    # Step 1: Parse and validate (no normalization yet)
    try:
        spec_raw = engine.parse_and_validate(dashml_path)
    except ValidationError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading DashML file: {e}", file=sys.stderr)
        return 1

    print(f"✓ DashML spec validated successfully")

    # Step 2: Build db_config from CLI args based on data type
    data_type = spec_raw.get("data", {}).get("type", "csv")
    # Grafana generates static JSON — no DB connection needed at build time
    if target == "grafana" and data_type in ("sql", "bigquery"):
        db_config = _build_db_config(args, data_type, silent=True)
        if db_config is False:
            db_config = {"type": getattr(args, "db_type", None) or "postgresql"}
    else:
        db_config = _build_db_config(args, data_type)
        if db_config is False:
            return 1

    # Step 3: Normalize (produces NormalizedSpec with db_config baked in)
    try:
        spec = engine.normalize(spec_raw, dashml_path, db_config)
    except Exception as e:
        print(f"Error normalizing spec: {e}", file=sys.stderr)
        return 1

    if db_config:
        config_label = "BigQuery" if data_type == "bigquery" else "Database"
        print(f"✓ {config_label} configuration set")

    # Step 4: Get transformer
    try:
        if target == "superset":
            from dashml_new.transformers.superset import SupersetTransformer
            transformer = SupersetTransformer(
                superset_url=args.superset_url,
                username=args.superset_user,
                password=args.superset_password
            )
        elif target == "grafana":
            from dashml_new.transformers.grafana import GrafanaTransformer
            csv_url = getattr(args, "grafana_csv_url", None)
            serve_port = getattr(args, "grafana_serve_csv", None)
            csv_host = getattr(args, "grafana_csv_host", None) or "localhost"
            # --grafana-serve-csv: derive csv_url from the host + port + csv filename
            if serve_port and data_type == "csv" and not csv_url:
                csv_path = spec.get("data", {}).get("csv_path")
                if csv_path:
                    csv_filename = Path(csv_path).name
                    csv_url = f"http://{csv_host}:{serve_port}/{csv_filename}"
            transformer = GrafanaTransformer(
                datasource_uid=getattr(args, "grafana_datasource_uid", None),
                csv_url=csv_url,
            )
        elif target == "vegalite" and (getattr(args, "embed_data", False) or getattr(args, "bare", False)):
            from dashml_new.transformers.vegalite import VegaLiteTransformer
            import csv as csv_mod
            embedded_data = None
            bare = getattr(args, "bare", False)
            if getattr(args, "embed_data", False) and data_type == "csv":
                csv_path = spec.get("data", {}).get("csv_path")
                if csv_path and Path(csv_path).exists():
                    with open(csv_path, newline="", encoding="utf-8") as f:
                        reader = csv_mod.DictReader(f)
                        embedded_data = []
                        for row in reader:
                            converted = {}
                            for k, v in row.items():
                                if v is None or v == "":
                                    converted[k] = None
                                else:
                                    try:
                                        converted[k] = int(v)
                                    except (ValueError, TypeError):
                                        try:
                                            converted[k] = float(v)
                                        except (ValueError, TypeError):
                                            converted[k] = v
                            embedded_data.append(converted)
                    print(f"\u2713 Embedded {len(embedded_data)} rows from CSV")
            transformer = VegaLiteTransformer(embedded_data=embedded_data, bare=bare)
        else:
            transformer = TransformerRegistry.get(target)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Using transformer: {transformer.description}")

    # Step 5: Generate code
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
                    # Single-file output - write inside a directory
                    output_dir = Path(output_path)
                    # If a file exists at this path, remove it so we can create a directory
                    if output_dir.is_file():
                        output_dir.unlink()
                    output_dir.mkdir(parents=True, exist_ok=True)
                    # Clean stale files from previous builds of different type
                    for stale in ("app.py", "index.html"):
                        stale_file = output_dir / stale
                        if stale_file.exists() and stale != transformer.output_filename:
                            stale_file.unlink()
                    out_file = output_dir / transformer.output_filename
                    out_file.write_text(code, encoding="utf-8")
                    print(f"✓ Output written to: {out_file}")

                    # For CSV data sources, copy CSV into output dir so it's served alongside
                    if data_type == "csv":
                        csv_path = spec.get("data", {}).get("csv_path")
                        if csv_path and Path(csv_path).exists():
                            csv_dest = output_dir / Path(csv_path).name
                            shutil.copy2(csv_path, csv_dest)
                            print(f"✓ Copied data file: {csv_dest}")
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

    # Start CSV file server for Grafana if requested
    if target == "grafana" and getattr(args, "grafana_serve_csv", None) and output_path:
        serve_port = args.grafana_serve_csv
        serve_dir = Path(output_path).resolve()
        import http.server
        import functools

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(serve_dir))
        try:
            httpd = http.server.HTTPServer(("", serve_port), handler)
        except OSError as e:
            print(f"Error: Could not start CSV server on port {serve_port}: {e}", file=sys.stderr)
            return 1

        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        print(f"\n✓ Serving CSV at http://localhost:{serve_port}/")
        print(f"  Keep this process running while Grafana is open. Press Ctrl+C to stop.\n")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            httpd.shutdown()
            print("\n✓ CSV server stopped")
            return 0

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

    def rebuild():
        """Rebuild the output file"""
        engine = DashMLEngine()

        try:
            # Load, validate, and normalize (db_config=None for watch/CSV mode)
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

            # Write output (directory-based, consistent with build_command)
            output_dir = Path(output_path)
            if output_dir.is_file():
                output_dir.unlink()
            output_dir.mkdir(parents=True, exist_ok=True)
            # Clean stale files from previous builds of different type
            for stale in ("app.py", "index.html"):
                stale_file = output_dir / stale
                if stale_file.exists() and stale != transformer.output_filename:
                    stale_file.unlink()
            out_file = output_dir / transformer.output_filename
            out_file.write_text(code, encoding="utf-8")
            # Copy CSV data file if needed
            data_type = spec.get("data", {}).get("type", "csv")
            if data_type == "csv":
                csv_path = spec.get("data", {}).get("csv_path")
                if csv_path and Path(csv_path).exists():
                    shutil.copy2(csv_path, output_dir / Path(csv_path).name)
            print(f"✓ Written to {out_file}")

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
    build_parser.add_argument(
        "--grafana-datasource-uid",
        help="Grafana datasource UID (for grafana backend; default: placeholder for import wizard)"
    )
    build_parser.add_argument(
        "--grafana-csv-url",
        help="URL serving the CSV file (for grafana backend with Infinity plugin)"
    )
    build_parser.add_argument(
        "--grafana-serve-csv",
        type=int,
        nargs="?",
        const=8888,
        default=None,
        metavar="PORT",
        help="Start a local HTTP server for the CSV file (default port: 8888, for grafana backend with Infinity plugin)"
    )
    build_parser.add_argument(
        "--grafana-csv-host",
        default=None,
        metavar="HOST",
        help="Hostname Grafana uses to reach the CSV server (default: localhost; use host.docker.internal for Docker)"
    )
    build_parser.add_argument(
        "--embed-data",
        action="store_true",
        help="Embed CSV data inline in the output (for vegalite backend — makes spec self-contained)"
    )
    build_parser.add_argument(
        "--bare",
        action="store_true",
        help="Output bare VL objects [{mark, encoding, transform}] for benchmark evaluation (vegalite backend)"
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
