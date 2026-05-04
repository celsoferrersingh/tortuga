# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — Tortuga PPE Monitor
Gera executável standalone para macOS ARM ou Windows x86_64.
"""
import sys, os
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

ROOT = Path(SPECPATH)          # pasta raiz do projeto
SERVER = ROOT / "server"

# ── Arquivos de dados a incluir no bundle ──────────────────
datas = [
    (str(SERVER / "models"), "models"),        # best.pt, best.old.pt
]
# Inclui dados do ultralytics (yamls de configuração)
try:
    import ultralytics
    ult_path = Path(ultralytics.__file__).parent
    datas.append((str(ult_path / "cfg"),  "ultralytics/cfg"))
    datas.append((str(ult_path / "assets"), "ultralytics/assets"))
except Exception:
    pass

# ── Imports ocultos necessários ────────────────────────────
hiddenimports = [
    "ultralytics",
    "ultralytics.nn.tasks",
    "ultralytics.nn.modules",
    "ultralytics.nn.modules.block",
    "ultralytics.nn.modules.conv",
    "ultralytics.nn.modules.head",
    "ultralytics.models",
    "ultralytics.models.yolo",
    "ultralytics.models.yolo.detect",
    "ultralytics.utils",
    "ultralytics.utils.torch_utils",
    "ultralytics.data",
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torchvision",
    "torchvision.transforms",
    "cv2",
    "numpy",
    "PIL",
    "PIL.Image",
    "yaml",
    "scipy",
    "sklearn",
]

# Módulos torch específicos para MPS (macOS) ou CUDA (Windows)
if IS_MAC:
    hiddenimports += ["torch.backends.mps"]
if IS_WIN:
    hiddenimports += ["torch.backends.cudnn", "torch.cuda"]

a = Analysis(
    [str(SERVER / "gui.py")],
    pathex=[str(SERVER)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "IPython", "jupyter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

if IS_MAC:
    # ── macOS: bundle .app ─────────────────────────────────
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="Tortuga",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
    )
    coll = COLLECT(
        exe, a.binaries, a.datas,
        strip=False, upx=False,
        upx_exclude=[],
        name="Tortuga",
    )
    app = BUNDLE(
        coll,
        name="Tortuga.app",
        icon=None,
        bundle_identifier="com.tortuga.ppemonitor",
        info_plist={
            "NSCameraUsageDescription": "Tortuga precisa da câmera para detecção de EPIs.",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "CFBundleShortVersionString": "2.1",
        },
    )

else:
    # ── Windows: .exe único ────────────────────────────────
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas,
        name="Tortuga",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,   # sem janela de terminal
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch="x86_64",
        icon=None,
    )
