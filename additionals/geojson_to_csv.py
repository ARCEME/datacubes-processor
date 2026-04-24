import json
import csv
from pathlib import Path

GEOJSON_PATH = Path(__file__).parent / 'selection_eu_wocat_dhp_qdoy(2).geojson'
CSV_PATH = Path(__file__).parent / 'selection_eu_wocat_dhp_qdoy(2).csv'

def geojson_to_csv(geojson_path, csv_path):
    with open(geojson_path, 'r', encoding='utf-8') as f:
        gj = json.load(f)

    features = gj.get('features', [])
    if not features:
        print('No features found in', geojson_path)
        return

    # define columns: latitude, longitude and properties present in file
    fieldnames = ['latitude', 'longitude', 'uid', 'startdate', 'wocat_id', 'dhp_label', 'country']

    with open(csv_path, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()

        for feat in features:
            geom = feat.get('geometry') or {}
            props = feat.get('properties', {})

            coords = []
            if geom.get('type') == 'Point':
                coords = geom.get('coordinates', [])
            elif geom.get('type') in ('MultiPoint', 'LineString'):
                coords = geom.get('coordinates', [None])[0] or []
            else:
                # try bbox or fallback
                coords = feat.get('bbox', [])

            lon = coords[0] if len(coords) > 0 else None
            lat = coords[1] if len(coords) > 1 else None

            row = {
                'latitude': lat,
                'longitude': lon,
                'uid': props.get('uid'),
                'startdate': props.get('startdate'),
                'wocat_id': props.get('wocat_id'),
                'dhp_label': props.get('dhp_label'),
                'country': props.get('country'),
            }
            writer.writerow(row)

    print(f'Wrote CSV: {csv_path} (rows: {len(features)})')


if __name__ == '__main__':
    geojson_to_csv(GEOJSON_PATH, CSV_PATH)
