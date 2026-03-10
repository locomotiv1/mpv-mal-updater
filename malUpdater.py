"""
mpv-anilist-updater: Auto-update AniList based on MPV file watching.

Parses anime filenames, finds AniList entries, and updates progress/status.
"""

# Configuration options for anilistUpdater (set in anilistUpdater.conf):
#   DIRECTORIES: List or comma/semicolon-separated string. The directories the script will work on. Leaving it empty will make it work on every video you watch with mpv. Example: DIRECTORIES = ["D:/Torrents", "D:/Anime"]
#   UPDATE_PERCENTAGE: Integer (0-100). The percentage of the video you need to watch before it updates AniList automatically. Default is 85 (usually before the ED of a usual episode duration).
#   SET_COMPLETED_TO_REWATCHING_ON_FIRST_EPISODE: Boolean. If true, when watching episode 1 of a completed anime, set it to rewatching and update progress.
#   UPDATE_PROGRESS_WHEN_REWATCHING: Boolean. If true, allow updating progress for anime set to rewatching. This is for if you want to set anime to rewatching manually, but still update progress automatically.
#   SET_TO_COMPLETED_AFTER_LAST_EPISODE_CURRENT: Boolean. If true, set to COMPLETED after last episode if status was CURRENT.
#   SET_TO_COMPLETED_AFTER_LAST_EPISODE_REWATCHING: Boolean. If true, set to COMPLETED after last episode if status was REPEATING (rewatching).
#   ADD_ENTRY_IF_MISSING: Boolean. If true, automatically add anime to your list when an update is triggered (i.e., when you've watched enough of the episode). Default is False.

# ═══════════════════════════════════════════════════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════

import hashlib
import json
import os
import re
import sys
import time
import webbrowser
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import requests
from guessit import guessit  # type: ignore

# ═══════════════════════════════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class SeasonEpisodeInfo:
    """Season and episode info for absolute numbering."""

    season_id: int | None
    season_title: str | None
    progress: int | None
    episodes: int | None
    relative_episode: int | None


@dataclass
class AnimeInfo:
    """Anime information including progress and status."""

    anime_id: int | None
    anime_name: str | None
    current_progress: int | None
    total_episodes: int | None
    file_progress: int | None
    current_status: str | None

    # Can not specify the type further. Causes some of the the variables type checking to be unhappy.
    def __iter__(self) -> Iterator[Any]:  # fmt: off
        """Allow tuple unpacking of AnimeInfo."""
        return iter((self.anime_id, self.anime_name, self.current_progress, self.total_episodes, self.file_progress, self.current_status))  # fmt: off


@dataclass
class FileInfo:
    """Parsed filename information."""

    name: str
    episode: int
    year: str
    file_format: str | None

    def __iter__(self) -> Iterator[Any]:
        """Allow tuple unpacking of FileInfo."""
        return iter((self.name, self.episode, self.year, self.file_format))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════
# MAIN ANILIST UPDATER CLASS
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════


class MALUpdater:
    MAL_API_URL: str = "https://api.myanimelist.net/v2"
    AUTH_PATH: str = os.path.join(os.path.dirname(__file__), "mal_auth.json")

    # --- Restoring the missing variables ---
    CACHE_PATH: str = os.path.join(os.path.dirname(__file__), "cache.json")
    OPTIONS: dict[str, Any] = {"excludes": ["country", "language"]}
    CACHE_REFRESH_RATE: int = 24 * 60 * 60

    _CHARS_TO_REPLACE: str = r'\/:!*?"<>|._-'
    # Matches any of the chars, only if not followed by a whitespace and a digit.
    CLEAN_PATTERN: str = rf"(?: - Movie)|[{re.escape(_CHARS_TO_REPLACE)}](?!\s*\d)"
    VERSION_REGEX: re.Pattern[str] = re.compile(r"(E\d+)v\d")

    # ──────────────────────────────────────────────────────────────────────────────────────────────────
    # INITIALIZATION & TOKEN HANDLING
    # ──────────────────────────────────────────────────────────────────────────────────────────────────

    def __init__(self, options: dict[str, Any], action: str) -> None:
        self.access_token: str | None = self.load_access_token()
        self.options: dict[str, Any] = options
        self.ACTION: str = action
        self._cache: dict[str, Any] | None = None

    def load_access_token(self) -> str | None:
        """
        Load access token from file, supporting legacy formats.

        Returns:
            str | None: Access token or None if not found.
        """
        try:
            if not os.path.exists(self.AUTH_PATH):
                print(f"Auth file not found at {self.AUTH_PATH}. Please run setup_auth.py first.")
                return None
            with open(self.AUTH_PATH, encoding="utf-8") as f:
                auth_data = json.load(f)
            return auth_data.get("access_token")

        except Exception as e:
            print(f"Error reading access token: {e}")
            return None

    def cleanup_legacy_formats(self, lines: list[str], has_legacy_user_id: bool) -> str:
        """
        Clean legacy cache entries and user_id from token file.

        Args:
            lines (list[str]): Lines read from token file.
            has_legacy_user_id (bool): Whether first line has user_id:token format.

        Returns:
            str: Cleaned token.
        """
        token = ""
        try:
            header = lines[0] if lines else ""

            # Extract just the token if it's in user_id:token format
            token = header.split(":", 1)[1].strip() if has_legacy_user_id and ":" in header else header.strip()

            # Rewrite token file with just the token, removing user_id and cache lines
            with open(self.AUTH_PATH, "w", encoding="utf-8") as f:
                f.write(token + ("\n" if token else ""))

            if has_legacy_user_id:
                print("Cleaned up legacy user_id from token file.")
            if any(";;" in ln for ln in lines):
                print("Cleaned up legacy cache entries from token file.")
        except Exception as e:
            print(f"Legacy format cleanup failed: {e}")

        return token

    # ──────────────────────────────────────────────────────────────────────────────────────────────────
    # CACHE MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────────────────────────────

    def cache_to_file(self, path: str, guessed_name: str, absolute_progress: int, result: AnimeInfo) -> None:
        """
        Store/update cache entry for anime information.

        Args:
            path (str): File path.
            guessed_name (str): Guessed anime name.
            absolute_progress (int): Absolute episode number.
            result (AnimeInfo): Anime information to cache.
        """
        try:
            dir_hash = self.hash_path(os.path.dirname(path))
            cache = self.load_cache()

            anime_id, _, current_progress, total_episodes, relative_progress, current_status = result

            now = time.time()

            cache[dir_hash] = {
                "guessed_name": guessed_name,
                "anime_id": anime_id,
                "current_progress": current_progress,
                "relative_progress": f"{absolute_progress}->{relative_progress}",
                "total_episodes": total_episodes,
                "current_status": current_status,
                "ttl": now + self.CACHE_REFRESH_RATE,
            }

            self.save_cache(cache)
        except Exception as e:
            print(f"Error trying to cache {result}: {e}")

    def hash_path(self, path: str) -> str:
        """
        Generate SHA256 hash of path.

        Args:
            path (str): Path to hash.

        Returns:
            str: Hashed path.
        """
        return hashlib.sha256(path.encode("utf-8")).hexdigest()

    def check_and_clean_cache(self, path: str, guessed_name: str) -> dict[str, Any] | None:
        """
        Get valid cache entry and clean expired entries.

        Args:
            path (str): Path to media file.
            guessed_name (str): Guessed anime name.

        Returns:
            dict[str, Any] | None: Cache entry or None if not found/valid.
        """
        try:
            cache = self.load_cache()
            now = time.time()
            changed = False
            # Purge expired
            for k, v in list(cache.items()):
                if v.get("ttl", 0) < now:
                    cache.pop(k, None)
                    changed = True
            if changed:
                self.save_cache(cache)

            dir_hash = self.hash_path(os.path.dirname(path))
            entry = cache.get(dir_hash)

            if entry and entry.get("guessed_name") == guessed_name:
                return entry

            return None
        except Exception as e:
            print(f"Error trying to read cache file: {e}")
            return None

    def load_cache(self) -> dict[str, Any]:
        """
        Load cache from JSON file with lazy loading.

        Returns:
            dict[str, Any]: Cache data or empty dict if file doesn't exist.
        """
        if self._cache is None:
            try:
                if not os.path.exists(self.CACHE_PATH):
                    self._cache = {}
                else:
                    with open(self.CACHE_PATH, encoding="utf-8") as f:
                        self._cache = json.load(f)
            except Exception:
                self._cache = {}
        # At this point, self._cache is guaranteed to be a dict
        assert self._cache is not None
        return self._cache

    def save_cache(self, cache: dict[str, Any]) -> None:
        """
        Save cache dictionary to JSON file.

        Args:
            cache (dict[str, Any]): Cache data to save.
        """
        try:
            with open(self.CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            # Keep local cache in sync
            self._cache = cache
        except Exception as e:
            print(f"Failed saving cache.json: {e}")

    # ──────────────────────────────────────────────────────────────────────────────────────────────────
    # API COMMUNICATION
    # ──────────────────────────────────────────────────────────────────────────────────────────────────

    # Function to make an api request to AniList's api
    def make_api_request(
        self, endpoint: str, method: str = "GET", data: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Make REST request to MyAnimeList API v2."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.MAL_API_URL}/{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=data, timeout=10)
            elif method in {"PATCH", "POST", "PUT"}:
                # MAL requires x-www-form-urlencoded for modifying list entries
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                response = requests.patch(url, headers=headers, data=data, timeout=10)
            else:
                # This explicitly handles any other method so Pyright knows 'response' is safe
                print(f"Unsupported HTTP method: {method}")
                return None

            # 200 OK, 201 Created, 204 No Content
            if response.status_code in {200, 201, 204}:
                return response.json() if response.text else {}

            print(
                f"API request failed: {response.status_code} - {response.text}\nEndpoint: {endpoint}\nData: {data}"
            )
            return None
        except Exception as e:
            print(f"Request error: {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────────────────────────────────
    # SEASON & EPISODE HANDLING
    # ──────────────────────────────────────────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────────────────────────────────────────
    # FILE PROCESSING & PARSING
    # ──────────────────────────────────────────────────────────────────────────────────────────────────

    def handle_filename(self, filename: str) -> None:
        """
        Handle file processing: parse, check cache, update AniList.

        Args:
            filename (str): Path to video file.
        """
        file_info = self.parse_filename(filename)
        cache_entry = self.check_and_clean_cache(filename, file_info.name)
        result = None

        # If launching and cache has anime_id, we can skip search and open directly.
        if self.ACTION == "launch" and cache_entry and cache_entry.get("anime_id"):
            anime_id = cache_entry["anime_id"]
            print(f'Opening MAL (cached) for guessed "{file_info.name}": https://myanimelist.net/anime/{anime_id}')
            osd_message(f'Opening MAL for "{file_info.name}"')
            webbrowser.open_new_tab(f"https://myanimelist.net/anime/{anime_id}")
            return

        # Use cached data if available, otherwise fetch fresh info
        if cache_entry:
            print(f'Using cached data for "{file_info.name}"')

            left, right = cache_entry.get("relative_progress", "0->0").split("->")
            # For example, if 19->7, that means that 19 absolute is equivalent to 7 relative to this season
            # File episode 20: 20 - 19 + 7 = 8 relative to this season
            offset = int(left) - int(right)

            relative_episode = file_info.episode - offset

            if 1 <= relative_episode <= (cache_entry.get("total_episodes") or 0):
                # Reconstruct result from cache
                result = AnimeInfo(
                    cache_entry["anime_id"],
                    cache_entry["guessed_name"],
                    cache_entry["current_progress"],
                    cache_entry["total_episodes"],
                    relative_episode,
                    cache_entry["current_status"],
                )

        # At this point, we guess using the guessed name and other information
        if result is None:
            result = self.get_anime_info_and_progress(file_info)

        result = self.update_episode_count(result)

        if result and result.current_progress is not None:
            # Update cache with latest data
            self.cache_to_file(filename, file_info.name, file_info.episode, result)
        return

    # Attempt to improve detection
    def fix_filename(self, path_parts: list[str]) -> list[str]:
        """
        Apply hardcoded fixes to filename/folder structure for better detection.

        Args:
            path_parts (list[str]): Path components.

        Returns:
            list[str]: Modified path components.
        """
        # Before using guessit, clean up the filename
        path_parts[-1] = re.sub(self.CLEAN_PATTERN, " ", path_parts[-1])
        path_parts[-1] = " ".join(path_parts[-1].split())

        # Remove 'v2', 'v3'... from the title since it fucks up with episode detection
        match = self.VERSION_REGEX.search(path_parts[-1])
        if match:
            episode = match.group(1)
            path_parts[-1] = path_parts[-1].replace(match.group(0), episode)

        return path_parts

    # Parse the file name using guessit
    def parse_filename(self, filepath: str) -> FileInfo:
        """
        Parse filename/folder structure to extract anime info.

        Args:
            filepath (str): Path to video file.

        Raises:
            Exception: If no title is found from file name and the folders it is in.

        Returns:
            FileInfo: Parsed info with name, episode, year.
        """
        path_parts = self.fix_filename(filepath.replace("\\", "/").split("/"))
        filename = path_parts[-1]
        guessed_name, season, part, year = "", "", "", ""
        remaining: list[int] = []
        # First, try to guess from the filename
        guess = guessit(filename, self.OPTIONS)

        print(f"File name guess: {filename} -> {dict(guess)}")

        # Episode guess from the title.
        # Usually, releases are formated [Release Group] Title - S01EX

        # If the episode index is 0, that would mean that the episode is before the title in the filename
        # Which is a horrible way of formatting it, so assume its wrong

        # If its 1, then the title is probably 0, so its okay. (Unless season is 0)
        # Really? What is the format "S1E1 - {title}"? That's almost psycopathic.

        # If its >2, theres probably a Release Group and Title / Season / Part, so its good

        episode = guess.get("episode", None)
        season = guess.get("season", "")
        part = str(guess.get("part", ""))
        year = str(guess.get("year", ""))
        file_format = None

        # Right now, only detect both these formats
        other = guess.get("other", "")
        if other == "Original Animated Video":
            file_format = "OVA"
        elif other == "Original Net Animation":
            file_format = "ONA"

        # Quick fixes assuming season before episode
        # 'episode_title': '02' in 'S2 02'
        if guess.get("episode_title", "").isdigit() and "episode" not in guess:
            print(f"Detected episode in episode_title. Episode: {int(guess.get('episode_title'))}")
            episode = int(guess.get("episode_title"))

        # 'episode': [86, 13] (EIGHTY-SIX), [1, 2, 3] (RANMA) lol.
        if isinstance(episode, list):
            print(f"Detected multiple episodes: {episode}. Picking last one.")
            remaining = episode[:-1]
            episode = episode[-1]

        # 'season': [2, 3] in "S2 03"
        if isinstance(season, list):
            print(f"Detected multiple seasons: {season}. Picking first one as season.")
            # If episode wasn't detected or is default, try to extract from season list
            if episode is None and len(season) > 1:
                print("Episode not detected. Picking last position of the season list.")
                episode = season[-1]

            season = season[0]

        # Ensure episode is never None
        episode = episode or 1

        season = str(season)

        keys = list(guess.keys())
        episode_index = keys.index("episode") if "episode" in guess else 1
        season_index = keys.index("season") if "season" in guess else -1
        title_in_filename = "title" in guess and (episode_index > 0 and (season_index > 0 or season_index == -1))
        found_title = title_in_filename

        # If the title is not in the filename or episode index is 0, try the folder name
        # If the episode index > 0 and season index > 0, its safe to assume that the title is in the file name

        if title_in_filename:
            guessed_name = guess["title"]
        else:
            # If it isnt in the name of the file, try to guess using the name of the folder it is stored in

            # Depth=2 folders
            for depth in [2, 3]:
                folder_guess = guessit(path_parts[-depth], self.OPTIONS) if len(path_parts) > depth - 1 else None
                if folder_guess:
                    print(
                        f"{depth - 1}{'st' if depth - 1 == 1 else 'nd'} Folder guess:\n{path_parts[-depth]} -> {dict(folder_guess)}"
                    )

                    guessed_name = str(folder_guess.get("title", ""))
                    season = season or str(folder_guess.get("season", ""))
                    part = part or str(folder_guess.get("part", ""))
                    year = year or str(folder_guess.get("year", ""))

                    # If we got the name, its probable we already got season and part from the way folders are usually structured
                    if guessed_name:
                        found_title = True
                        break

        if not found_title:
            raise Exception(f"Couldn't find title in filename '{filename}'! Guess result: {guess}")

        # Haven't tested enough but seems to work fine
        # If there are remaining episodes, append them to the name
        if remaining:
            guessed_name += " " + " ".join(str(ep) for ep in remaining)

        # Add season and part if there are
        if season and (int(season) > 1 or part):
            guessed_name += f" Season {season}"

        # Rare case where "Part" is in the episode title: "My Hero Academia S06E06 Encounter, Part 2"
        # If episode_title is detected, part must be before it
        episode_title_index = keys.index("episode_title") if "episode_title" in guess else 99

        if part and keys.index("part") < episode_title_index:
            guessed_name += f" Part {part}"

        print(f"Guessed: {guessed_name}{f' {file_format}' if file_format else ''} - E{episode} {year}")
        return FileInfo(guessed_name, episode, year, file_format)

    # ──────────────────────────────────────────────────────────────────────────────────────────────────
    # ANIME INFO & PROGRESS UPDATES
    # ──────────────────────────────────────────────────────────────────────────────────────────────────

    def get_anime_info_and_progress(self, file_info: FileInfo) -> AnimeInfo:
        """
        Query MyAnimeList for anime info and user progress.
        """
        name, file_progress, _year, _file_format = file_info

        # Search MAL via GET request
        endpoint = "anime"
        params = {"q": name, "limit": 5, "fields": "id,title,num_episodes,my_list_status,media_type,status"}

        response = self.make_api_request(endpoint, method="GET", data=params)

        if not response or "data" not in response or not response["data"]:
            raise Exception(f"Couldn't find an anime from this title! ({name}). Is it on your list?")

        # Grab the first valid result from the search query
        first_result = response["data"][0]["node"]

        mal_id = first_result["id"]
        title = first_result["title"]
        total_episodes = first_result.get("num_episodes")

        current_progress = None
        current_status = None

        # Check if the user has this anime on their list
        my_list_status = first_result.get("my_list_status")
        if my_list_status:
            current_progress = my_list_status.get("num_episodes_watched")
            # MAL statuses: watching, completed, on_hold, dropped, plan_to_watch
            current_status = my_list_status.get("status")

        anime_data = AnimeInfo(mal_id, title, current_progress, total_episodes, file_progress, current_status)

        print(f"Final guessed anime: {title}")
        return anime_data

    # Update the anime based on file progress
    def update_episode_count(self, result: AnimeInfo) -> AnimeInfo:
        """
        Update episode count and/or status on MyAnimeList per user settings.
        """
        if result is None:
            raise Exception("Parameter in update_episode_count is null.")

        anime_id, anime_name, current_progress, total_episodes, file_progress, current_status = result

        if anime_id is None:
            raise Exception("Couldn't find that anime! Make sure it is on your list and the title is correct.")

        # Only launch MyAnimeList
        if self.ACTION == "launch":
            osd_message(f'Opening MAL for "{anime_name}"')
            print(f'Opening MAL for "{anime_name}": https://myanimelist.net/anime/{anime_id}')
            webbrowser.open_new_tab(f"https://myanimelist.net/anime/{anime_id}")
            return result

        # Handle ADD_ENTRY_IF_MISSING feature
        if current_progress is None and current_status is None:
            if self.options.get("ADD_ENTRY_IF_MISSING", False):
                print(f'Adding "{anime_name}" to your list since you\'re watching it...')
                initial_status = "watching"

                if file_progress == total_episodes and self.options.get(
                    "SET_TO_COMPLETED_AFTER_LAST_EPISODE_CURRENT", False
                ):
                    initial_status = "completed"

                if self.add_anime_to_list(anime_id, anime_name, initial_status, file_progress):
                    osd_message(f'Added "{anime_name}" to your list with progress: {file_progress}')
                    print(f'Successfully added "{anime_name}" to your list with progress: {file_progress}')
                    return AnimeInfo(
                        anime_id, anime_name, file_progress, total_episodes, file_progress, initial_status
                    )
                raise Exception(f"Failed to add '{anime_name}' to your list.")
            raise Exception("Failed to get current episode count. Is it on your list?")

        status_to_set = None
        is_rewatching = False

        # Handle completed -> rewatching on first episode
        if (
            current_status == "completed"
            and file_progress == 1
            and self.options["SET_COMPLETED_TO_REWATCHING_ON_FIRST_EPISODE"]
        ):
            print("Setting status to watching (rewatching) for first episode of completed anime.")
            status_to_set = "watching"
            is_rewatching = True

        # Only update if status is watching, plan_to_watch, or on_hold
        elif current_status in {"watching", "plan_to_watch", "on_hold"}:
            if file_progress and current_progress is not None and file_progress <= current_progress:
                raise Exception(f"Episode was not new. Not updating ({file_progress} <= {current_progress})")
            status_to_set = "watching"
        else:
            raise Exception(f"Anime is not in a modifiable state (status: {current_status}). Not updating.")

        # Set to COMPLETED if last episode
        if file_progress == total_episodes and self.options["SET_TO_COMPLETED_AFTER_LAST_EPISODE_CURRENT"]:
            status_to_set = "completed"
            is_rewatching = False

        # Make the PATCH request
        endpoint = f"anime/{anime_id}/my_list_status"
        update_data = {"num_watched_episodes": file_progress}

        if status_to_set:
            update_data["status"] = status_to_set
        if is_rewatching:
            update_data["is_rewatching"] = True

        response = self.make_api_request(endpoint, method="PATCH", data=update_data)

        if response and "num_episodes_watched" in response:
            updated_progress = response["num_episodes_watched"]
            updated_status = response["status"]
            osd_message(f'Updated "{anime_name}" to: {updated_progress}')
            print(f"Episode count updated successfully! New progress: {updated_progress}")
            return AnimeInfo(anime_id, anime_name, updated_progress, total_episodes, file_progress, updated_status)

        print("Failed to update episode count.")
        raise Exception("Failed to update episode count.")

    def add_anime_to_list(
        self, anime_id: int, anime_name: str, initial_status: str = "plan_to_watch", initial_progress: int = 0
    ) -> bool:
        """
        Add an anime to the user's MyAnimeList.
        """
        try:
            endpoint = f"anime/{anime_id}/my_list_status"
            update_data = {"status": initial_status, "num_watched_episodes": initial_progress}

            response = self.make_api_request(endpoint, method="PATCH", data=update_data)

            # MAL returns the list status object upon successful creation
            if response and "status" in response:
                return True

            print(f'Failed to add "{anime_name}" to your list.')
            return False
        except Exception as e:
            print(f'Error adding "{anime_name}" to list: {e}')
            return False


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════


def osd_message(msg: str) -> None:
    """Display an on-screen display (OSD) message."""
    print(f"OSD:{msg}")


def main() -> None:
    """Main entry point for the script."""
    try:
        # Reconfigure to utf-8
        if sys.stdout.encoding != "utf-8":
            try:
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
                sys.stderr.reconfigure(encoding="utf-8")  # type: ignore
            except Exception as e_reconfigure:
                print(f"Couldn't reconfigure stdout/stderr to UTF-8: {e_reconfigure}", file=sys.stderr)

        # Parse options from argv[3] if present
        options = {
            "SET_COMPLETED_TO_REWATCHING_ON_FIRST_EPISODE": False,
            "UPDATE_PROGRESS_WHEN_REWATCHING": True,
            "SET_TO_COMPLETED_AFTER_LAST_EPISODE_CURRENT": False,
            "SET_TO_COMPLETED_AFTER_LAST_EPISODE_REWATCHING": True,
            "ADD_ENTRY_IF_MISSING": False,
        }
        if len(sys.argv) > 3:
            user_options = json.loads(sys.argv[3])
            options.update(user_options)

        # Pass options to AniListUpdater
        updater = MALUpdater(options, sys.argv[2])
        updater.handle_filename(sys.argv[1])

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
