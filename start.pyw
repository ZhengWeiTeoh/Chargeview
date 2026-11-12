import sys
from pathlib import Path

sys.dont_write_bytecode = True
folder = Path(__file__).resolve().parent
if not (folder / "chargeview" / "app.py").is_file():
    folder = (folder / "DeskCharge Project").resolve()
sys.path.insert(0, str(folder))

from chargeview.app import main
main()
