"""
main.py — Interactive entry point for crypto-renta.

Usage:
    python main.py

Presents a top-level menu to choose between staking, trades, or both,
then asks for the CSV path. Delegates to staking.run() / trades.run().
"""

import glob
import os
import readline
from pathlib import Path

import staking
import trades
from loaders import select_loader


def _setup_path_completion() -> None:
    def _completer(text: str, state: int):
        matches = glob.glob(text + "*")
        matches = [m + "/" if os.path.isdir(m) else m for m in matches]
        return matches[state] if state < len(matches) else None

    readline.set_completer(_completer)
    readline.set_completer_delims(" \t\n")
    # macOS ships libedit instead of GNU readline — different bind syntax
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")


def _ask_calculation() -> str:
    print("\nWhat do you want to calculate?")
    print("  1) Staking rewards (capital income)")
    print("  2) Trades (capital gains / losses)")
    print("  3) Both")
    print("  q) Quit")
    while True:
        choice = input("Choice: ").strip().lower()
        if choice in ("1", "2", "3", "q"):
            return choice
        print("  Enter 1, 2, 3, or q.")


def _ask_csv_path() -> Path:
    _setup_path_completion()
    while True:
        raw = input("\nCSV path: ").strip()
        path = Path(raw).expanduser()
        if path.is_file():
            return path
        print(f"  File not found: {path}")


def main() -> None:
    print("crypto-renta — Spanish crypto tax calculator")

    choice = _ask_calculation()
    if choice == "q":
        return

    csv_path = _ask_csv_path()
    loader = select_loader()

    if choice in ("1", "3"):
        print("\n--- Staking rewards ---")
        staking.run(csv_path, loader)

    if choice in ("2", "3"):
        if choice == "3":
            print("\n--- Trades ---")
        trades.run(csv_path, loader)


if __name__ == "__main__":
    main()
