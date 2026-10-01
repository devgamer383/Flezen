import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flezen import Flezen, FlezenAuthError



def main():
    # Initialize client (replace with valid credentials or tokens)
    client = Flezen(
        email="user@example.com",
        password="YourPassword123",
        auto_login=False,  # Set to True when using real credentials
    )

    print("Flezen SDK Initialized!")
    print("Public URL sample:", Flezen.get_public_url("datnfupbjlnn77sojlo0g-myqmbnsvw"))
    print("Android Intent deep link:", Flezen.get_intent_url("datnfupbjlnn77sojlo0g-myqmbnsvw"))


if __name__ == "__main__":
    main()
