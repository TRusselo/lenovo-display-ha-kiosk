# Running from source (Python)

The same tool as the standalone program: same steps, prompts, checks and resume. You run it with your own
Python, which needs to be 3.10 or newer.

## 1. Install Python

| System | How |
|---|---|
| **Windows** | Install from [python.org](https://www.python.org/downloads/windows/), and **tick "Add python.exe to PATH"**. Or run `winget install Python.Python.3.12`. |
| **macOS** | Install from [python.org](https://www.python.org/downloads/macos/), or run `brew install python@3.12`. Apple's own `python3` (3.9, from the Command Line Tools) is too old. |
| **Linux** | Use your distro's packages: `sudo apt install python3 python3-venv` (Debian/Ubuntu), `sudo dnf install python3` (Fedora) or `sudo pacman -S python` (Arch). |

Check: `python3 --version` (or `py --version` on Windows) shows 3.10 or newer.

## 2. Get the code and its packages

```bash
git clone https://github.com/TRusselo/lenovo-display-ha-kiosk
cd lenovo-display-ha-kiosk
python3 -m venv .venv
```

Activate the venv: `source .venv/bin/activate` on macOS or Linux, `.venv\Scripts\activate` on Windows.

```bash
pip install -r requirements.txt
```

Or, with [uv](https://docs.astral.sh/uv/): `uv run -m lhk setup`.

## 3. The volume helper (`ks-volkeys.jar`)

Download `ks-volkeys.jar` from the [latest release](../../../releases) and put it in the repo folder.

To build it yourself, you need JDK 17+ and the Android SDK (platform 35, build-tools 35.0.0):

```bash
cd assets/bootfix/volkeys
javac --release 8 -cp $ANDROID_SDK/platforms/android-35/android.jar -d build/classes VolKeys.java
(cd build/classes && jar cf ../classes.jar ks/*.class)
$ANDROID_SDK/build-tools/35.0.0/d8 --min-api 26 --lib $ANDROID_SDK/platforms/android-35/android.jar --output build/ks-volkeys.jar build/classes.jar
```

## 4. Run

```bash
python -m lhk setup
```

Options:
- `--dry-run`: list the steps, change nothing
- `--from STEP`: start at a step
- `--restart`: forget saved progress
- `--skip-backup`: skip the backup, after a warning
- `--name NAME`: a name for each display when you do several
- `--workdir DIR`: where downloads, backups, logs and progress go

`python -m lhk status` shows which steps are done. `python -m lhk restore BACKUP` restores a backup: the folder or its zip. `python -m lhk lock` locks verified boot on a restored display left unlocked.

## Tests

```bash
pip install pytest
python -m pytest -q
```

The tests need no display and no network.
