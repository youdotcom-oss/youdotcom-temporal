import sys
import zipfile
from pathlib import Path

wheel_path = Path(sys.argv[1])
z = zipfile.ZipFile(wheel_path)
names = z.namelist()
py_typed = [n for n in names if "py.typed" in n]
print(f"Total files: {len(names)}")
print(f"py.typed files: {py_typed}")
print("All non-directory files:")
for n in sorted(names):
    if not n.endswith("/"):
        print(f"  {n}")
