import keyring
import os

SERVICE = "india-trade-cli"
secret = keyring.get_password(SERVICE, "KITE_API_SECRET")
key = keyring.get_password(SERVICE, "KITE_API_KEY")

print(f"KITE_API_KEY in keychain: {'Found' if key else 'Not Found'}")
print(f"KITE_API_SECRET in keychain: {'Found' if secret else 'Not Found'}")
if key:
    print(f"Key value: {key}")
