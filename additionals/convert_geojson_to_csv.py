#!/usr/bin/env python3
"""
Convert GeoJSON file to CSV format compatible with the ARCEME processor.
Maps uid field to location (DisNo.) column.
"""

import json
import pandas as pd
from pathlib import Path


def convert_geojson_to_csv(
    input_geojson: str,
    output_csv: str
):
    """
    Convert GeoJSON to CSV format for processor input.
    
    Parameters
    ----------
    input_geojson : str
        Path to input GeoJSON file
    output_csv : str
        Path to output CSV file
    """
    # Read GeoJSON
    print(f"Reading GeoJSON from: {input_geojson}")
    with open(input_geojson, 'r') as f:
        geojson_data = json.load(f)
    
    # Extract data from features
    records = []
    for feature in geojson_data['features']:
        properties = feature['properties']
        coords = feature['geometry']['coordinates']
        
        record = {
            'DisNo.': properties['uid'],  # uid as location identifier
            'longitude': coords[0],
            'latitude': coords[1],
            'start_date': properties['startdate'],
            'wocat_id': properties.get('wocat_id', ''),
            'dhp_label': properties.get('dhp_label', ''),
            'country': properties.get('country', '')
        }
        records.append(record)
    
    # Create DataFrame
    df = pd.DataFrame(records)
    
    # Display summary
    print(f"\nConverted {len(df)} locations")
    print(f"\nFirst few rows:")
    print(df.head())
    print(f"\nDate range: {df['start_date'].min()} to {df['start_date'].max()}")
    print(f"Countries: {df['country'].nunique()} unique ({', '.join(df['country'].unique()[:10])}...)")
    
    # Save to CSV
    df.to_csv(output_csv, index=False)
    print(f"\nSaved to: {output_csv}")
    print(f"Total records: {len(df)}")
    
    return df


if __name__ == "__main__":
    # Define paths
    base_dir = Path("/home/eouser/datacubes/data-cubes-arceme")
    input_file = base_dir / "data" / "selection_eu_wocat_dhp_qdoy.geojson"
    output_file = base_dir / "data" / "selection_eu_wocat_dhp_qdoy.csv"
    
    # Run conversion
    df = convert_geojson_to_csv(str(input_file), str(output_file))
