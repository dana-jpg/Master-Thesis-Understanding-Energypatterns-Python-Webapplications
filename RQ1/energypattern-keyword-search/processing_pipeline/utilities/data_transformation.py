from pathlib import Path
from typing import List

import pandas as pd
import pyarrow.dataset as ds


def load_all_files(in_dir: Path, *, name_contains: str = None, columns=None):
    files = [file_path for file_path in in_dir.glob("*.parquet") if
             not name_contains or (name_contains in str(file_path))]
    try:
        dataset = ds.dataset(files, format="parquet")
        df = dataset.to_table(columns=columns).to_pandas() if columns else dataset.to_table().to_pandas()
        print(f"Loaded {len(dataset.files)} files, {files}")
        return df
    except Exception as e:
        print(f"Error while loading dataset: {e}")
        return pd.DataFrame()
