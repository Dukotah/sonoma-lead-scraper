# How to build the standalone `LeadScraper.exe` (Windows)

You do this **once**. After that you have a single .exe file you can:
- Double-click to launch (no Python needed)
- Copy to other Windows machines
- Put on a USB stick, email, share with employees
- Move to your Desktop and pin to taskbar

## What you need
- A Windows PC
- Python 3.10+ installed — get it from https://www.python.org/downloads/
  - **IMPORTANT:** during install, check the box **"Add python.exe to PATH"** (it's on the first screen)

## Steps

1. **Make sure the whole `lead_scraper` folder is on your computer.** Don't move individual files out of it.

2. **Open the `lead_scraper` folder** in File Explorer.

3. **Double-click `build.bat`.**
   - A black window opens.
   - It says "Installing build dependencies" — wait ~30 seconds.
   - It says "Compiling LeadScraper.exe" — wait 2–5 minutes. This is the slow part. The window will look frozen. It isn't. Be patient.
   - When it says **DONE**, hit any key to close the window.

4. **Find your app.** Inside the `lead_scraper` folder you'll see a new folder called `dist`. Inside `dist` is `LeadScraper.exe`. That's your app.

5. **Test it.** Double-click `LeadScraper.exe`. A window should open titled "Lead Scraper". If it does — done. The folder of source files (`app.py`, `desktop_app.py`, etc.) is no longer needed — `LeadScraper.exe` is fully self-contained.

6. **Move it where you want it.** Drag `LeadScraper.exe` to your Desktop, your Documents folder, wherever. Right-click → "Pin to taskbar" if you want it always there.

## Troubleshooting

**"python is not recognized as an internal or external command"**
You skipped the "Add Python to PATH" checkbox during install. Reinstall Python from python.org and check that box.

**Build fails with "No module named X"**
Run `build.bat` again — sometimes pip needs two passes on a fresh Python install.

**Antivirus flags the .exe**
PyInstaller-built apps sometimes trigger false positives because they bundle a Python interpreter. Allow it in your antivirus. (If you want to verify safety: open the source files — they're all in this folder and human-readable.)

**The .exe is huge (~50 MB)**
Normal. It bundles the entire Python interpreter + Flask + pywebview + openpyxl. The price of "no Python install needed".

**Want a smaller .exe?**
Replace the `--onefile` flag in `build.bat` with `--onedir`. You get a folder instead of a single file, but it loads faster and is smaller per-file. Zip the whole `dist/LeadScraper/` folder to share it.

## Mac users
Use `build.sh` instead. Open Terminal, `cd` into the folder, run `./build.sh`. You'll get `dist/LeadScraper.app` (Mac equivalent). All other steps are the same.

## What if I just want to run it without building an .exe?
Skip all of this. Run `run.bat` (Windows) or `run.sh` (Mac/Linux). It starts the app the same way, just opens in your browser instead of a native window, and requires Python on every machine you run it on.
