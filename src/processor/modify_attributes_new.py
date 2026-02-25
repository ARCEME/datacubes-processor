import json
from pathlib import Path

ROOT = Path("/ARCEME-MERGE/TEST-ATTR/")
FILL_VALUE_UINT16 = 65535

def process_zmetadata(zmeta_path: Path) -> bool:
    with zmeta_path.open("r") as f:
        zmeta = json.load(f)

    metadata = zmeta.get("metadata", {})
    modified = False
    changed_arrays = []

    for key, value in metadata.items():
        if not key.endswith("/.zarray"):
            continue

        if value.get("dtype") == "<u2" and value.get("fill_value") is None:
            value["fill_value"] = FILL_VALUE_UINT16
            modified = True
            changed_arrays.append(key.replace("/.zarray", ""))

    if modified:
        with zmeta_path.open("w") as f:
            json.dump(zmeta, f, indent=4)

    return modified, changed_arrays


def main():
    for zarr in sorted(ROOT.glob("*.zarr")):
        zmeta = zarr / ".zmetadata"
        if not zmeta.exists():
            continue

        modified, arrays = process_zmetadata(zmeta)

        print(f"\nProcessed: {zarr.name}")
        if modified:
            print("Updated arrays:")
            for a in arrays:
                print(f"  - {a}")
        else:
            print("No changes needed")

        # <<< STOP AFTER FIRST ZARR >>>
        break


if __name__ == "__main__":
    main()
