import os

import dotenv

from cfg.selected_repos import selected_repos
from processing_pipeline.keyword_matching.services.GithubDataFetcher import GithubDataFetcher
from processing_pipeline.keyword_matching.services.MongoDB import MongoDB

dotenv.load_dotenv()

def main():
    token = os.getenv('GITHUB_TOKEN')

    for repo in selected_repos:
        fetcher = GithubDataFetcher(token, repo)
        db = MongoDB(repo)
        print("Fetching PRs...")
        for pr in fetcher.get_prs(10):
            db.insert_prs(pr)

    print("Done!")


if __name__ == "__main__":
    main()
