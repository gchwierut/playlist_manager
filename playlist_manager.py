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

        # Deduplicate tracks based on artist name + track name
        deduplicated_tracks = []
        existing_tracks = get_playlist_tracks(playlist_id)

        for track_id in tracks:
            track_details = sp.track(track_id)
            artist_name = track_details['artists'][0]['name']
            track_name = track_details['name']
            artist_track_key = f"{artist_name} - {track_name}"

            if artist_track_key not in existing_tracks:
                deduplicated_tracks.append(track_id)

        for i in range(0, len(deduplicated_tracks), 100):
            sp.playlist_add_items(playlist_id, deduplicated_tracks[i:i+100])
            rate_limit_check()

        print(f"Playlist '{playlist_name}' created successfully with {len(deduplicated_tracks)} unique tracks.")



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

def import_tracks_from_txt():
    scope = "playlist-modify-public playlist-modify-private playlist-read-private"
    sp = init_spotify(scope)

    def list_txt_files():
        """List all .txt files in the current directory."""
        files = [f for f in os.listdir('.') if f.endswith('.txt')]
        return files

    def load_track_ids_from_txt(file_path):
        """Read track URLs from a text file and extract track IDs."""
        with open(file_path, 'r', encoding='utf-8') as file:
            return [line.strip().split("/")[-1] for line in file if line.strip()]

    def get_playlist_tracks(playlist_id):
        """Get all track IDs in a playlist."""
        offset = 0
        track_ids = []
        while True:
            rate_limit_check()
            tracks = sp.playlist_tracks(playlist_id, offset=offset)
            track_ids.extend(track['track']['id'] for track in tracks['items'])
            offset += len(tracks['items'])
            if not tracks['next']:
                break
        return track_ids

    # List available text files
    txt_files = list_txt_files()
    
    if not txt_files:
        print("No .txt files found.")
        return

    print("Available .txt files:")
    for i, file in enumerate(txt_files):
        print(f"{i + 1}. {file}")
    
    file_index = int(input(f"Select a .txt file by number (1-{len(txt_files)}): ")) - 1
    if 0 <= file_index < len(txt_files):
        selected_file = txt_files[file_index]
    else:
        print("Invalid selection.")
        return

    track_ids = load_track_ids_from_txt(selected_file)

    if not track_ids:
        print(f"No track IDs found in {selected_file}.")
        return

    print("Select an option:")
    print("1. Create a new playlist")
    print("2. Add to an existing playlist")
    option = input("Enter your choice (1 or 2): ").strip()

    user_id = sp.current_user()['id']
    rate_limit_check()

    if option == '1':
        # Create a new playlist
        playlist_name = input("Enter the name for the new playlist: ").strip()
        playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=False)
        rate_limit_check()
        playlist_id = playlist['id']

        # Add tracks to the new playlist
        new_tracks = [track_id for track_id in track_ids if track_id not in get_playlist_tracks(playlist_id)]
        
        if not new_tracks:
            print("All tracks are already in the playlist.")
        else:
            for i in range(0, len(new_tracks), 100):
                sp.playlist_add_items(playlist_id, new_tracks[i:i + 100])
                rate_limit_check()

            print(f"New playlist '{playlist_name}' created with {len(new_tracks)} new tracks.")
    
    elif option == '2':
        # Add to an existing playlist
        playlists = sp.current_user_playlists(limit=50)['items']
        if not playlists:
            print("No existing playlists found.")
            return

        print("Available playlists:")
        for i, playlist in enumerate(playlists):
            print(f"{i + 1}. {playlist['name']}")

        playlist_index = int(input("Select a playlist by number: ").strip()) - 1
        if 0 <= playlist_index < len(playlists):
            playlist_id = playlists[playlist_index]['id']
            existing_tracks = get_playlist_tracks(playlist_id)
            new_tracks = [track for track in track_ids if track not in existing_tracks]

            if not new_tracks:
                print("No new tracks to add; all are already in the playlist.")
                return

            for i in range(0, len(new_tracks), 100):
                sp.playlist_add_items(playlist_id, new_tracks[i:i + 100])
                rate_limit_check()

            print(f"{len(new_tracks)} new tracks added to the playlist.")
        else:
            print("Invalid playlist selection.")
    else:
        print("Invalid option. Please choose 1 or 2.")

# Update the main function to include the third option
def main():
    print("Select an option:")
    print("1. Export Spotify playlists")
    print("2. Import Spotify playlists")
    print("3. Import track IDs from a text file")

    choice = input("Enter your choice (1, 2, or 3): ")

    if choice == '1':
        export_playlists()
    elif choice == '2':
        import_playlists()
    elif choice == '3':
        import_tracks_from_txt()
    else:
        print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()

