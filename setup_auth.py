import secrets
import requests
import urllib.parse
import json
import os

AUTH_FILE = "mal_auth.json"


def main():
    print("=== MyAnimeList MPV Updater Setup ===")
    print("To use this script, you need a MAL Client ID.")
    print("1. Go to https://myanimelist.net/apiconfig")
    print("2. Create a new App (App Type: 'other', Redirect URL: 'http://localhost')")
    print("3. Copy the Client ID and paste it below.\n")

    client_id = input("Enter your MAL Client ID: ").strip()

    if not client_id:
        print("Client ID cannot be empty. Exiting.")
        return

    # Generate a secure code verifier for PKCE
    code_verifier = secrets.token_urlsafe(96)[:128]

    # Generate the Auth URL
    auth_url = f"https://myanimelist.net/v1/oauth2/authorize?response_type=code&client_id={client_id}&code_challenge={code_verifier}"

    print("\n--- AUTHORIZATION STEP ---")
    print("1. Go to this URL in your web browser and click 'Allow':\n")
    print(auth_url)
    print("\n2. After allowing, you will be redirected to an empty/broken localhost page.")
    print("3. Copy the ENTIRE URL from your browser's address bar and paste it below.\n")

    redirect_url = input("Paste the redirected URL here: ").strip()

    # Extract the code from the URL
    try:
        parsed_url = urllib.parse.urlparse(redirect_url)
        auth_code = urllib.parse.parse_qs(parsed_url.query).get("code", [None])[0]
    except Exception:
        auth_code = None

    if not auth_code:
        print(
            "Error: Could not find the authorization code in the URL. Make sure you pasted the full http://localhost... URL."
        )
        return

    # Exchange the code for tokens
    print("\nRequesting tokens from MAL...")
    data = {
        "client_id": client_id,
        "code": auth_code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
    }

    response = requests.post("https://myanimelist.net/v1/oauth2/token", data=data)

    if response.status_code == 200:
        token_data = response.json()

        # Save everything to our auth file
        auth_payload = {
            "client_id": client_id,
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
        }

        with open(AUTH_FILE, "w") as f:
            json.dump(auth_payload, f, indent=4)

        print(f"\nSuccess! Authentication data saved to {AUTH_FILE}")
        print("You are now ready to use the MPV script!")
    else:
        print(f"Failed to get token: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    main()
