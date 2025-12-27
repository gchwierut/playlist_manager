import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import csv
import time
from datetime import datetime
import tkinter as tk
from tkinter import filedialog

# ==========================================
# CONFIGURATION
# ==========================================

# ⚠️ SECURITY WARNING: Replace these with your actual credentials.
client_id = 'null'
client_secret = 'null'
redirect_uri = 'http://127.0.0.1:8000/callback/'

# Rate-limiting constants
MAX_CALLS_PER_MINUTE = 60
call_count = 0
start_time = datetime.now()

# ==========================================
# CORE FUNCTIONS
# ==========================================

def init_spotify(scope):
    """Initialize Spotify API client with the requested scope."""
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope
    ))

def rate_limit_check():
    """Prevents hitting Spotify's API rate limits."""
    global call_count, start_time
    call_count += 1
    elapsed_time = (datetime.now() - start_time).total_seconds()

    if call_count >= MAX_CALLS_PER_MINUTE:
        if elapsed_time < 60:
            time_to_wait = 60 - elapsed_time + 1  # Add 1s buffer
            print(f"Rate limit reached. Waiting for {time_to_wait:.2f} seconds.")
            time.sleep(time_to_wait)
        call_count = 0
        start_time = datetime.now()

# ==========================================
# OPTION 1: EXPORT PLAYLISTS
# ==========================================

def export_playlists():
    scope = "playlist-read-private"
    sp = init_spotify(scope)

    username = sp.current_user()['id']
    date_str = datetime.now().strftime("%Y%m%d")
    csv_filename = f'spotify_backup_{username}_{date_str}.csv'

    with open(csv_filename, 'w', encoding='utf-8', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['artist_id', 'track_id', 'album_id', 'artist_name', 'track_name', 'album_name', 'track_popularity', 'release_date', 'playlist_id', 'playlist_name', 'playlist_index'])

        playlists = sp.current_user_playlists(limit=50)
        total_playlists = playlists['total']
        print(f"Total playlists to export: {total_playlists}")

        playlist_index = 1

        while playlists:
            for playlist in playlists['items']:
                offset = 0
                while True:
                    rate_limit_check()
                    tracks = sp.playlist_tracks(playlist['id'], offset=offset)

                    for track in tracks['items']:
                        if track.get('track') and track['track'].get('id'):
                            t = track['track']
                            track_id = t['id']
                            artist_id = t['artists'][0]['id'] if t['artists'] else ''
                            album_id = t['album']['id'] if t['album'] else ''
                            artist_name = t['artists'][0]['name'] if t['artists'] else 'Unknown'
                            track_name = t['name']
                            album_name = t['album']['name'] if t['album'] else 'Unknown'
                            track_popularity = t['popularity']
                            release_date = t['album']['release_date'] if t['album'] else ''
                            playlist_id = playlist['id']
                            playlist_name = playlist['name']

                            csv_writer.writerow([artist_id, track_id, album_id, artist_name, track_name, album_name, track_popularity, release_date, playlist_id, playlist_name, playlist_index])

                    offset += len(tracks['items'])
                    if not tracks['next']:
                        break

                print(f"Playlist '{playlist['name']}' exported ({playlist_index}/{total_playlists}).")
                playlist_index += 1

            playlists = sp.next(playlists) if playlists['next'] else None

    print(f"Playlists exported successfully to {csv_filename}.")

# ==========================================
# OPTION 2: IMPORT PLAYLISTS (FROM SINGLE BACKUP)
# ==========================================

def import_playlists():
    scope = "playlist-modify-public playlist-modify-private playlist-read-private"
    sp = init_spotify(scope)

    def list_csv_files():
        return [f for f in os.listdir('.') if f.startswith('spotify_backup') and f.endswith('.csv')]

    csv_files = list_csv_files()
    if not csv_files:
        print("No CSV files found starting with 'spotify_backup'.")
        return

    print("Available CSV files:")
    for i, file in enumerate(csv_files):
        print(f"{i + 1}. {file}")

    try:
        file_index = int(input(f"\nSelect a CSV file by number (1-{len(csv_files)}): ")) - 1
        selected_file = csv_files[file_index]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return

    playlists_map = {}
    with open(selected_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            p_name = row['playlist_name']
            if p_name not in playlists_map:
                playlists_map[p_name] = []
            playlists_map[p_name].append(row['track_id'])

    playlist_names = list(playlists_map.keys())
    print("\nAvailable playlists in backup:")
    for i, p_name in enumerate(playlist_names):
        print(f"{i + 1}. {p_name}")

    user_input = input(f"\nEnter numbers (e.g., 1,3,5-7 or 'all'): ")

    indices = set()
    if user_input.lower() == 'all':
        indices = set(range(len(playlist_names)))
    else:
        parts = user_input.split(',')
        for part in parts:
            if '-' in part:
                try:
                    s, e = map(int, part.split('-'))
                    indices.update(range(s-1, e))
                except ValueError: continue
            else:
                try:
                    indices.add(int(part) - 1)
                except ValueError: continue

    user_id = sp.current_user()['id']

    for idx in indices:
        if 0 <= idx < len(playlist_names):
            p_name = playlist_names[idx]
            track_ids = playlists_map[p_name]
            print(f"\nCreating playlist: {p_name} ({len(track_ids)} tracks)")

            rate_limit_check()
            new_playlist = sp.user_playlist_create(user=user_id, name=p_name, public=False)
            playlist_id = new_playlist['id']

            unique_tracks = list(dict.fromkeys(track_ids))

            for i in range(0, len(unique_tracks), 100):
                chunk = unique_tracks[i:i+100]
                rate_limit_check()
                sp.playlist_add_items(playlist_id, chunk)

            print(f"Finished {p_name}")

# ==========================================
# OPTION 3: IMPORT FROM TXT
# ==========================================

def import_tracks_from_txt():
    scope = "playlist-modify-public playlist-modify-private playlist-read-private"
    sp = init_spotify(scope)

    files = [f for f in os.listdir('.') if f.endswith('.txt')]
    if not files:
        print("No .txt files found.")
        return

    print("Available files:")
    for i, f in enumerate(files):
        print(f"{i+1}. {f}")

    try:
        sel = int(input("Select file: ")) - 1
        filepath = files[sel]
    except:
        print("Invalid.")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        track_ids = []
        for line in f:
            clean = line.strip()
            if clean:
                if 'http' in clean:
                    clean = clean.split('/')[-1].split('?')[0]
                track_ids.append(clean)

    print(f"Found {len(track_ids)} tracks.")
    choice = input("1. New Playlist\n2. Add to Existing\nChoice: ")
    user_id = sp.current_user()['id']

    target_playlist_id = None

    if choice == '1':
        name = input("Playlist Name: ")
        rate_limit_check()
        pl = sp.user_playlist_create(user=user_id, name=name, public=False)
        target_playlist_id = pl['id']
    elif choice == '2':
        print("Please use Option 1 for now.")
        return

    if target_playlist_id:
        for i in range(0, len(track_ids), 100):
            rate_limit_check()
            sp.playlist_add_items(target_playlist_id, track_ids[i:i+100])
        print("Done.")

# ==========================================
# OPTION 4: SPOTIFY DUMP IMPORT (REVERSE CHRONOLOGICAL)
# ==========================================

def import_spotify_dump():
    scope = "playlist-modify-public playlist-modify-private"
    sp = init_spotify(scope)
    user_id = sp.current_user()['id']

    # 1. Open GUI Folder Selector
    print("Opening folder selection dialog...")
    root = tk.Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Select Folder with CSV Files")
    root.destroy()

    if not folder_path:
        print("No folder selected.")
        return

    print(f"Selected folder: {folder_path}")

    # 2. List CSV files
    csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    if not csv_files:
        print("No CSV files found in that folder.")
        return

    print(f"Found {len(csv_files)} CSV files. Analyzing dates to sort them...")

    files_metadata = []

    # 3. Analyze all files first
    for file_name in csv_files:
        full_path = os.path.join(folder_path, file_name)
        track_ids = []
        years = []

        try:
            with open(full_path, 'r', encoding='utf-8') as csv_file:
                csv_reader = csv.DictReader(csv_file)

                for row in csv_reader:
                    # Extract Track ID
                    tid = row.get('track_id', '').strip()
                    if tid:
                        track_ids.append(tid)

                    # Extract Year
                    date_str = row.get('album_release_date', '').strip()
                    if date_str and len(date_str) >= 4:
                        try:
                            year_int = int(date_str[:4])
                            years.append(year_int)
                        except ValueError:
                            pass
        except Exception as e:
            print(f"Error reading {file_name}: {e}")
            continue

        if not track_ids:
            continue

        # Determine Playlist Name
        if not years:
            min_year = 0
            playlist_name = "Spotify Dump [Unknown Year]"
        else:
            min_year = min(years)
            max_year = max(years)

            if min_year == max_year:
                playlist_name = f"Spotify Dump [{min_year}]"
            else:
                playlist_name = f"Spotify Dump [{min_year}-{max_year}]"

        files_metadata.append({
            'filename': file_name,
            'track_ids': track_ids,
            'min_year': min_year,
            'playlist_name': playlist_name
        })

    # 4. Sort files DESCENDING (Newest -> Oldest)
    # This ensures the OLDEST year is created LAST, making it appear at the TOP of the Spotify UI.
    files_metadata.sort(key=lambda x: x['min_year'], reverse=True)

    print(f"\nAnalysis complete. Starting import of {len(files_metadata)} playlists (Newest -> Oldest).\n")

    # 5. Create Playlists
    for index, data in enumerate(files_metadata):
        playlist_name = data['playlist_name']
        track_ids = data['track_ids']
        file_name = data['filename']

        print(f"[{index+1}/{len(files_metadata)}] Creating '{playlist_name}' (from {file_name})...")

        try:
            rate_limit_check()
            playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=False)
            playlist_id = playlist['id']

            # Deduplicate IDs
            unique_ids = list(dict.fromkeys(track_ids))

            # Batch add
            for i in range(0, len(unique_ids), 100):
                batch = unique_ids[i:i+100]
                rate_limit_check()
                sp.playlist_add_items(playlist_id, batch)

            print(f"   -> Success. Added {len(unique_ids)} tracks.")

        except Exception as e:
            print(f"   -> API Error: {e}")

    print("\nAll files processed.")

# ==========================================
# MAIN MENU
# ==========================================

def main():
    print("==================================")
    print("   SPOTIFY MANAGER TOOL           ")
    print("==================================")
    print("1. Export Spotify playlists (Backup)")
    print("2. Import Spotify playlists (Restore)")
    print("3. Import track IDs from a text file")
    print("4. Spotify Dump Import (Folder - Auto-Sort)")
    print("==================================")

    choice = input("Enter your choice (1-4): ")

    if choice == '1':
        export_playlists()
    elif choice == '2':
        import_playlists()
    elif choice == '3':
        import_tracks_from_txt()
    elif choice == '4':
        import_spotify_dump()
    else:
        print("Invalid choice.")

if __name__ == "__main__":
    main()
