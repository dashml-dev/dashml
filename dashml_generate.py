#!/usr/bin/env python3
"""
DashML Code Generator
Demonstrates compiler pipeline: .dashml → IR → Backend Code
"""
import sys
import argparse
from pathlib import Path
from dashml.core import DashMLCompiler
from dashml.backends import StreamlitBackend, PlotlyBackend


def main():
    parser = argparse.ArgumentParser(description="DashML Code Generator")
    parser.add_argument("dashml_file", help="Path to .dashml file")
    parser.add_argument(
        "--backend",
        choices=["streamlit", "plotly", "ir"],
        default="streamlit",
        help="Target backend"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file (default: stdout)"
    )
    
    args = parser.parse_args()
    
    # Compile to IR
    compiler = DashMLCompiler()
    
    try:
        ir = compiler.compile(args.dashml_file)
    except Exception as e:
        print(f"Error compiling {args.dashml_file}: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Generate backend code
    if args.backend == "ir":
        # Just output IR as JSON
        import json
        output = json.dumps(ir.to_dict(), indent=2)
    
    elif args.backend == "streamlit":
        backend = StreamlitBackend()
        output = backend.generate(ir)
    
    elif args.backend == "plotly":
        backend = PlotlyBackend()
        output = backend.generate_html(ir)
    
    else:
        print(f"Unknown backend: {args.backend}", file=sys.stderr)
        sys.exit(1)
    
    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Generated {args.backend} code → {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()

