# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec 文件 — 检察侦查画像系统
# 打包目标：server.py (FastAPI后端 + 静态前端)

import sys
import os
from pathlib import Path

block_cipher = None

# 获取 pyvis 模板文件路径
import pyvis
pyvis_path = os.path.dirname(pyvis.__file__)
pyvis_templates = os.path.join(pyvis_path, 'templates')

# 需要打包进去的数据文件（源路径, 目标路径）
added_files = [
    # 前端静态资源
    ('frontend', 'frontend'),
    # src 模块
    ('src', 'src'),
    # config
    ('config.py', '.'),
    # pyvis 模板文件
    (pyvis_templates, 'pyvis/templates'),
    # 注意：data 目录不打包，运行时会在可执行文件旁边自动创建
]

a = Analysis(
    ['server.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        # FastAPI / Starlette 相关
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.off',
        'uvicorn.lifespan.on',
        'fastapi',
        'fastapi.middleware',
        'fastapi.middleware.cors',
        'starlette',
        'starlette.staticfiles',
        'starlette.responses',
        'starlette.middleware',
        'starlette.middleware.cors',
        # 数据处理
        'pandas',
        'openpyxl',
        'xlrd',
        # 图谱
        'networkx',
        'pyvis',
        'pyvis.network',
        # AI
        'anthropic',
        'openai',
        # 其他
        'pydantic',
        'aiofiles',
        'multipart',
        'sqlite3',
        'json',
        'hashlib',
        'tempfile',
        # src 子模块
        'src.database',
        'src.ingest',
        'src.anomaly',
        'src.graph_analysis',
        'src.profiler',
        'src.agent',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
        'matplotlib',
        'scipy',
        'sklearn',
        'tensorflow',
        'torch',
        # 'IPython',  # pyvis 需要 IPython，不能排除
        'jupyter',
        'notebook',
        'pytest',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='检察侦查画像系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # 保留控制台窗口，方便查看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# 单文件模式，不需要 COLLECT
