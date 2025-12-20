#!/usr/bin/env python3
"""
DashML CLI - Command-line interface for DashML compiler
"""
import sys
import argparse
from pathlib import Path
import json
from dashml.core import DashMLCompiler
from dashml.backends import StreamlitBackend, PlotlyBackend


def cmd_compile(args):
    """Compile .dashml to IR"""
    compiler = DashMLCompiler()
    
    try:
        ir = compiler.compile(args.file)
        print(json.dumps(ir.to_dict(), indent=2))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_validate(args):
    """Validate .dashml file"""
    compiler = DashMLCompiler()
    
    is_valid, errors = compiler.validate(args.file)
    
    if is_valid:
        print(f"✅ {args.file} is valid")
        return 0
    else:
        print(f"❌ {args.file} has errors:")
        for error in errors:
            print(f"  - {error}")
        return 1


def cmd_generate(args):
    """Generate backend code"""
    compiler = DashMLCompiler()
    
    try:
        ir = compiler.compile(args.file)
    except Exception as e:
        print(f"Error compiling: {e}", file=sys.stderr)
        return 1
    
    # Generate code
    if args.backend == "streamlit":
        backend = StreamlitBackend()
        code = backend.generate(ir)
    elif args.backend == "plotly":
        backend = PlotlyBackend()
        code = backend.generate_html(ir)
    else:
        print(f"Unknown backend: {args.backend}", file=sys.stderr)
        return 1
    
    # Output
    if args.output:
        Path(args.output).write_text(code)
        print(f"✅ Generated {args.backend} code → {args.output}")
    else:
        print(code)
    
    return 0


def cmd_dev(args):
    """Development mode with hot reload"""
    print(f"🔄 DashML Dev Mode - watching {args.file}")
    print("   Edit .dashml file to see instant updates")
    print("   Press Ctrl+C to stop")
    print()
    
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import time
    import os
    
    class DashMLReloader(FileSystemEventHandler):
        def __init__(self, file_path, backend):
            self.file_path = Path(file_path).resolve()
            self.backend = backend
            self.last_reload = 0
            
        def on_modified(self, event):
            if Path(event.src_path).resolve() == self.file_path:
                # Debounce
                now = time.time()
                if now - self.last_reload < 0.5:
                    return
                self.last_reload = now
                
                print(f"\n🔄 {self.file_path.name} changed, recompiling...")
                self.reload()
        
        def reload(self):
            try:
                compiler = DashMLCompiler()
                ir = compiler.compile(str(self.file_path))
                
                if self.backend == "streamlit":
                    # Trigger Streamlit rerun (it watches files automatically)
                    print("   ✅ Recompiled successfully (Streamlit will auto-reload)")
                elif self.backend == "plotly":
                    # Regenerate HTML
                    backend = PlotlyBackend()
                    html = backend.generate_html(ir)
                    output_path = self.file_path.with_suffix('.html')
                    output_path.write_text(html)
                    print(f"   ✅ Regenerated → {output_path}")
                    print(f"   🌐 Refresh browser to see changes")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    # Setup watcher
    handler = DashMLReloader(args.file, args.backend)
    observer = Observer()
    observer.schedule(handler, path=str(Path(args.file).parent), recursive=False)
    observer.start()
    
    # Initial compilation
    handler.reload()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 Stopping dev mode")
    
    observer.join()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="DashML - Declarative Dashboard Language Compiler",
        epilog="Examples:\n"
               "  dashml compile dashboard.dashml\n"
               "  dashml generate -b streamlit dashboard.dashml -o app.py\n"
               "  dashml dev dashboard.dashml\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # compile command
    compile_parser = subparsers.add_parser('compile', help='Compile .dashml to IR (JSON)')
    compile_parser.add_argument('file', help='.dashml file to compile')
    
    # validate command
    validate_parser = subparsers.add_parser('validate', help='Validate .dashml file')
    validate_parser.add_argument('file', help='.dashml file to validate')
    
    # generate command
    generate_parser = subparsers.add_parser('generate', help='Generate backend code')
    generate_parser.add_argument('file', help='.dashml file')
    generate_parser.add_argument('-b', '--backend', 
                                choices=['streamlit', 'plotly'],
                                default='streamlit',
                                help='Target backend')
    generate_parser.add_argument('-o', '--output', help='Output file')
    
    # dev command
    dev_parser = subparsers.add_parser('dev', help='Development mode with hot reload')
    dev_parser.add_argument('file', help='.dashml file to watch')
    dev_parser.add_argument('-b', '--backend',
                           choices=['streamlit', 'plotly'],
                           default='plotly',
                           help='Target backend')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Dispatch to command handlers
    commands = {
        'compile': cmd_compile,
        'validate': cmd_validate,
        'generate': cmd_generate,
        'dev': cmd_dev
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

