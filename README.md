# PJS Compressor (Python-only)

Windows GUI for ZIP and the custom PJS archive format. The PJS codec is a learning-oriented LZ77-style lossless codec.

## PJS2 changes
- PJS2 uses a deterministic filename-derived parameter to vary compression candidate selection.
- Compressed payload bytes are reversibly transformed using the normalized archive path and a per-4-KiB block index.
- PJS1 archives from the earlier project remain readable; newly created PJS archives use PJS2.
- ZIP behavior remains standard ZIP compression/extraction.

## Important security note
The filename-derived value is public and is not a password or secret key. The reversible byte transformation is obfuscation, **not encryption**. Anyone who can inspect the executable, observe input/output, or infer the filename rule may reproduce it. Do not use PJS to protect confidential data. This design aims only to increase the effort needed to write a casual third-party compatible tool.

## Build the Windows executable
1. Push this project to a GitHub repository on the `main` branch.
2. Open **Actions** and run **Build Windows EXE**, or push a commit.
3. Download the `PJSCompressor-Windows` artifact from the completed workflow.

The build uses PyInstaller `--onefile --windowed`. That packages the program; it does not make Python bytecode impossible to extract.

## Run from source
```bash
python -m pip install -r requirements.txt
python main.py
```

## Tests
`main.py` can be syntax-checked with `python -m py_compile main.py`. Round-trip tests should include empty files, repetitive data, random data, nested folders, Unicode filenames, and deliberate archive corruption.
