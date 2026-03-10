# mpv-mal-updater

A script for MPV that automatically updates your MyAnimeList episode progress based on the local video file you just watched. 

*Forked and adapted from the original [mpv-anilist-updater](https://github.com/AzuredBlue/mpv-anilist-updater) by AzuredBlue.*

> [!IMPORTANT]
> By default, the anime must be set to "watching", "plan_to_watch", or "on_hold" on your MyAnimeList profile to update progress. This is done to prevent accidentally updating the wrong show.<br>
> **Recommendation:** Check out the configuration options in your `malUpdater.conf` file to customize the script to your needs. See the [Configuration](#configuration-malupdaterconf) section for details.<br>

> [!TIP]
> In order for the script to work properly, make sure your files are named correctly:<br>
>
> - Either the file or the folder it is in must have the anime title in it.<br>
> - The file must have the episode number in it (absolute numbering should work).<br>
> - In case of remakes, specify the year of the remake to ensure it updates the proper one.<br>
>
> To avoid the script running and making useless API calls on non-anime videos, you can set one or more target directories in the config file.

## Requirements

You will need **Python 3** installed, as well as the Python libraries `guessit` and `requests`. You can install them via pip:

```bash
pip install guessit requests
```

## Installation & Authentication

Simply `git clone` this repository into your mpv `scripts` folder, or download this repository as a ZIP and extract the contents into your mpv `scripts` folder.

Because MyAnimeList uses strict API authentication, **you will need to generate your own local token** to use this script. A setup script is provided to make this easy:

1. Open a terminal/command prompt inside the `mpv-mal-updater` folder.
2. Run the authentication setup script:
   ```bash
   python setup_auth.py
   ```
3. The script will give you a link to MyAnimeList to register a free API "App". 
   - Set **App Type** to `other`
   - Set **App Redirect URL** to `http://localhost`
4. Copy the generated **Client ID** and paste it into the terminal.
5. Follow the browser prompt to log in and allow access.
6. Paste the redirected localhost URL back into the terminal. 

The script will automatically generate your `mal_auth.json` token file locally. *(Note: This file is ignored by git so your tokens stay safe!).*

## Configuration (`malUpdater.conf`)

When you first run the script in MPV, it will automatically create a configuration file called `malUpdater.conf` if it does not already exist. This file is typically created in your mpv `script-opts` directory. 

**You should edit this file to change any options.**

### Example `malUpdater.conf`

```ini
# Use 'yes' or 'no' for boolean options below
# Example for multiple directories (comma or semicolon separated):
# DIRECTORIES=D:/Torrents,D:/Anime
DIRECTORIES=
EXCLUDED_DIRECTORIES=
UPDATE_PERCENTAGE=85
SET_COMPLETED_TO_REWATCHING_ON_FIRST_EPISODE=no
UPDATE_PROGRESS_WHEN_REWATCHING=yes
SET_TO_COMPLETED_AFTER_LAST_EPISODE_CURRENT=yes
SET_TO_COMPLETED_AFTER_LAST_EPISODE_REWATCHING=yes
ADD_ENTRY_IF_MISSING=no
SILENT_MODE=no
```

#### Option Descriptions

- **DIRECTORIES**: Comma or semicolon separated list of directories. If empty, the script works for every video. Example: `DIRECTORIES=D:/Torrents,D:/Anime`. Manual keybind actions will still work for any file regardless of this setting.
- **EXCLUDED_DIRECTORIES**: Comma or semicolon separated list of directories to ignore. Example: `EXCLUDED_DIRECTORIES=D:/Torrents/Watched`
- **UPDATE_PERCENTAGE**: Number (0-100). The percentage of the video you need to watch before it updates MyAnimeList automatically. Default is `85`.
- **SET_COMPLETED_TO_REWATCHING_ON_FIRST_EPISODE**: `yes`/`no`. If `yes`, when watching episode 1 of a completed anime, it will set it to rewatching. Default is `no`.
- **UPDATE_PROGRESS_WHEN_REWATCHING**: `yes`/`no`. Allow updating progress for anime already set to rewatching. Default is `yes`.
- **SET_TO_COMPLETED_AFTER_LAST_EPISODE_CURRENT**: `yes`/`no`. If `yes`, sets the show to COMPLETED after you finish the last episode. Default is `yes`.
- **ADD_ENTRY_IF_MISSING**: `yes`/`no`. If `yes`, automatically add anime to your list if it's found in the MAL database but not on your profile. **⚠️ Warning: This can add incorrect anime to your list if the file name guess is inaccurate.** Default is `no`.
- **SILENT_MODE**: `yes`/`no`. If `yes`, hides the top-left MPV OSD text messages. Default is `no`.

## Usage

This script has 3 default keybinds:

- **`Ctrl + A`**: Manually forces an update to your MyAnimeList with the current episode you are watching.
- **`Ctrl + B`**: Opens the MyAnimeList page of the anime you are watching in your default web browser. Useful to check if it guessed the right show!
- **`Ctrl + D`**: Opens the folder where the current video is playing in your file explorer.

The script will **automatically update** your MyAnimeList when the video you are watching reaches 85% completion (or whatever percentage you set in the config file).

### Customizing Keybinds

You can change the keybinds by adding these lines to your `input.conf` in your MPV folder:

```text
A script-binding update_mal
B script-binding launch_mal
D script-binding open_folder
```

## How It Works

The script uses `guessit` to parse as much information as possible from the file name.
If the episode and season are positioned before the title, it will try to get the title from the parent folder name instead. Once parsed, it hits the MyAnimeList API to find your show, checks your current progress, and updates it if the local episode is newer.

**Troubleshooting:**
If the script does not update correctly, press `Ctrl + B` to see what MAL page it is trying to open. Try renaming your file or folder so `guessit` has a better chance of reading the title and episode number correctly (e.g., `Show Name - S01E05.mkv`).

## Credits

- Original AniList script by [AzuredBlue](https://github.com/AzuredBlue)
- Inspired by [mpv-open-anilist-page](https://github.com/ehoneyse/mpv-open-anilist-page) by ehoneyse.
