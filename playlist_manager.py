import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import csv
import time
from datetime import datetime

# Spotify API credentials
client_id = 'your_client_id'
client_secret = 'your_client_secret'
redirect_uri = 'http://localhost:8000/callback/'

# Rate-limiting constants
MAX_CALLS_PER_MINUTE = 180
call_count = 0
start_time = datetime.now()

# Initialize Spotify API client with both scopes
def init_spotify(scope):
    return spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id,
                                                     client_secret=client_secret,
                                                     redirect_uri=redirect_uri,
                                                     scope=scope))

# Rate-limit checking function
def rate_limit_check():
    global call_count, start_time
    call_count += 1
    elapsed_time = (datetime.now() - start_time).total_seconds()
    if call_count >= MAX_CALLS_PER_MINUTE:
        if elapsed_time < 60:
            time_to_wait = 60 - elapsed_time
            print(f"Rate limit reached. Waiting for {time_to_wait:.2f} seconds.")
            time.sleep(time_to_wait)
        call_count = 0
        start_time = datetime.now()

# Export Spotify playlists to CSV
def export_playlists():
    scope = "playlist-read-private"
    sp = init_spotify(scope)
    
    # Generate the filename with the current username and date
    username = sp.current_user()['id']
    date_str = datetime.now().strftime("%Y%m%d")
    csv_filename = f'spotify_backup_{username}_{date_str}.csv'
    
    # Create CSV file and write headers
    with open(csv_filename, 'w', encoding='utf-8', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['artist_id', 'track_id', 'album_id', 'artist_name', 'track_name', 'album_name', 'track_popularity', 'release_date', 'playlist_id', 'playlist_name', 'playlist_index'])

        # Initialize the first playlist request
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
                        track_id = track['track']['id']
                        artist_id = track['track']['artists'][0]['id']
                        album_id = track['track']['album']['id']
                        artist_name = track['track']['artists'][0]['name']
                        track_name = track['track']['name']
                        album_name = track['track']['album']['name']
                        track_popularity = track['track']['popularity']
                        release_date = track['track']['album']['release_date']
                        playlist_id = playlist['id']
                        playlist_name = playlist['name']
                        csv_writer.writerow([artist_id, track_id, album_id, artist_name, track_name, album_name, track_popularity, release_date, playlist_id, playlist_name, playlist_index])

                    offset += len(tracks['items'])
                    if not tracks['next']:
                        break

                print(f"Playlist '{playlist['name']}' exported.")
                # Progress update
                print(f"Export progress: {playlist_index}/{total_playlists}")
                playlist_index += 1

            # Fetch the next set of playlists
            playlists = sp.next(playlists) if playlists['next'] else None

    print(f"Playlists exported successfully to {csv_filename}.")


def import_playlists():
    scope = "playlist-modify-public playlist-modify-private playlist-read-private"
    sp = init_spotify(scope)

    def list_csv_files():
        files = [f for f in os.listdir('.') if f.startswith('spotify_backup') and f.endswith('.csv')]
        return files

    def select_csv_file(files):
        print("Available CSV files:")
        for i, file in enumerate(files):
            print(f"{i + 1}. {file}")
        
        file_index = int(input(f"\nSelect a CSV file by number (1-{len(files)}): ")) - 1
        
        if 0 <= file_index < len(files):
            return files[file_index]
        else:
            print("Invalid selection.")
            return None

    def get_playlist_tracks_from_csv(csv_filename, playlist_name):
        tracks = []
        with open(csv_filename, 'r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                if row['playlist_name'] == playlist_name:
                    tracks.append(row['track_id'])
        return tracks

    def create_new_playlist(user_id, playlist_name, tracks):
        playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=False)
        rate_limit_check()
        playlist_id = playlist['id']
        for i in range(0, len(tracks), 100):
            sp.playlist_add_items(playlist_id, tracks[i:i+100])
            rate_limit_check()
        print(f"Playlist '{playlist_name}' created successfully with {len(tracks)} tracks.")

    csv_files = list_csv_files()
    
    if not csv_files:
        print("No CSV files found starting with 'spotify_backup'.")
        return

    selected_file = select_csv_file(csv_files)
    
    if not selected_file:
        return

    playlists = []
    with open(selected_file, 'r', encoding='utf-8') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            if row['playlist_name'] not in playlists:
                playlists.append(row['playlist_name'])

    if not playlists:
        print("No playlists found in the selected CSV file.")
        return

    print("Available playlists:")
    for i, playlist in enumerate(playlists):
        print(f"{i + 1}. {playlist}")

    user_input = input(f"\nEnter playlist numbers, ranges, or 'all' (e.g., 1,3,5-7 or all): ")

    if user_input.lower() == 'all':
        indices = list(range(1, len(playlists) + 1))
    else:
        indices = parse_input(user_input, len(playlists))

    if not indices:
        print("No valid playlists selected.")
        return

    user_id = sp.current_user()['id']
    rate_limit_check()

    total_playlists = len(indices)
    print(f"Total playlists to import: {total_playlists}")

    for i in indices:
        playlist_name = playlists[i - 1]
        print(f"\nImporting playlist: {playlist_name}")
        tracks = get_playlist_tracks_from_csv(selected_file, playlist_name)

        if not tracks:
            print(f"No tracks found for playlist: {playlist_name}")
            continue

        create_new_playlist(user_id, playlist_name, tracks)

        # Progress update
        print(f"Import progress: {i}/{total_playlists}")

def parse_input(input_str, max_value):
    indices = set()
    parts = input_str.split(',')

    for part in parts:
        if '-' in part:
            start, end = map(int, part.split('-'))
            if start <= end and start >= 1 and end <= max_value:
                indices.update(range(start, end + 1))
        else:
            try:
                index = int(part)
                if 1 <= index <= max_value:
                    indices.add(index)
            except ValueError:
                # Handle the case where part is not an integer
                continue

    return sorted(indices)


def main():
    print("Select an option:")
    print("1. Export Spotify playlists")
    print("2. Import Spotify playlists")

    choice = input("Enter your choice (1 or 2): ")

    if choice == '1':
        export_playlists()
    elif choice == '2':
        import_playlists()
    else:
        print("Invalid choice. Please enter 1 or 2.")

if __name__ == "__main__":
    main()
