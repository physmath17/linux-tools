# linux-tools

A small collection of handy utilities for Linux.

| Tool | Folder | Description |
|------|--------|-------------|
| Battery Status Notifier | `battery-status-notifier/` | Desktop notification to connect the charger when the battery is low (35% or less) and to remove it once it reaches 80%, which helps prolong battery life |
| BibTeX Duplicate Finder | `bib-duplicates/` | Scans a large `.bib` file and reports entries that share the same title, ignoring differences in capitalization, braces, whitespace and trailing punctuation |
| Card Tracker | `credit-card-tracker/` | A minimal desktop app to track credit card payment due dates, with reminder pop-ups for payments that are due soon |


## Requirements

- Linux with a desktop environment
- Python 3.8+ with Tkinter (Card Tracker and the BibTeX tool use only the standard library)
- `notify-send` (for notifications) and `upower` (for the battery notifier)
- A cron daemon (for the scheduled jobs)

| | Arch Linux | Debian / Ubuntu |
|---|---|---|
| Tkinter | `sudo pacman -S tk` | `sudo apt install python3-tk` |
| Notifications | `sudo pacman -S libnotify` | `sudo apt install libnotify-bin` |
| Battery info | `sudo pacman -S upower` | `sudo apt install upower` |
| Cron | `sudo pacman -S cronie` | preinstalled |

On Arch, start the cron daemon and enable it at boot:

```bash
sudo systemctl enable --now cronie
```

## Installation

```bash
git clone https://github.com/physmath17/linux-tools.git
cd linux-tools
```

### Make the scripts executable

Run this from the repository root:

```bash
chmod +x battery-status-notifier/battery_status_notifier.sh \
         bib-duplicates/find_bib_duplicates.py \
         credit-card-tracker/card_tracker.py
```

You can now run any of them directly, for example `./credit-card-tracker/card_tracker.py`.

### Optional: run them by name from anywhere

Create symlinks in `~/.local/bin` (make sure that folder is in your `PATH`):

```bash
mkdir -p ~/.local/bin
ln -s "$PWD/credit-card-tracker/card_tracker.py" ~/.local/bin/card-tracker
ln -s "$PWD/bib-duplicates/find_bib_duplicates.py" ~/.local/bin/bib-duplicates
```

Then just type `card-tracker` or `bib-duplicates` in a terminal.

## Desktop app (Card Tracker)

To make Card Tracker show up in your application menu with its icon, create a `.desktop` file. Run this from the repository root. `$PWD` is filled in with the full path to your clone, so no editing is needed.

```bash
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/card-tracker.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Card Tracker
Comment=Track credit card due dates
Exec=$PWD/credit-card-tracker/card_tracker.py
Icon=$PWD/credit-card-tracker/card-tracker.png
Terminal=false
Categories=Office;Finance;
StartupWMClass=CardTracker
EOF
```

Refresh the application menu if the entry doesn't appear right away:

```bash
update-desktop-database ~/.local/share/applications
```

> **Note:** If the app's icon doesn't match the launcher in your taskbar, check the window's class with `xprop WM_CLASS` (then click the window) and set `StartupWMClass` to the matching value. If you move the repository, re-run the command above so the paths are updated.

## Usage

### Battery Status Notifier

The script checks the battery once and exits, so it is meant to be run by cron (see [Scheduled jobs](#scheduled-jobs-cron)). Run by hand in a terminal, it prints `All Good!` when there is nothing to do.

- Charging and at 80% or above: **"Battery Full"** notification, remove the charger.
- Not charging and at 35% or below: **"Battery Low"** notification, connect the charger.

To change the thresholds, edit the `80` and `35` values in the script. The script reads `battery_BAT0`; if your battery has a different name, find it with `upower -e` and update the `BATTERY` line.

### BibTeX Duplicate Finder

```bash
./bib-duplicates/find_bib_duplicates.py references.bib
./bib-duplicates/find_bib_duplicates.py references.bib --output report.txt
```

### Card Tracker

Tracks the due dates of your credit cards across last month, this month and next month, with the most urgent card at the top.

- Click an empty month cell to enter the amount due.
- Click a cell with an amount to toggle it paid (it turns green).
- Right-click a cell to edit the amount, mark it paid or clear it.
- Click the due date to set the day of the month, and click a card name to rename it (right-click to delete).
- Press `Ctrl+N` to add a card and `Ctrl+Z` to undo the last change (up to 50 changes, while the app is open).
- The currency symbol in reminders is set by `CURRENCY` near the top of the script.

Command-line options:

```bash
card_tracker.py                      # open the app
card_tracker.py --remind             # pop-up for payments due soon, then exit
card_tracker.py --remind --dry-run   # print the reminder instead of a pop-up
card_tracker.py --test-popup         # check that notifications work
```

Your data is stored locally in `~/.local/share/card-tracker/data.json`. It is outside the repository and is never uploaded.

## Scheduled jobs (cron)

Open your crontab:

```bash
crontab -e
```

Add the following lines. They assume the repository is cloned at `~/linux-tools`; adjust the path if it's elsewhere.

```
# Battery notifier: every 5 minutes
*/5 * * * * $HOME/linux-tools/battery-status-notifier/battery_status_notifier.sh

# Card Tracker due-date reminder: every 4 hours (00:00, 04:00, 08:00, 12:00, 16:00, 20:00)
0 */4 * * * $HOME/linux-tools/credit-card-tracker/card_tracker.py --remind
```

Check that they were saved:

```bash
crontab -l
```

Before relying on the schedule, test each job by hand:

```bash
~/linux-tools/battery-status-notifier/battery_status_notifier.sh
~/linux-tools/credit-card-tracker/card_tracker.py --test-popup
~/linux-tools/credit-card-tracker/card_tracker.py --remind --dry-run
```

Notes:

- The Card Tracker reminder stays silent when nothing is overdue or due within 5 days.
- The battery notification repeats on every run while the condition holds, so you get a reminder every 5 minutes until you plug in or unplug the charger.
- Cron runs with a minimal environment, so both scripts set up the display and D-Bus session themselves. Always use full paths in crontab entries.

## License

Released under the MIT License. See [LICENSE](LICENSE) for details.
