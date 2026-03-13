import dotenv
from tqdm import tqdm

from cfg.patterns import patterns
from cfg.selected_repos import selected_repos
from processing_pipeline.keyword_matching.services.KeywordExtractor import RepoDataKeywordExtractor
from processing_pipeline.keyword_matching.model.MatchSource import MatchSource
from processing_pipeline.keyword_matching.services.MongoDB import MongoDB
from processing_pipeline.keyword_matching.utils.save_to_file import save_matches_to_file

dotenv.load_dotenv()

def main():
    for repo in tqdm(selected_repos, desc="Parsing repos"):
        tqdm.write(f"Parsing github metadata for {repo}")

        db = MongoDB(repo)
        keyword_parser = RepoDataKeywordExtractor(patterns, repo, db=db)

        save_matches_to_file(keyword_parser.parse_issues(), MatchSource.ISSUE, repo)
        save_matches_to_file(keyword_parser.parse_issue_comments(), MatchSource.ISSUE_COMMENT, repo)
        save_matches_to_file(keyword_parser.parse_releases(), MatchSource.RELEASE, repo)

    print("Done!")


if __name__ == "__main__":
    main()
