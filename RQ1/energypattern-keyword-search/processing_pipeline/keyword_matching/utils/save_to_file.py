import os
from typing import List

import pandas as pd

from constants.abs_paths import AbsDirPath
from models.Repo import Repo
from processing_pipeline.keyword_matching.services.KeywordExtractor import FullMatch
from processing_pipeline.keyword_matching.model.MatchSource import MatchSource


def save_matches_to_file(records: List[FullMatch], source: MatchSource, repo: Repo, *, with_matched_text: bool = False):
    base_dir = AbsDirPath.OPENDX_KEYWORDS_MATCHING
    filename = f'{repo.dotted_ref}.{source.value}.parquet'
    if with_matched_text:
        resulting_filename = base_dir / "full" / filename
    else:
        resulting_filename = base_dir / filename
    os.makedirs(resulting_filename.parent, exist_ok=True)

    if len(records) == 0:
        print(f"No records to save for {repo.id} and source {source.value}")
        return

    #serialized = [record.as_dict() for record in records]
    serialized = [record.as_dict(keep_text=with_matched_text) for record in records]
    pd.DataFrame(serialized).to_parquet(resulting_filename, engine='pyarrow', compression='snappy', index=False)
