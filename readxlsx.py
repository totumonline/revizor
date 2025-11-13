import pandas as pd
import json
import argparse
import sys

# Function for automatically renaming duplicate columns
def make_unique_columns(columns):
    seen = {}
    unique_columns = []
    for col in columns:
        if col in seen:
            seen[col] += 1
            unique_columns.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            unique_columns.append(col)
    return unique_columns

# Command-line argument parser setup
parser = argparse.ArgumentParser(description="Extract tables and text from an Excel file.")
parser.add_argument("xlsx_path", type=str, help="Path to the Excel file")
args = parser.parse_args()
xlsx_path = args.xlsx_path

# List to store data from all tables and texts
data = {"sheets": []}

# Open the Excel file and extract data
xls = pd.ExcelFile(xlsx_path)
for sheet_name in xls.sheet_names:
    df = xls.parse(sheet_name, dtype=str)  # Read data as strings
    df.columns = make_unique_columns(df.columns)
    data["sheets"].append({
        "sheet_name": sheet_name,
        "data": df.to_dict(orient="records")
    })

# Output JSON to stdout
sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=4) + "\n")
