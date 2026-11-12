#!/bin/bash

# Battery status notifier.
# Checks the battery once and exits, so it is meant to be run by cron every few minutes.
#   - Charging and level >= 80%     -> "Battery Full" notification (remove the charger)
#   - Not charging and level <= 35% -> "Battery Low" notification (connect the charger)
#   - Otherwise nothing to do       -> prints "All Good!" if run from a terminal (silent under cron)

# cron starts jobs without a desktop session, so point notifications at the user's session

export DISPLAY="${DISPLAY:-:0.0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

BATTERY=/org/freedesktop/UPower/devices/battery_BAT0

# Only talks to the terminal when run by hand, so cron stays quiet
all_good() {
    if [ -t 1 ]; then
        echo "All Good!"
    fi
}

battery_level=$(upower -i "$BATTERY" | grep -w percentage | awk '{print $2+0}')
state=$(upower -i "$BATTERY" | grep -w state | awk '{print $2}')

if [ "$state" = "charging" ]; then
    if [ "$battery_level" -ge 80 ]; then
        notify-send -i face-smile "Done charging!" "Remove the charger, battery is already at ${battery_level}%!"
    else
        all_good
    fi
else
    if [ "$battery_level" -le 35 ]; then
        notify-send --urgency=CRITICAL -i face-sad "Start charging!" "Connect the charger, battery level is only ${battery_level}%!"
    else
        all_good
    fi
fi
