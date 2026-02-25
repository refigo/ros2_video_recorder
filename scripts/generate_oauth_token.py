#!/usr/bin/env python3

import argparse

from google_auth_oauthlib.flow import InstalledAppFlow


def parse_args():
    parser = argparse.ArgumentParser(description="Generate Google OAuth token for Drive uploads")
    parser.add_argument("--client-secrets", required=True, help="Path to OAuth client secrets JSON")
    parser.add_argument("--out", default="gdrive_token.json", help="Output token JSON path")
    parser.add_argument(
        "--scopes",
        default="https://www.googleapis.com/auth/drive",
        help="Comma-separated OAuth scopes",
    )
    parser.add_argument(
        "--oob",
        action="store_true",
        help="Use copy/paste flow (OOB). May be blocked for new clients.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    scopes = [scope.strip() for scope in args.scopes.split(",") if scope.strip()]

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, scopes)
    if args.oob:
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(prompt="consent")
        print("Open this URL in your browser and authorize access:\n")
        print(auth_url)
        code = input("\nEnter the authorization code: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials
    else:
        creds = flow.run_local_server(port=0)

    with open(args.out, "w") as handle:
        handle.write(creds.to_json())
    print(f"Saved token to {args.out}")


if __name__ == "__main__":
    main()
