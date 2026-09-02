# -*- mode: python ; coding: utf-8 -*-
"""精简版 PyInstaller 配置：只打包分析所需依赖，避免把整个 Anaconda 打进去。"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = []
binaries = []

# ultralytics / torch 需要的数据与动态库
try:
    datas += collect_data_files("ultralytics")
except Exception:
    pass
try:
    binaries += collect_dynamic_libs("torch")
except Exception:
    pass
try:
    binaries += collect_dynamic_libs("torchvision")
except Exception:
    pass
try:
    binaries += collect_dynamic_libs("cv2")
except Exception:
    pass

hiddenimports = [
    "segment",
    "segment.analyze_engine",
    "app_paths",
    "export",
    "utils.load_user_config",
    "utils.console_ui",
    "utils.launcher_gui",
    "app_metadata",
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "models.common",
    "models.yolo",
    "models.experimental",
    "sklearn.linear_model",
    "sklearn.metrics",
    "scipy.integrate",
    "scipy.stats",
    "pandas",
    "seaborn",
    "yaml",
    "ultralytics",
    "ultralytics.utils.plotting",
]

# Exclude common large / unused packages so the exe stays manageable
excludes = [
    "IPython",
    "jupyter",
    "notebook",
    "nbconvert",
    "nbformat",
    "sphinx",
    "pytest",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "bokeh",
    "panel",
    "plotly",
    "dash",
    "streamlit",
    "tensorflow",
    "tensorboard",
    "onnxruntime",
    "botocore",
    "boto3",
    "distributed",
    "dask",
    "numba",
    "llvmlite",
    "sqlalchemy",
    "tables",
    "h5py",
    "skimage",
    "statsmodels",
    "pyarrow",
    "fsspec",
    "win32com",
    "pythoncom",
]

a = Analysis(
    ["run_analysis.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TLC-RAPID",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TLC-RAPID",
)
