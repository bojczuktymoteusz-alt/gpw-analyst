import sys
import subprocess
import shutil

def check_command(cmd):
    return shutil.which(cmd) is not None

def check_python_module(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False

print("=== GPW Analyst V2 Environment Check ===")

# Check Python
print(f"Python version: {sys.version.split()[0]} - OK")

# Check Node/NPM
if check_command("node"):
    try:
        node_v = subprocess.check_output(["node", "--version"]).decode().strip()
        print(f"Node.js version: {node_v} - OK")
    except:
        print("Node.js: Installed but failed to get version.")
else:
    print("ERR: Node.js is not installed or not in PATH.")

# Check NPM
if check_command("npm") or check_command("npm.cmd"):
    print("NPM: OK")
else:
    print("ERR: NPM is not installed or not in PATH.")

# Check Python Modules
modules = ["fastapi", "uvicorn", "yfinance", "pandas"]
for mod in modules:
    if check_python_module(mod):
        print(f"Python module '{mod}': OK")
    else:
        print(f"ERR: Python module '{mod}' is missing. Run: pip install {mod}")

print("=========================================")
