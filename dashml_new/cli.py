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

    For SQL targets, all credential CLI args (--db-host, --db-user, etc.) are
    OPTIONAL — the generated artifact reads them from environment variables
    (DASHML_DB_*) at runtime, not from baked-in literals. CLI args, when
    provided, are written into a generated .env.example as visible defaults
    to make local-machine setup a one-step copy.

    For BigQuery, --bq-project is REQUIRED at build time because the project
    ID is embedded into SQL queries as part of the fully-qualified table
    reference. Project ID is not a secret (public identifier).
    Credentials path is always read from env at runtime.
    """
    if data_type == "sql":
        # All SQL credentials are optional at build time — they live in env at runtime.
        return {
            "type": getattr(args, "db_type", None),
            "host": getattr(args, "db_host", None),
            "port": getattr(args, "db_port", None),
            "database": getattr(args, "db_name", None),
            "user": getattr(args, "db_user", None),
            "password": getattr(args, "db_password", None),
        }

    elif data_type == "bigquery":
        if not getattr(args, "bq_project", None):
            if not silent:
                print(f"Error: BigQuery datasource requires --bq-project argument", file=sys.stderr)
                print(f"  (project ID is embedded into SQL queries at build time and is not a secret;", file=sys.stderr)
                print(f"   credentials are read from DASHML_BQ_CREDENTIALS env var at runtime)", file=sys.stderr)
            return False

        return {
            "type": "bigquery",
            "project": args.bq_project,
            # credentials_path retained for backward compat in db_config but no longer
            # baked into generated code — generator always reads from env at runtime.
            "credentials_path": getattr(args, "bq_credentials", None),
        }

    return None


def _register_build_args(parser, *, output_required=False):
    """Register the full set of build arguments on a parser.

    Shared by `build` and `watch` so the two subcommands stay in lockstep —
    any flag accepted by `build` is automatically accepted by `watch`, and
    watch can pipe them through to the underlying build on each rebuild.
    """
    parser.add_argument("input", help="Path to .dashml file")
    parser.add_argument(
        "--target", "-t",
        required=True,
        help="Target platform (e.g., streamlit, plotly)"
    )
    parser.add_argument(
        "--output", "-o",
        required=output_required,
        help="Output directory" if output_required else "Output file path (default: print to stdout)"
    )
    parser.add_argument(
        "--run", "-r",
        action="store_true",
        help="Run the dashboard after building (requires --output)"
    )
    parser.add_argument(
        "--superset-url",
        default="http://localhost:8088",
        help="Superset instance URL (for superset backend only)"
    )
    parser.add_argument("--superset-user", help="Superset username (for superset backend only)")
    parser.add_argument("--superset-password", help="Superset password (for superset backend only)")
    parser.add_argument(
        "--grafana-datasource-uid",
        help="Grafana datasource UID (for grafana backend; default: placeholder for import wizard)"
    )
    parser.add_argument(
        "--grafana-csv-url",
        help="URL serving the CSV file (for grafana backend with Infinity plugin)"
    )
    parser.add_argument(
        "--grafana-serve-csv",
        type=int, nargs="?", const=8888, default=None, metavar="PORT",
        help="Start a local HTTP server for the CSV file (default port: 8888, for grafana backend with Infinity plugin)"
    )
    parser.add_argument(
        "--grafana-csv-host",
        default=None, metavar="HOST",
        help="Hostname Grafana uses to reach the CSV server (default: localhost; use host.docker.internal for Docker)"
    )
    parser.add_argument(
        "--embed-data",
        action="store_true",
        help="Embed CSV data inline in the output (for vegalite backend — makes spec self-contained)"
    )
    parser.add_argument(
        "--bare",
        action="store_true",
        help="Output bare VL objects [{mark, encoding, transform}] for benchmark evaluation (vegalite backend)"
    )
    # Database arguments (for SQL datasources).
    parser.add_argument(
        "--db-type", choices=["postgresql", "mysql", "sqlite"],
        help="Database type (optional; written into .env.example as default for DASHML_DB_TYPE)"
    )
    parser.add_argument(
        "--db-host",
        help="Database host (optional; written into .env.example as default for DASHML_DB_HOST)"
    )
    parser.add_argument(
        "--db-port", type=int,
        help="Database port (optional; written into .env.example as default for DASHML_DB_PORT)"
    )
    parser.add_argument(
        "--db-name",
        help="Database name (optional; written into .env.example as default for DASHML_DB_NAME)"
    )
    parser.add_argument(
        "--db-user",
        help="Database username (optional; written into .env.example as default for DASHML_DB_USER)"
    )
    parser.add_argument(
        "--db-password",
        help="Database password (optional; NEVER written to .env.example — supply at runtime via DASHML_DB_PASSWORD)"
    )
    # BigQuery arguments
    parser.add_argument(
        "--bq-project",
        help="Google Cloud project ID (required for BigQuery datasources; embedded in SQL queries; not a secret)"
    )
    parser.add_argument(
        "--bq-credentials",
        help="Path to service account JSON credentials file (optional, written to .env.example as default for DASHML_BQ_CREDENTIALS)"
    )
    parser.add_argument(
        "--emit-env-example",
        action="store_true",
        help="Emit .env.example template (blank values) alongside the artifact. Off by default; .gitignore and SECRETS.md are always emitted for SQL/BigQuery targets."
    )


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

                # For SQL/BigQuery targets that produce runnable Python (Plotly,
                # Observable, Streamlit), generate auxiliary files for runtime
                # secrets management: .env.example, .gitignore, SECRETS.md.
                if data_type in ("sql", "bigquery") and target in ("plotly", "observable", "streamlit"):
                    from dashml_new.transformers.secrets import (
                        emit_env_example, emit_gitignore, emit_secrets_readme,
                    )
                    output_dir = Path(output_path)
                    aux_files = {
                        ".gitignore": emit_gitignore(),
                        "SECRETS.md": emit_secrets_readme(data_type),
                    }
                    if getattr(args, "emit_env_example", False):
                        aux_files[".env.example"] = emit_env_example(data_type)
                    for name, content in aux_files.items():
                        if not content:
                            continue
                        (output_dir / name).write_text(content, encoding="utf-8")
                        print(f"✓ Written: {output_dir / name}")
                    print("ℹ Credentials are read from environment at runtime — see SECRETS.md")
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

    # Suppress --run on per-rebuild invocations — watch handles the run
    # itself once, outside the rebuild loop, so subsequent rebuilds shouldn't
    # try to re-launch the app.
    args.run = False

    def rebuild():
        """Delegate to build_command so every flag accepted by `build`
        (--bq-project, --db-*, --emit-env-example, --embed-data, ...) is
        honored on every rebuild without watch needing to duplicate logic."""
        try:
            build_command(args)
        except Exception as e:
            print(f"✗ Rebuild error: {e}", file=sys.stderr)

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
    _register_build_args(build_parser, output_required=False)

    # List command
    list_parser = subparsers.add_parser("list", help="List available transformers")

    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch .dashml file and rebuild on changes")
    _register_build_args(watch_parser, output_required=True)

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
