import sys
from pathlib import Path
sys.path[:0]=['/mcpfix/scripts','/mcpfix/src']
mode=sys.argv.pop(1)
if mode=='setup':import setup_isolated_profile as launcher
else:import start_freecad_isolated as launcher
launcher._repo_root=lambda:Path('/workspace')
raise SystemExit(launcher.main())
