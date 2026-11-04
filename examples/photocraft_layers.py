"""Owned PhotoCraft inspection: ADDRESS PORT TOKEN_FILE PERSISTED_DOCUMENT_UUID.

Read the broker credential from stdin. Native credentials never appear in argv.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'sdk'))
from craftlink import Client, CraftLinkError
from photocraft_readonly import PhotoCraftInspector


def main():
    if len(sys.argv) != 5:
        raise SystemExit('usage: photocraft_layers ADDRESS PORT TOKEN_FILE DOCUMENT_UUID')
    try:
        client = Client(sys.argv[1], sys.stdin.readline().strip())
        adapter = PhotoCraftInspector(int(sys.argv[2]), sys.argv[3], sys.argv[4])
        adapter.register_application(client)
        print(json.dumps(adapter.enumerate_objects(), ensure_ascii=True))
    except (CraftLinkError, OSError, ValueError):
        raise SystemExit('Read-only PhotoCraft inspection failed; check the owned session and credentials') from None


if __name__ == '__main__':
    main()
