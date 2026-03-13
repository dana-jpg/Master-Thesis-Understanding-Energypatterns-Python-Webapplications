from enum import Enum


class MatchSource(Enum):
    RELEASE = "release"
    WIKI = "wiki"
    DOCS = "docs"
    ISSUE = "issue"
    ISSUE_COMMENT = "issue_comment"
    PR = "pr"
    PR_CORPUS = "pr_corpus"
    PR_COMMENT = "pr_comment"
    PR_RELATED_ISSUE = "pr_related_issue"
    PR_RELATED_ISSUE_COMMENT = "pr_related_issue_comment"
    CODE_COMMENT = "code_comment"
