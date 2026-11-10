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
   You should end up with `Documents\GitHub\drainshield\` containing `README.md`, `simulate.py`, etc.
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

This installs `numpy` (math), `pandas` (tables of data), `matplotlib` (plots),
`streamlit` (turns a Python script into a web page) and `plotly` (interactive charts).
If you already did this step before, run it again: the list has new libraries.

## 5. Open the dashboard

In the VS Code terminal:

```
python -m streamlit run app.py
```
(or `py -m streamlit run app.py` if `python` isn't found)

Your web browser opens the dashboard (the first time it takes a few extra seconds to make the
fake data). If it asks for an email, just press Enter. The terminal stays busy while the
dashboard is running: that's normal. **To stop it, click in the terminal and press Ctrl+C.**

The **Network** page opens first: the weather readiness banner, a map of every basin and a dispatch
list. Click a pin or search a basin to see its card. Use the **Demo replay** slider on the left
(or the buttons under it) to move through the two simulated months. Try **Before storm**: basins
with slow drainage turn red ("inspect before storm"). Then **Storm (Oct 15)** to see basins backing up.
Switch **View** between **Crew** (simple) and **Engineering** (sensor health, hydrographs, history).

On a basin's page, **Log maintenance** records a crew visit. "Cleaned / vacuumed" closes the issue.
The log is saved in `data/maintenance_log.csv`.

To add a basin, click **Add basin**. Pick one of the city's catch basins (or type the position),
enter the IDs and what's on the as-built plan, and click **Save basin**. Your basins are saved in
`data/basins_user.csv`: commit that file in GitHub Desktop to share them with the team.

If the map stays blank, your internet may be blocking the map tiles: turn off
**Street map** in the sidebar to see the dots on a plain background.

If you change the code while it's running, click **Rerun** at the top right of the page
to see your change.

## 6. Other scripts (optional)

Still in the VS Code terminal, run these one at a time:

```
python make_basins.py
python simulate.py pilot
python plot_compare.py pilot
```

A plot window should open, comparing a clean basin with a clogging one.
Close the window to get your terminal back. The plot is also saved in `output\figures\`.

Try the town network too:

```
python simulate.py town
python plot_compare.py town
```

---

## Your everyday Git routine

Every time you work on the project:

1. **Pull first.** In GitHub Desktop click **Fetch origin**, then **Pull origin** if it appears.
   This downloads your teammates' changes. Do it *before* you start editing.
2. **Work** in VS Code: change code, run it, check that it works.
3. **Commit.** In GitHub Desktop, look at the changes on the left (green = added lines,
   red = removed lines). Write a short summary of *what* you did, e.g.
   `Make storms more frequent in simulator`, then click **Commit to main**.
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
| `Can't find data/basins_pilot.csv` | Run `python make_basins.py` first, and make sure the terminal is in the `drainshield` folder |
| The terminal seems frozen after the plot | Close the plot window |
| `streamlit` is not recognized | Use `python -m streamlit run app.py` |
| The dashboard looks the same after I changed the code | Click **Rerun** (top right of the page), or stop with Ctrl+C and start again |
