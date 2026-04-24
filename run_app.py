"""PyInstaller entry point — uses absolute imports so it works inside a frozen bundle."""
from disclosure_analyst.gui import main

if __name__ == "__main__":
    main()
