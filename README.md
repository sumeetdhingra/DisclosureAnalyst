# Disclosure Analyst

A cross-platform (macOS + Windows) desktop application that analyzes a ZIP archive of home purchase disclosure documents and produces a structured PDF report using Claude.

The report covers:
1. Key Inspection Findings
2. Repairs Performed
3. Repairs Pending (with cost estimates)
4. Appliance Conditions (condition + age)
5. Roof Condition
6. Foundation
7. Termite Inspection
8. HOA Details

Plus a final "Unreadable Files" section if anything in the archive could not be parsed.

## Supported file types in the ZIP
- PDF (`.pdf`)
- Word (`.docx` — legacy `.doc` not supported, please convert)
- Excel (`.xlsx`, `.xlsm`, `.xls`)
- Text-like (`.txt`, `.md`, `.csv`, `.html`, `.xml`, `.json`, `.log`, `.rtf`)
- Images (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`) — analyzed via Claude vision

## Install (run from source)

```bash
cd DisclosureAnalyst
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m disclosure_analyst
```

The first time you run it, click **API Key…** in the toolbar and paste your Anthropic API key (it will be stored in `~/.disclosure_analyst_key`). Alternatively set the environment variable `ANTHROPIC_API_KEY` before launching.

## Usage
1. Click **Choose ZIP…** and select a disclosure archive.
2. Click **Analyze**. A progress indicator runs while Claude reads every document.
3. The generated PDF report appears in the preview pane.
4. Click **Download PDF…** to save it anywhere.

## Build installers

> PyInstaller does not cross-compile. Build the macOS installer on a Mac and the Windows installer on Windows.

In your activated virtualenv:

```bash
pip install pyinstaller
python build_app.py
```

### macOS — produces a `.dmg`

After the script finishes you'll have:

```
dist/DisclosureAnalyst.app                  ← the app bundle
dist/DisclosureAnalyst-1.0.0.dmg            ← drag-to-install disk image
```

The DMG opens to a window containing the app and an `Applications` shortcut — users drag `DisclosureAnalyst.app` onto `Applications` to install. No extra tools required (uses macOS's built-in `hdiutil`).

For Gatekeeper to launch the app without a right-click warning, you'd additionally codesign and notarize it with an Apple Developer ID — optional and outside this script.

### Windows — produces a `.exe` installer

`python build_app.py` produces:

```
dist\DisclosureAnalyst.exe                  ← single-file portable app
installer.iss                               ← Inno Setup script
```

To turn that into a real installer with Start menu shortcut and uninstaller:

1. Install [Inno Setup](https://jrsoftware.org/isdl.php) (free).
2. Open `installer.iss` in **Inno Setup Compiler** and press **F9** (Build > Compile).
3. Output: `dist\DisclosureAnalyst-1.0.0-Setup.exe` — a standard Windows installer your users can double-click.

## Configuration
- `ANTHROPIC_API_KEY` environment variable, **or**
- API key entered via the toolbar (saved to `~/.disclosure_analyst_key` with mode 600 on Unix).

## Model
Uses `claude-opus-4-7` with streaming for long inputs. Edit `disclosure_analyst/analyzer.py` to change models or limits.
