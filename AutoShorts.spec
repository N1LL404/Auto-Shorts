# Build on Windows with: pyinstaller --clean --noconfirm AutoShorts.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH)
datas = [(str(root / "web"), "web"), (str(root / "prompts"), "prompts")]
binaries = []
hiddenimports = []
for package in ("faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av",
                "huggingface_hub"):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports
for distribution in ("faster-whisper", "huggingface-hub", "tokenizers", "ctranslate2", "av"):
    datas += copy_metadata(distribution)
for path in (root / "vendor" / "bin").glob("*.exe"):
    binaries.append((str(path), "bin"))
for path in (root / "vendor").glob("*.txt"):
    datas.append((str(path), "licenses"))

a = Analysis([str(root / "desktop.py")], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=["pytest", "IPython", "torch", "tensorflow"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AutoShorts",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=True)
collect = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AutoShorts")
