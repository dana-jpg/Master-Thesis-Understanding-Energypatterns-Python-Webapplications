import os
import shelve
import time
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Dict, Optional, Set, cast, TypeGuard, List, Iterator, Literal

from github import Github
from github.Issue import Issue
from github.IssueComment import IssueComment
from github.PullRequest import PullRequest
from github import RateLimitExceededException
from tqdm import tqdm

from constants.abs_paths import AbsDirPath
from models.Repo import Repo

import random
from github.GithubException import GithubException


InternalReactionKey = Literal[
    "thumbs_up", "thumbs_down", "laugh", "confused", 
    "heart", "hooray", "rocket", "eyes"
]
ReactionKey = Literal[InternalReactionKey, "+1", "-1"]

@dataclass
class ReactionDTO:
    thumbs_up: int = 0
    thumbs_down: int = 0
    laugh: int = 0
    confused: int = 0
    heart: int = 0
    hooray: int = 0
    rocket: int = 0
    eyes: int = 0

    _name_map: ClassVar[Dict[ReactionKey, InternalReactionKey]] = {'+1': 'thumbs_up', '-1': 'thumbs_down', }

    def _get_key(self, key: ReactionKey) -> InternalReactionKey:
        return self._name_map.get(key, cast(InternalReactionKey, key))

    @classmethod
    def is_reaction_key(cls, key: str) -> TypeGuard[ReactionKey]:
        return key in [*cls.__dict__.keys(), "+1", "-1"]

    def add(self, reaction: str):
        if self.is_reaction_key(reaction):
            key = self._get_key(reaction)
            self.__setattr__(key, self.__getattribute__(key) + 1)


@dataclass
class CommentDTO:
    issue_id: int
    _id: int
    html_url: str
    body: str
    user: str | None
    created_at: datetime
    updated_at: datetime
    reactions: ReactionDTO


@dataclass
class IssueDTO:
    _id: int
    html_url: str
    number: int
    pull_request_html_url: str | None
    title: str
    body: str
    state: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime
    labels: List[str]
    author: str | None
    assignees: List[str]
    milestone: str | None
    comments_count: int
    comments_data: List[CommentDTO]
    reactions: ReactionDTO

    @property
    def id(self):
        return self._id

@dataclass
class PullRequestDTO:
    _id: int
    html_url: str
    number: int
    title: str
    body: str
    state: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime
    labels: List[str]
    comments_data: List[CommentDTO]
    issues: List[IssueDTO]

    @property
    def id(self):
        return self._id

@dataclass
class ReleaseDTO:
    _id: int
    html_url: str
    tag_name: str
    title: str
    name: str
    body: str
    created_at: datetime
    published_at: datetime
    draft: bool
    prerelease: bool
    author: str | None
    asset_count: int

    @property
    def id(self):
        return self._id




class GithubDataFetcher:
    def __init__(self, token: str, repo: Repo):
        """
        Initialize the fetcher with GitHub token

        Args:
            token (str): GitHub Personal Access Token
        """
        self.github = Github(token, per_page=100, retry=3, timeout=30)
        self.repo = repo
    
    def _respect_rate_limit(self, min_remaining: int = 100) -> None:
        """
        Sleep until reset if our cached remaining tokens drop below min_remaining.
        Uses header-derived attributes that do NOT trigger an extra API call.
        """
        try:
            remaining, _ = self.github.rate_limiting  
            reset_ts = self.github.rate_limiting_resettime  

            if remaining is not None and reset_ts is not None and remaining < min_remaining:
                sleep_for = max(int(reset_ts - time.time()) + 1, 1)
                time.sleep(sleep_for)
        except Exception:
            pass

    
    def _sleep_backoff(self, attempt: int, base: float = 1.5, max_sleep: float = 30.0):
        # Exponential backoff with jitter
        delay = min(max_sleep, (base ** attempt) + random.random())
        time.sleep(delay)
    
    def _with_retry(self, fn, *, max_retries: int = 6):
        """
        Retry wrapper for transient GitHub/server/network errors.
        Returns fn() or raises after exhausting retries.
        """
        _TRANSIENT_STATUSES = {500, 502, 503, 504}

        for attempt in range(max_retries + 1):
            try:
                return fn()
            except GithubException as ge:
                status = getattr(ge, "status", None)
                # Respect rate-limit if present, otherwise retry on transient 5xx
                if status == 403 and "rate limit" in str(ge).lower():
                    self._respect_rate_limit(min_remaining=1)
                    continue
                if status in _TRANSIENT_STATUSES:
                    if attempt == max_retries:
                        raise
                    self._sleep_backoff(attempt)
                    continue
                # Non-transient -> re-raise
                raise
            except (OSError, TimeoutError) as e:
                # Network flake
                if attempt == max_retries:
                    raise
                self._sleep_backoff(attempt)
                continue


    def _iter_paginated_resilient(self, paginated_list):
        for item in paginated_list:
            for attempt in range(6):
                try:
                    yield item
                    break
                except RateLimitExceededException:
                    self._respect_rate_limit(min_remaining=1)
                except GithubException as ge:
                    if ge.status in (500, 502, 503, 504):
                        self._sleep_backoff(attempt)
                        continue
                    raise



    def get_issues(self, batch_size: int = 10) -> Iterator[List[IssueDTO]]:
        assert batch_size > 0, "Batch size must be greater than 0"
        repo = self.github.get_repo(self.repo.git_id)

        issue_cache_dir = AbsDirPath.CACHE / "issues"
        os.makedirs(issue_cache_dir, exist_ok=True)
        with shelve.open(issue_cache_dir / self.repo.repo_name) as db:
            since = db.get("since", None)
            # Get all issues (including pull requests)
            issues = repo.get_issues(state='all', direction='asc', since=since) if since else repo.get_issues(
                state='all', direction='asc')
            total_count = issues.totalCount

            batch = []
            for issue in tqdm(issues, total=total_count, desc="Fetching issues"):
                try:
                    batch.append(self._map_issue_to_dto(issue))

                    if len(batch) == batch_size:
                        yield batch
                        db["since"] = issue.created_at
                        batch.clear()

                    self._respect_rate_limit(min_remaining=100)

                except RateLimitExceededException as rle:
                    # Fallback safety: if we still hit the limit, sleep until reset and continue
                    # PyGithub raises this with headers already parsed; the global attributes are set.
                    self._respect_rate_limit(min_remaining=1)
                    continue
                except Exception as e:
                    print(f"Error processing issue #{getattr(issue, 'number', '?')}: {str(e)}")
                    continue

            if len(batch) > 0:
                yield batch

    from tqdm import tqdm

    def get_prs(
        self,
        batch_size: int = 10,
        known_pr_numbers: Optional[Set[int]] = None,   
    ) -> Iterator[List[PullRequestDTO]]:
        assert batch_size > 0, "Batch size must be greater than 0"
        known_pr_numbers = known_pr_numbers or set()
    
        repo = self.github.get_repo(self.repo.git_id)
    
        prs_cache_dir = AbsDirPath.CACHE / "prs"
        os.makedirs(prs_cache_dir, exist_ok=True)
    
        with shelve.open(prs_cache_dir / self.repo.repo_name) as db:
            boundary_ts: Optional[datetime] = db.get("boundary_ts")  
            boundary_num: Optional[int] = db.get("boundary_num")     
    
            # NOTE: Issues API supports 'since' (by updated_at)
            issues_pl = (
                repo.get_issues(state="all", direction="asc", since=boundary_ts)
                if boundary_ts else
                repo.get_issues(state="all", direction="asc")
            )
    
            # tqdm will show *processed PRs* (not raw items) so total is unknown
            batch: List[PullRequestDTO] = []
            max_ts, max_num = boundary_ts, boundary_num or 0
            seen_numbers: Set[int] = db.get("seen_numbers", set())
    
            with tqdm(desc="Fetching Pull Requests", unit="pr") as pbar:
                for it in self._iter_paginated_resilient(issues_pl):
                    try:
                        # keep only PRs (Issues API returns both)
                        if not getattr(it, "pull_request", None):
                            continue
    
                        num = it.number
    
                        # skip already-known (DB) or seen in previous runs
                        if num in known_pr_numbers or num in seen_numbers:
                            continue
    
                        # guard against inclusive boundary (same updated_at)
                        if boundary_ts and it.updated_at == boundary_ts and num <= (boundary_num or 0):
                            continue
    
                        # fetch PR object for PR-specific fields/comments/etc.
                        pr = self._with_retry(lambda: repo.get_pull(num))
    
                        batch.append(self._map_pr_to_dto(pr))
                        seen_numbers.add(num)
                        pbar.update(1)
                        pbar.set_postfix_str(f"last=#{num}")
    
                        # advance boundary
                        if (max_ts is None) or (it.updated_at, num) > (max_ts, max_num):
                            max_ts, max_num = it.updated_at, num
    
                        if len(batch) == batch_size:
                            yield batch
                            # persist progress
                            db["boundary_ts"] = max_ts
                            db["boundary_num"] = max_num
                            db["seen_numbers"] = seen_numbers
                            batch.clear()
    
                        self._respect_rate_limit(min_remaining=100)
    
                    except RateLimitExceededException:
                        self._respect_rate_limit(min_remaining=1)
                        continue
                    except GithubException as ge:
                        # Non-fatal: log and keep going
                        print(f"[WARN] GitHub error on PR #{getattr(it, 'number', '?')}: {ge}")
                        continue
                    except Exception as e:
                        print(f"[WARN] Error processing PR #{getattr(it, 'number', '?')}: {e}")
                        continue
    
            # flush remainder
            if batch:
                yield batch
                db["boundary_ts"] = max_ts
                db["boundary_num"] = max_num
                db["seen_numbers"] = seen_numbers
    
    

    def _map_issue_to_dto(self, issue: Issue) -> IssueDTO:
        # Get comments with their reactions
        comments_data = self._get_comments(issue)
        issue_data = IssueDTO(_id=issue.id, html_url=issue.html_url, number=issue.number,
                              pull_request_html_url=issue.pull_request.html_url if issue.pull_request else None,
                              title=issue.title, body=issue.body, state=issue.state, created_at=issue.created_at,
                              updated_at=issue.updated_at, closed_at=issue.closed_at,
                              labels=[label.name for label in issue.labels],
                              author=issue.user.login if issue.user else None,
                              assignees=[assignee.login for assignee in issue.assignees],
                              milestone=issue.milestone.title if issue.milestone else None,
                              comments_count=issue.comments, comments_data=comments_data, reactions=None)
        return issue_data
    
    def _map_pr_to_dto(self, pull_request: PullRequest) -> PullRequestDTO:
        comments_data = self._get_pr_comments(pull_request)
        related_issues = self._get_pr_related_issues(pull_request)
        pr_data = PullRequestDTO(_id=pull_request.id, html_url=pull_request.html_url, number=pull_request.number,
                              title=pull_request.title, body=pull_request.body, state=pull_request.state, created_at=pull_request.created_at,
                              updated_at=pull_request.updated_at, closed_at=pull_request.closed_at,
                              labels=[label.name for label in pull_request.labels],
                              comments_data=comments_data, issues=related_issues)
        return pr_data

    def _graphql(self, query: str, variables: dict) -> dict:
        _headers, payload = self.github._Github__requester.graphql_query(
            query=query,
            variables=variables
        )
        # Normalize shape to return only the "data" object
        if isinstance(payload, dict):
            if "errors" in payload and payload["errors"]:
                # surface the first error (you can log the whole list)
                raise RuntimeError(f"GraphQL error: {payload['errors'][0]}")
            if "data" in payload and isinstance(payload["data"], dict):
                return payload["data"]
        # Fallback: return as-is (defensive)
        return payload

    
    def _get_pr_related_issues(self, pull_request: PullRequest) -> List[IssueDTO]:
        repo = self.github.get_repo(self.repo.git_id)
        owner, name = repo.full_name.split("/", 1)
        pr_number = pull_request.number
    
        issue_numbers: set[int] = set()
    
        # A) Issues this PR closes (via closing keywords / commits)
        cursor = None
        while True:
            query = """
            query($owner:String!, $name:String!, $number:Int!, $first:Int!, $after:String) {
              repository(owner:$owner, name:$name) {
                pullRequest(number:$number) {
                  closingIssuesReferences(first:$first, after:$after) {
                    nodes { number }
                    pageInfo { hasNextPage endCursor }
                  }
                }
              }
            }"""
            data = self._graphql(query, {
                "owner": owner, "name": name, "number": pr_number,
                "first": 50, "after": cursor
            })
            refs = data["repository"]["pullRequest"]["closingIssuesReferences"]
            for n in refs["nodes"]:
                issue_numbers.add(int(n["number"]))
            if not refs["pageInfo"]["hasNextPage"]:
                break
            cursor = refs["pageInfo"]["endCursor"]
    
        # B) Issues that cross-reference (mention) this PR
        cursor = None
        while True:
            query = """
            query($owner:String!, $name:String!, $number:Int!, $first:Int!, $after:String) {
              repository(owner:$owner, name:$name) {
                pullRequest(number:$number) {
                  timelineItems(itemTypes: CROSS_REFERENCED_EVENT, first:$first, after:$after) {
                    nodes {
                      ... on CrossReferencedEvent {
                        source { __typename ... on Issue { number } }
                      }
                    }
                    pageInfo { hasNextPage endCursor }
                  }
                }
              }
            }"""
            data = self._graphql(query, {
                "owner": owner, "name": name, "number": pr_number,
                "first": 100, "after": cursor
            })
            items = data["repository"]["pullRequest"]["timelineItems"]
            for node in items["nodes"]:
                src = node.get("source") or {}
                if src.get("__typename") == "Issue" and "number" in src:
                    issue_numbers.add(int(src["number"]))
            if not items["pageInfo"]["hasNextPage"]:
                break
            cursor = items["pageInfo"]["endCursor"]
    
        # Fetch & map full issue objects via REST (reuses your DTO mapper)
        issues_dto: list[IssueDTO] = []
        for num in sorted(issue_numbers):
            try:
                gh_issue = repo.get_issue(number=num)
                issues_dto.append(self._map_issue_to_dto(gh_issue))
                self._respect_rate_limit(min_remaining=100)
            except RateLimitExceededException:
                self._respect_rate_limit(min_remaining=1)
            except Exception as e:
                print(f"Error fetching Issue #{num} linked to PR #{pr_number}: {e}")
        return issues_dto
    

    def _get_comments(self, issue: Issue) -> List[CommentDTO]:
        """Fetch all comments for an issue with their reactions"""
        comments_data = []

        for comment in issue.get_comments():
            try:
                reactions = self._get_reactions(comment)

                comment_data = CommentDTO(_id=comment.id, issue_id=issue.id, html_url=comment.html_url,
                                          body=comment.body, user=comment.user.login if comment.user else None,
                                          created_at=comment.created_at, updated_at=comment.updated_at,
                                          reactions=reactions)
                comments_data.append(comment_data)

            except Exception as e:
                print(f"Error processing comment {comment.id}: {str(e)}")
                continue

        return comments_data

    def _get_pr_comments(self, pr: PullRequest) -> List[CommentDTO]:
        """Fetch all comments for an issue with their reactions"""
        comments_data = []

        for comment in pr.get_issue_comments():
            try:

                comment_data = CommentDTO(_id=comment.id, issue_id=pr.id, html_url=comment.html_url,
                                          body=comment.body, user=comment.user.login if comment.user else None,
                                          created_at=comment.created_at, updated_at=comment.updated_at,
                                          reactions=None)
                comments_data.append(comment_data)

            except Exception as e:
                print(f"Error processing comment {comment.id}: {str(e)}")
                continue

        return comments_data

    def _get_reactions(self, item: Issue | IssueComment) -> ReactionDTO:
        """Get reaction counts for an issue or comment"""
        reaction_counts = ReactionDTO()

        try:
            reactions = item.get_reactions()
            for reaction in reactions:
                reaction_counts.add(reaction.content)
        except Exception as e:
            print(f"Error getting reactions: {str(e)}")

        return reaction_counts

    def get_releases(self, batch_size=10) -> Iterator[List[ReleaseDTO]]:
        assert batch_size > 0, "Batch size must be greater than 0"

        repo = self.github.get_repo(self.repo.git_id)

        releases = repo.get_releases()
        total_releases = releases.totalCount

        batch = []
        for release in tqdm(releases, total=total_releases, desc="Fetching releases"):
            try:
                release_data = ReleaseDTO(_id=release.id, html_url=release.html_url, title=release.title,
                                          tag_name=release.tag_name, name=release.title, body=release.body,
                                          created_at=release.created_at, published_at=release.published_at,
                                          draft=release.draft, prerelease=release.prerelease,
                                          author=release.author.login if release.author else None,
                                          asset_count=release.get_assets().totalCount)
                batch.append(release_data)
                if len(batch) == batch_size:
                    yield batch
                    batch.clear()

            except Exception as e:
                print(f"Error processing release {release.title}: {str(e)}")
                continue

        if len(batch) > 0:
            yield batch
