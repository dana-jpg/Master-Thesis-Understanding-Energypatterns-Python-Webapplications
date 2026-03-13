import dataclasses
import re
from typing import TypedDict, List

from pymongo import UpdateOne
from pymongo.synchronous.collection import Collection
from pymongo.synchronous.command_cursor import CommandCursor

from models.Repo import Repo
from processing_pipeline.keyword_matching.services.GithubDataFetcher import IssueDTO, ReleaseDTO, PullRequestDTO
from services.MongoDBConnection import MongoDBConnection


class MongoMatch(TypedDict):
    text: str
    html_url: str


class MongoDB:
    def __init__(self, repo: Repo):
        self.non_robot_users = ["olgabot", "hugtalbot", "arrogantrobot", "robot-chenwei", "Bot-Enigma-0"]
        self.regex_omitting_bots = re.compile(r"bot\b", re.IGNORECASE)
        self.repo = repo
        self.client = MongoDBConnection().get_client()

    def _issue_collection(self) -> Collection:
        return self.client['git_issues'][self.repo.repo_name]
    
    def _prs_collection(self) -> Collection:
        return self.client['git_prs'][self.repo.repo_name]

    def _releases_collection(self) -> Collection:
        return self.client['git_releases'][self.repo.repo_name]

    def insert_issues(self, documents: List[IssueDTO]):
        table = self._issue_collection()
        try:
            res = table.bulk_write(
                [UpdateOne({"_id": issue.id}, {"$set": dataclasses.asdict(issue)}, upsert=True) for issue in documents])
            print(res)
        except Exception as e:
            print(e)

    def insert_prs(self, documents: List[PullRequestDTO]):
        """
        Upsert pull requests into git_prs.<repo_name>.
        Uses the DTO's .id property (backed by _id) as the Mongo _id.
        """
        table = self._prs_collection()
        try:
            res = table.bulk_write(
                [UpdateOne({"_id": pr.id}, {"$set": dataclasses.asdict(pr)}, upsert=True) for pr in documents]
            )
            print(res)
        except Exception as e:
            print(e)

    def insert_releases(self, documents: List[ReleaseDTO]):
        table = self._releases_collection()
        try:
            res = table.bulk_write(
                [UpdateOne({"_id": release.id}, {"$set": dataclasses.asdict(release)}, upsert=True) for release in
                 documents])
            print(res)
        except Exception as e:
            print(e)

    def extract_comments(self) -> CommandCursor[MongoMatch]:
        return self._issue_collection().aggregate(
            [{"$unwind": "$comments_data"}, {"$addFields": {"text": "$comments_data.body"}}, {"$match": {
                "$or": [{"comments_data.user": {"$not": {"$regex": self.regex_omitting_bots}}},
                        {"comments_data.user": {"$in": self.non_robot_users}}]}},
             {"$project": {"text": 1, "html_url": 1, }}])

    def extract_issues(self) -> CommandCursor[MongoMatch]:
        return self._issue_collection().aggregate([{# 1. Concatenate 'title' and 'body' into a new field called 'text'
            "$addFields": {"text": {"$concat": ["$title", "; ", "$body"]}}},
            {"$match": {
                "$or": [{"author": {"$not": {"$regex": self.regex_omitting_bots}}},
                        {"author": {"$in": self.non_robot_users}}]}},
            {"$project": {"text": 1, "html_url": 1, }}])

    def extract_releases(self) -> CommandCursor[MongoMatch]:
        return self._releases_collection().aggregate(
            [{"$addFields": {"text": {"$trim": {"input": "$body"}}}}, {"$project": {"text": 1, "html_url": 1}}])


    def extract_prs(self) -> CommandCursor[MongoMatch]:
        """
        Return PRs as (text, html_url) where text := title + '; ' + body,
        excluding obvious bot authors (by 'author' or 'user' fields) unless whitelisted.
        """
        return self._prs_collection().aggregate([
            {
                # Concatenate 'title' and 'body' into a new field called 'text'
                "$addFields": {"text": {"$concat": ["$title", "; ", {"$ifNull": ["$body", ""]}]}}
            },
            {
                "$match": {
                    "$or": [
                        {"author": {"$not": {"$regex": self.regex_omitting_bots}}},
                        {"author": {"$in": self.non_robot_users}},
                        {"user":   {"$not": {"$regex": self.regex_omitting_bots}}},
                        {"user":   {"$in": self.non_robot_users}},
                    ]
                }
            },
            {"$project": {"text": 1, "html_url": 1}}
        ])

    def extract_pr_comments(self) -> CommandCursor[MongoMatch]:
        """
        If PR documents embed comment data similarly to issues in 'comments_data',
        this mirrors extract_comments() but runs on the PR collection.
        Each emitted doc has: text := comments_data.body, html_url := parent PR html_url.
        """
        return self._prs_collection().aggregate([
            {"$unwind": "$comments_data"},
            {"$addFields": {"text": "$comments_data.body"}},
            {
                "$match": {
                    "$or": [
                        {"comments_data.user": {"$not": {"$regex": self.regex_omitting_bots}}},
                        {"comments_data.user": {"$in": self.non_robot_users}},
                    ]
                }
            },
            {"$project": {"text": 1, "html_url": 1}}
        ])



    def extract_pr_related_issues(self) -> CommandCursor[MongoMatch]:
        """
        Return PR-embedded issues as (text, html_url) where
        text := issues.title + '; ' + issues.body,
        excluding obvious bot authors unless whitelisted.
        """
        return self._prs_collection().aggregate([
            {"$unwind": "$issues"},
            {
                "$addFields": {
                    "text": {
                        "$concat": [
                            "$issues.title", "; ",
                            {"$ifNull": ["$issues.body", ""]}
                        ]
                    }
                }
            },
            {
                "$match": {
                    "$or": [
                        {"issues.author": {"$not": {"$regex": self.regex_omitting_bots}}},
                        {"issues.author": {"$in": self.non_robot_users}}
                    ]
                }
            },
            {"$project": {"text": 1, "html_url": "$issues.html_url"}}
        ])

    def extract_pr_related_issue_comments(self) -> CommandCursor[MongoMatch]:
        """
        Return comments on PR-embedded issues as (text, html_url) where
        text := issues.comments_data.body,
        html_url := parent issue link (issues.html_url),
        excluding obvious bot commenters unless whitelisted.
        """
        return self._prs_collection().aggregate([
            {"$unwind": "$issues"},
            {"$unwind": "$issues.comments_data"},
            {"$addFields": {"text": "$issues.comments_data.body"}},
            {
                "$match": {
                    "$or": [
                        {"issues.comments_data.user": {"$not": {"$regex": self.regex_omitting_bots}}},
                        {"issues.comments_data.user": {"$in": self.non_robot_users}}
                    ]
                }
            },
            {"$project": {"text": 1, "html_url": "$issues.html_url"}}
        ])
    

    def extract_pr_corpus(self) -> CommandCursor[dict]:
        """
        One row per PR with a unified 'text' corpus that includes:
          - PR title + body
          - PR comments (filtered)
          - Related issue titles + bodies (filtered)
          - Related issue comments (filtered)
        """
        return self._prs_collection().aggregate([
            # Build base snippets from PR itself
            {
                "$addFields": {
                    "pr_text": {
                        "$concat": [
                            {"$ifNull": ["$title", ""]}, "; ",
                            {"$ifNull": ["$body", ""]}
                        ]
                    },
    
                    # PR comments (filtered for non-bots or whitelisted)
                    "pr_comment_bodies": {
                        "$map": {
                            "input": {
                                "$filter": {
                                    "input": {"$ifNull": ["$comments_data", []]},
                                    "as": "c",
                                    "cond": {
                                        "$or": [
                                            {"$not": [{
                                                "$regexMatch": {
                                                    "input": "$$c.user",
                                                    "regex": self.regex_omitting_bots
                                                }
                                            }]},
                                            {"$in": ["$$c.user", self.non_robot_users]}
                                        ]
                                    }
                                }
                            },
                            "as": "c",
                            "in": {"$ifNull": ["$$c.body", ""]}
                        }
                    },
    
                    # Related issues (filtered)
                    "issue_texts": {
                        "$map": {
                            "input": {
                                "$filter": {
                                    "input": {"$ifNull": ["$issues", []]},
                                    "as": "i",
                                    "cond": {
                                        "$or": [
                                            {"$not": [{
                                                "$regexMatch": {
                                                    "input": "$$i.author",
                                                    "regex": self.regex_omitting_bots
                                                }
                                            }]},
                                            {"$in": ["$$i.author", self.non_robot_users]}
                                        ]
                                    }
                                }
                            },
                            "as": "i",
                            "in": {
                                "$concat": [
                                    {"$ifNull": ["$$i.title", ""]}, "; ",
                                    {"$ifNull": ["$$i.body", ""]}
                                ]
                            }
                        }
                    },
    
                    # Related issue comments (filtered, flattened)
                    "issue_comment_bodies": {
                        "$let": {
                            "vars": {
                                "issueCommentsArrays": {
                                    "$map": {
                                        "input": {"$ifNull": ["$issues", []]},
                                        "as": "i",
                                        "in": {
                                            "$map": {
                                                "input": {
                                                    "$filter": {
                                                        "input": {"$ifNull": ["$$i.comments_data", []]},
                                                        "as": "ic",
                                                        "cond": {
                                                            "$or": [
                                                                {"$not": [{
                                                                    "$regexMatch": {
                                                                        "input": "$$ic.user",
                                                                        "regex": self.regex_omitting_bots
                                                                    }
                                                                }]},
                                                                {"$in": ["$$ic.user", self.non_robot_users]}
                                                            ]
                                                        }
                                                    }
                                                },
                                                "as": "ic",
                                                "in": {"$ifNull": ["$$ic.body", ""]}
                                            }
                                        }
                                    }
                                }
                            },
                            "in": {
                                "$reduce": {
                                    "input": "$$issueCommentsArrays",
                                    "initialValue": [],
                                    "in": {"$concatArrays": ["$$value", "$$this"]}
                                }
                            }
                        }
                    }
                }
            },
    
            # Merge all text pieces into a single array
            {
                "$addFields": {
                    "texts": {
                        "$concatArrays": [
                            [{"$ifNull": ["$pr_text", ""]}],
                            {"$ifNull": ["$pr_comment_bodies", []]},
                            {"$ifNull": ["$issue_texts", []]},
                            {"$ifNull": ["$issue_comment_bodies", []]}
                        ]
                    }
                }
            },
    
            # Join into one big string separated by newlines (no duplicates emitted upstream)
            {
                "$addFields": {
                    "text": {
                        "$reduce": {
                            "input": "$texts",
                            "initialValue": "",
                            "in": {
                                "$concat": [
                                    "$$value",
                                    {"$cond": [{"$eq": ["$$value", ""]}, "", "\n"]},
                                    "$$this"
                                ]
                            }
                        }
                    }
                }
            },
    
            # Final shape: one row per PR
            {"$project": {"text": 1, "html_url": 1}}
        ])
    