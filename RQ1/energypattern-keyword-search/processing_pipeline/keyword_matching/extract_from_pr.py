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
        tqdm.write(f"Parsing github PRs metadata for {repo}")

        db = MongoDB(repo)
        keyword_parser = RepoDataKeywordExtractor(patterns, repo, db=db)

        save_matches_to_file(keyword_parser.parse_pr_corpus(), MatchSource.PR_CORPUS, repo)

        save_matches_to_file(keyword_parser.parse_prs(), MatchSource.PR, repo)
        save_matches_to_file(keyword_parser.parse_pr_comments(), MatchSource.PR_COMMENT, repo)
        save_matches_to_file(keyword_parser.parse_prs_related_issues(), MatchSource.PR_RELATED_ISSUE, repo)
        save_matches_to_file(keyword_parser.parse_pr_related_issue_comments(), MatchSource.PR_RELATED_ISSUE_COMMENT, repo)

    print("Done!")


if __name__ == "__main__":
    main()
