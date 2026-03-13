import os
import shelve

from loguru import logger

from cfg.patterns import patterns
from cfg.selected_repos import selected_repos
from constants.abs_paths import AbsDirPath
from processing_pipeline.keyword_matching.model.MatchSource import MatchSource
from processing_pipeline.keyword_matching.services.DatasetCounter import DatasetCounter
from processing_pipeline.keyword_matching.services.KeywordExtractor import SourceCodeKeywordExtractor
from processing_pipeline.keyword_matching.utils.save_to_file import save_matches_to_file
from utilities.utils import create_logger_path


def main():
    cache_dir = AbsDirPath.CACHE / "keyword_extraction"
    os.makedirs(cache_dir, exist_ok=True)
    run_id = "03.07.2025_from_docs"
    cache_path = cache_dir / run_id
    logger.add(create_logger_path(run_id), mode="w")
    dataset_counter = DatasetCounter(run_id)
    dataset_counter.restore_datapoints_per_source_count()
    with shelve.open(cache_path) as db:
        for repo in selected_repos:

            logger.info(f"Processing {repo.id}")
            try:
                append_full_text = True

                parser = SourceCodeKeywordExtractor(patterns, repo, append_full_text=append_full_text,
                                                    dataset_counter=dataset_counter)
                if repo.has_wiki():
                    matches_wiki = parser.parse_wiki(str(AbsDirPath.WIKIS / repo.wiki_dir))
                    save_matches_to_file(matches_wiki, MatchSource.WIKI, repo, with_matched_text=append_full_text)
                    print(f"Found {len(matches_wiki)} matches in wiki for {repo.id}")

                source_code_path = str(AbsDirPath.SOURCE_CODE / repo.id)
                matches_code_comments = parser.parse_comments(source_code_path)
                print(f"Found {len(matches_code_comments)} matches in code comments for {repo.id}")
                save_matches_to_file(matches_code_comments, MatchSource.CODE_COMMENT, repo,
                                     with_matched_text=append_full_text)

                matches_docs = parser.parse_docs(source_code_path)
                print("this is the path where we look for docs:", source_code_path)
                save_matches_to_file(matches_docs, MatchSource.DOCS, repo, with_matched_text=append_full_text)
            except Exception as e:
                logger.error(f"Error processing {repo.id}: {str(e)}")
            finally:
                db["last_processed"] = repo.id
    dataset_counter.save_datapoints_per_source_count()


if __name__ == "__main__":
    main()
