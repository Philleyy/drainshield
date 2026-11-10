# Setup guide (Windows, beginner-friendly)

This guide takes you from nothing to "the project is on GitHub and the code runs".
It takes about 30–45 minutes the first time. You only do steps 1–4 once.

---

## 1. Install Python

1. Go to **python.org → Downloads** and download the latest Python 3 for Windows.
2. Run the installer. **On the first screen, tick "Add python.exe to PATH"** at the bottom.
   This is the step people most often miss.
3. Click **Install Now**.

**Check it worked:** open the Start menu, type `cmd`, open *Command Prompt* and type:

```
python --version
```

You should see something like `Python 3.13.x`.
If the Microsoft Store opens instead, close it and try `py --version`. If that works,
type `py` everywhere this guide says `python`.

## 2. Install VS Code (the code editor)

1. Download it from **code.visualstudio.com** and install it with the default options.
2. Open VS Code, click the **Extensions** icon on the left (four little squares),
   search **Python** and install the one made by Microsoft.

## 3. Put the project on your computer and on GitHub

You already have GitHub Desktop and an account.

1. Unzip `drainshield.zip` into `Documents\GitHub\` (create the `GitHub` folder if needed).
   You should end up with `Documents\GitHub\drainshield\` containing `README.md`, `app.py`, etc.
   (Make sure it's not doubled, like `drainshield\drainshield\`.)
2. Open **GitHub Desktop** → **File → Add local repository…** → choose the `drainshield` folder.
3. It will say *"This directory does not appear to be a Git repository"*.
   Click **"create a repository"** in that message.
   Leave the name as `drainshield`, leave *Git ignore* on **None** (we already have one),
   and click **Create repository**.
4. GitHub Desktop now makes a first snapshot ("commit") of all the files.
   If you still see files listed under **Changes** on the left, type `Initial commit`
   in the *Summary* box at the bottom left and click **Commit to main**.
5. Click **Publish repository** (top bar). **Keep "Keep this code private" ticked** for now.
   Click **Publish**.
6. Check on **github.com**: your repo is there. To add teammates, go to the repo
   → **Settings → Collaborators → Add people**.

> **What just happened?**
> **Git** keeps a history of snapshots of your folder (each snapshot is a **commit**).
> **GitHub** is the online copy that your team shares.
> **GitHub Desktop** is a friendly app that runs Git for you, so you don't have to type Git commands.

## 4. Install the Python libraries the project uses

1. In VS Code: **File → Open Folder…** → choose `Documents\GitHub\drainshield`.
2. Open a terminal inside VS Code: **Terminal → New Terminal** (it opens at the bottom).
3. Type:

```
python -m pip install -r requirements.txt
```

This installs `numpy` (math), `pandas` (tables of data), `streamlit` (turns a Python script into a
web page), `plotly` (interactive charts) and `pyserial` (talks to the Arduino over USB).
If you already did this step before, run it again: the list has new libraries.

## 5. Open the dashboard

In the VS Code terminal:

```
python -m streamlit run app.py
```
(or `py -m streamlit run app.py` if `python` isn't found)

Your web browser opens the dashboard. If it asks for an email, just press Enter. The terminal stays
busy while the dashboard is running: that's normal. **To stop it, click in the terminal and press Ctrl+C.**

The **Network** page shows all 5,035 Dorval catch basins as grey dots (no sensor yet). There is no
demo data any more: everything you see comes from real sensors.

If the map stays blank, your internet may be blocking the map tiles: turn off
**Street map** in the sidebar to see the dots on a plain background.

If you change the code while it's running, click **Rerun** at the top right of the page.

## 6. Connect the ultrasonic sensor (bench test)

```
[sensor] -> [Arduino] --USB--> sensor_bridge.py -> data/live_readings.csv -> dashboard
```

1. Wire the sensor: VCC → 5V, GND → GND, Trig → pin 13, Echo → pin 12.
2. In the **Arduino IDE**, open `arduino\drainshield_sensor\drainshield_sensor.ino`, pick your board and
   port (**Tools** menu) and click **Upload**. Open the Serial Monitor at **9600 baud** to check you see
   lines like `DIST,123.4,5`, then **close the Serial Monitor** (only one program can use the port).
3. Keep the dashboard running in the first terminal. Open a **second terminal** in VS Code
   (the **+** at the top right of the terminal panel) and type:
   ```
   python sensor_bridge.py
   ```
   It lists the ports, e.g. `COM3  USB-SERIAL CH340`. Then start recording:
   ```
   python sensor_bridge.py COM3 --basin TEST-01
   ```
   Each reading is printed in the terminal. Stop with **Ctrl+C**.
4. In the dashboard, open **Live sensor** and turn on **Auto-refresh** in the sidebar. The readings
   appear within a few seconds.
5. **Change the frequency** with the *Data collection frequency* buttons (1 s for bench tests, 15 min
   in the field). The bridge sends it to the Arduino within ~2 s and the *Firmware* tile shows
   "device confirms 1 s interval".

**Bench test ideas:** hold a board at 30, 50, 100, 150 cm (tape measure) and compare; check the
closest distance it can read (the blind zone); point it down a bucket of water; check the noise tile
(under 1 cm on a still target is good).

**When it goes into a real basin:** use **Add basin** with the same ID you give `--basin`
(e.g. pick the city's catch basin, ID `DOR-12345`), then run
`python sensor_bridge.py COM3 --basin DOR-12345`. The **Basin** page then shows the water depth below the street.

## 7. Share the project with your team

- **To work on it together:** on github.com, open the repo → **Settings → Collaborators → Add people**
  and invite each teammate by GitHub username. They accept the email, then in GitHub Desktop:
  **File → Clone repository** → `drainshield`, and do steps 1, 2 and 4 on their computer.
  The link to send them is `https://github.com/<your-username>/drainshield`.
- **To let them watch the live dashboard during a test:** on the same Wi-Fi, open the **Network URL**
  that Streamlit printed when it started (e.g. `http://192.168.1.23:8501`) on their phone or laptop.
  (University Wi-Fi sometimes blocks this; a phone hotspot works.) If Windows asks about the firewall, click **Allow**.
- Commit `data/monitored_basins.csv`, `data/live_readings.csv` and `data/maintenance_log.csv` after a test
  so the team gets the data too.

---

## Your everyday Git routine

Every time you work on the project:

1. **Pull first.** In GitHub Desktop click **Fetch origin**, then **Pull origin** if it appears.
   This downloads your teammates' changes. Do it *before* you start editing.
2. **Work** in VS Code: change code, run it, check that it works.
3. **Commit.** In GitHub Desktop, look at the changes on the left (green = added lines,
   red = removed lines). Write a short summary of *what* you did, e.g.
   `Add bench test readings`, then click **Commit to main**.
   Commit often: a few small commits are better than one huge one.
4. **Push.** Click **Push origin** so your commits go up to GitHub for the team.

**Made a mess?** In GitHub Desktop, right-click a changed file → **Discard changes**
to go back to the last commit. Nothing that was committed is ever lost.

**Later (not needed yet):** *branches* let you try something big without touching the
main version. We'll use them once two people are editing code at the same time.

## Common problems

| Problem | Fix |
|---|---|
| `python` opens the Microsoft Store | Use `py` instead, or reinstall Python with "Add to PATH" ticked |
| `ModuleNotFoundError: No module named 'pandas'` | Run the `pip install` command from step 4 again |
| `can't open file ... app.py` | The terminal isn't in the project folder: `cd Documents\GitHub\drainshield` |
| `No module named 'serial'` | `python -m pip install pyserial` |
| `PermissionError` / `Access is denied` on COM3 | Close the Arduino IDE's Serial Monitor (or anything else using the port) |
| `python sensor_bridge.py` lists no port | Try another USB cable (some only charge) or install the CH340 driver for clone boards |
| Readings are always "no echo" | Check the wiring (Trig 13, Echo 12, 5 V) and that nothing is closer than ~25 cm |
| Garbage characters | Baud rate mismatch: the sketch and the bridge both use 9600 |
| `streamlit` is not recognized | Use `python -m streamlit run app.py` |
| The dashboard looks the same after I changed the code | Click **Rerun** (top right of the page), or stop with Ctrl+C and start again |
