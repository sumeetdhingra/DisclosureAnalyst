"""Build standalone Disclosure Analyst installers.

Run on the platform you want to target (PyInstaller does not cross-compile):

    macOS:    python build_app.py        ->  dist/DisclosureAnalyst.app
                                              dist/DisclosureAnalyst-1.0.0.dmg
    Windows:  python build_app.py        ->  dist/DisclosureAnalyst.exe
              (then run Inno Setup on installer.iss to produce the .exe installer)
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "run_app.py"
APP_NAME = "DisclosureAnalyst"
APP_VERSION = "1.0.0"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def _run(cmd, **kw):
    print(">>", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, **kw)


def _clean():
    for p in (DIST, BUILD):
        if p.exists():
            shutil.rmtree(p)
    for spec in ROOT.glob("*.spec"):
        spec.unlink()


def _pyinstaller(extra: list[str]):
    if shutil.which("pyinstaller") is None:
        sys.exit("PyInstaller not installed. Run: pip install pyinstaller")
    cmd = [
        "pyinstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", APP_NAME,
        "--collect-submodules", "anthropic",
        "--collect-submodules", "PySide6",
        "--collect-data", "reportlab",
        *extra,
        str(ENTRY),
    ]
    _run(cmd, cwd=ROOT)


def _build_mac_dmg():
    app_path = DIST / f"{APP_NAME}.app"
    if not app_path.exists():
        sys.exit(f"Expected {app_path} after PyInstaller; not found.")

    dmg_name = f"{APP_NAME}-{APP_VERSION}.dmg"
    dmg_path = DIST / dmg_name
    if dmg_path.exists():
        dmg_path.unlink()

    # Stage a folder with the .app and a symlink to /Applications so users can
    # drag-and-drop install. hdiutil ships with macOS — no extra deps needed.
    stage = BUILD / "dmg_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(app_path, stage / app_path.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")

    _run([
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", str(stage),
        "-ov", "-format", "UDZO",
        str(dmg_path),
    ])
    print(f"\nBuilt {dmg_path}")


def _emit_inno_script():
    """Write installer.iss next to the project so the user can compile it."""
    iss_path = ROOT / "installer.iss"
    iss_path.write_text(f"""\
; Inno Setup script for Disclosure Analyst (Windows installer).
; Build the .exe first with `python build_app.py`, then open this file in
; Inno Setup Compiler (https://jrsoftware.org/isdl.php) and click Compile.

#define MyAppName "Disclosure Analyst"
#define MyAppVersion "{APP_VERSION}"
#define MyAppPublisher "Disclosure Analyst"
#define MyAppExeName "{APP_NAME}.exe"

[Setup]
AppId={{{{B7E0F3A2-9B43-4B1B-9B6F-9D6F3A8E5B11}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DefaultGroupName={{#MyAppName}}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename={APP_NAME}-{APP_VERSION}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
; Single-file PyInstaller build — just one .exe to ship.
Source: "dist\\{APP_NAME}.exe"; DestDir: "{{app}}"; Flags: ignoreversion

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{commondesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent
""")
    print(f"Wrote {iss_path}")


def main():
    _clean()
    system = platform.system()

    if system == "Darwin":
        _pyinstaller([
            "--osx-bundle-identifier", "com.disclosureanalyst.app",
        ])
        _build_mac_dmg()
        print("\nDone. Distribute dist/DisclosureAnalyst-{v}.dmg".format(v=APP_VERSION))

    elif system == "Windows":
        _pyinstaller(["--onefile"])
        _emit_inno_script()
        print(
            "\nDone. To produce the installer:\n"
            "  1. Install Inno Setup: https://jrsoftware.org/isdl.php\n"
            "  2. Open installer.iss in Inno Setup Compiler\n"
            "  3. Click Build > Compile (or press F9)\n"
            f"  Output: dist\\{APP_NAME}-{APP_VERSION}-Setup.exe"
        )

    else:
        _pyinstaller([])
        print(f"\nBuilt for {system}. No installer packaging configured for this OS.")


if __name__ == "__main__":
    main()
