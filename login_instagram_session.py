import argparse
import getpass
import os

import instaloader


def main():
    parser = argparse.ArgumentParser(description="Create or replace the local Instaloader session.")
    parser.add_argument("--username", help="Instagram username. If omitted, asks interactively.")
    parser.add_argument("--session-file", default="instaloader.session", help="Session file to write.")
    args = parser.parse_args()

    username = (args.username or input("Instagram username: ")).strip()
    if not username:
        raise SystemExit("Username is required.")

    password = getpass.getpass("Instagram password: ")
    if not password:
        raise SystemExit("Password is required.")

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_video_thumbnails=False,
        download_videos=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )
    loader.login(username, password)
    loader.save_session_to_file(args.session_file)

    session_path = os.path.abspath(args.session_file)
    print(f"Session saved: {session_path}")


if __name__ == "__main__":
    main()
