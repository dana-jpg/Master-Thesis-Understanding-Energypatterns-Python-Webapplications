import os
import re
from abc import ABC
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Generator

from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

from cfg.patterns import transform_keywords
from models.Repo import Repo
from processing_pipeline.keyword_matching.model.MatchSource import MatchSource
from processing_pipeline.keyword_matching.services.DatasetCounter import DatasetCounter
from processing_pipeline.keyword_matching.services.MongoDB import MongoDB
from services.ast_extractor import ext_to_lang, code_comments_iterator

AttributeDictType = Dict[str, List[str]]


@dataclass
class TextMatch:
    keyword: str
    keyword_raw: str
    matched_word: str
    match_idx: int
    sentence: str
    category: str
    text: Optional[str] = field(kw_only=True, default=None)


@dataclass
class FullMatch(TextMatch):
    repo: Repo
    source: MatchSource
    url: str

    @classmethod
    def from_text_match(cls, text_match: TextMatch, repo: Repo, source: MatchSource, url: str):
        # noinspection PyTypeChecker
        return cls(**asdict(text_match), repo=repo, source=source, url=url)

    def as_dict(self, keep_text = False) -> dict:
        # noinspection PyTypeChecker
        result = {k: v for k, v in asdict(self).items()}
        result["source"] = self.source.value
        del result["repo"]
        result["repo_id"] = self.repo.id
        if not keep_text:
            del result["text"]
        return result


class KeywordExtractor(ABC):
    context_length = 2000

    def __init__(self, QAs: AttributeDictType, repo: Repo, *, append_full_text: bool = False):
        self.QAs_non_regex = transform_keywords(QAs, keep_regex_notation=False)
        self.repo = repo
        self.append_full_text = append_full_text
        self.category_patterns = {category: SourceCodeKeywordExtractor.get_keyword_matching_pattern(keywords) for category, keywords in QAs.items()}
        self.QAs = QAs

    def _extract_match_details(self, match, quality_attr, text):
        full_match, match_idx = match.group(), match.start()
        keyword_idx = match.lastindex - 1
        keyword = self.QAs_non_regex[quality_attr][keyword_idx]
        keyword_raw = self.QAs[quality_attr][keyword_idx]
        context = SourceCodeKeywordExtractor.get_match_context(text, match.start(), match.end())
        text_match = TextMatch(category=quality_attr, keyword=keyword, keyword_raw=keyword_raw,
                               matched_word=full_match, match_idx=match_idx, sentence=context)
        if self.append_full_text:
            text_match.text = text
        return text_match

    def matched_keyword_iterator(self, text: str) -> Generator[TextMatch, None, None]:
        if not text:
            return
        text = SourceCodeKeywordExtractor._clean_text(text)
        for quality_attr, keywords in self.QAs.items():
            pattern = self.category_patterns[quality_attr]
            for match in re.finditer(pattern, text):
                yield self._extract_match_details(match, quality_attr, text)

    @staticmethod
    def _clean_text(text: str):
        text = re.sub(r'([.!?])?(?:\r?\n)+', lambda m: f"{m.group(1)} " if m.group(1) else ". ", text)
        text = re.sub(r'[ \n]{2,}', " ", text)
        return text.strip()

    @staticmethod
    def get_keyword_matching_pattern(keywords):
        """Expect list of sorted keywords, to be able to identify related keyword based on match group"""
        end_pattern = r'[a-z-]*\b'
        separator = rf"{end_pattern} \b"
        keywords_with_correct_delimiters = [separator.join(k.split(" ")) if " " in k else k for k in keywords]
        keywords_wrapped_in_groups = [f"({k})" for k in keywords_with_correct_delimiters]
        # noinspection RegExpUnnecessaryNonCapturingGroup
        return re.compile(rf'\b(?:{"|".join(keywords_wrapped_in_groups)}){end_pattern}', re.IGNORECASE)

    @staticmethod
    def _strip_html_tags(html_content: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text()

    @staticmethod
    def generate_link(base_url: str, page: str = "") -> str:
        full_url = f"{base_url}/{page}" if page else base_url
        return full_url

    @staticmethod
    def get_match_context(text: str, match_start: int, match_end: int) -> str:
        """ Returns a context string of length `KeywordParser.context_length` centered around the match. """
        if len(text) < SourceCodeKeywordExtractor.context_length:
            return text

        match_len = match_end - match_start
        remaining = SourceCodeKeywordExtractor.context_length - match_len
        remaining_left = remaining // 2
        remaining_right = remaining - remaining_left

        context_end = match_end + remaining_right
        if context_end > len(text): return text[-SourceCodeKeywordExtractor.context_length:]

        context_start = match_start - remaining_left
        if context_start < 0: return text[:SourceCodeKeywordExtractor.context_length]
        return text[context_start: context_end]


class SourceCodeKeywordExtractor(KeywordExtractor):
    """
    Extracting keywords from repository docs, code comments and wiki pages.
    Collections were fetched earlier with `GithubDataFetcher`, `services/ast_extractor.py` (tree-sitter based scripts)
    and external tool `WinHTTrack` (repo wiki pages).
    """
    def __init__(self, QAs: AttributeDictType, repo: Repo, *, append_full_text: bool = False, dataset_counter: DatasetCounter):
        super().__init__(QAs, repo, append_full_text=append_full_text)
        self.dataset_counter = dataset_counter

    def parse_wiki(self, wiki_path: str) -> List[FullMatch]:
        matches = []
        files = Path(wiki_path).glob("**/*.html")
        for file in tqdm(files, desc=f"Parsing wiki {wiki_path}"):
            abs_path = file
            rel_path = os.path.normpath(os.path.relpath(abs_path, start=wiki_path)).replace("\\", "/")
            link = self.generate_link(self.repo.wiki, rel_path)
            try:
                documentation_raw = open(abs_path, "r", encoding="utf-8", errors="replace").read()
                text_content = self._strip_html_tags(documentation_raw)
                matches.extend([FullMatch.from_text_match(match, source=MatchSource.WIKI, repo=self.repo, url=link) for match in
                                self.matched_keyword_iterator(text_content)])
                self.dataset_counter.add(self.repo, MatchSource.WIKI)
            except Exception as error:
                logger.error(f"Parse docs failed for {self.repo.id}, {file=}: {error=}")
        return matches

    def parse_docs(self, docs_path: str) -> List[FullMatch]:
        matches = []
        docs_extensions = [".md", ".rst", ".txt", ".adoc", ".html"]
        for ext in docs_extensions:
            files = Path(docs_path).glob(f"**/*{ext}")
            for file in tqdm(files, desc="Parsing docs"):
                tqdm.write(str(file))
                abs_path = file
                rel_path = os.path.normpath(os.path.relpath(abs_path, start=docs_path)).replace("\\", "/")
                link = self.generate_link(self.repo.github_source_code_url, rel_path)
                try:
                    documentation_raw = open(abs_path, "r", encoding="utf-8", errors="replace").read()
                    text_content = self._strip_html_tags(documentation_raw) if ext in ".html" else documentation_raw
                    matches.extend([FullMatch.from_text_match(match, source=MatchSource.DOCS, repo=self.repo, url=link) for match in
                                    self.matched_keyword_iterator(text_content)])
                    self.dataset_counter.add(self.repo, MatchSource.DOCS)
                except Exception as error:
                    logger.error(f"Parse docs failed for {self.repo.id}, {file=}: {error=}")

        return matches

    def parse_comments(self, source_code_path: str) -> List[FullMatch]:
        matches = []
        print(f"Parsing code comments in {source_code_path}")
        for root, dirs, files in tqdm(os.walk(source_code_path), desc="Parsing code comments"):
            tqdm.write(str(root))
            for file in files:
                supported_language_extensions = ext_to_lang.keys()
                if Path(file).suffix[1:].lower() in supported_language_extensions:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.normpath(os.path.relpath(abs_path, source_code_path)).replace("\\", "/")
                    link = self.generate_link(self.repo.github_source_code_url, rel_path)
                    try:
                        for text_content in code_comments_iterator(abs_path):
                            matches.extend(
                                [FullMatch.from_text_match(match, source=MatchSource.CODE_COMMENT, repo=self.repo, url=link) for match
                                 in self.matched_keyword_iterator(text_content)])
                            self.dataset_counter.add(self.repo, MatchSource.CODE_COMMENT)
                    except Exception as error:
                        logger.error(
                            f"Parse code comments failed for {self.repo.id}, {file=}, {rel_path=}: {error=}")
        return matches

class RepoDataKeywordExtractor(KeywordExtractor):
    """
    Extracting keywords directly from MongoDB.
    Collections were fetched earlier from github (issues, issue comments, releases) with `GithubDataFetcher`.
    """
    def __init__(self, QAs: AttributeDictType, repo: Repo, *, append_full_text: bool = False, db: MongoDB):
        super().__init__(QAs, repo, append_full_text=append_full_text)
        self.db = db
        self.source_to_generator_map = {MatchSource.ISSUE_COMMENT: db.extract_comments,
                                        MatchSource.ISSUE: db.extract_issues,
                                        MatchSource.RELEASE: db.extract_releases,
                                        MatchSource.PR: db.extract_prs,
                                        MatchSource.PR_COMMENT: db.extract_pr_comments,
                                        MatchSource.PR_RELATED_ISSUE: db.extract_pr_related_issues,
                                        MatchSource.PR_RELATED_ISSUE_COMMENT: db.extract_pr_related_issue_comments,
                                        MatchSource.PR_CORPUS: db.extract_pr_corpus
                                        }

    def _parse_source(self, source) -> List[FullMatch]:
        matches = []
        generator = self.source_to_generator_map[source]
        for match in tqdm(generator(), desc=f"Processing {self.repo.dotted_ref} / {source.value}"):
            matches.extend(
                [FullMatch.from_text_match(text_match, source=source, repo=self.repo, url=match["html_url"]) for
                 text_match in
                 self.matched_keyword_iterator(match["text"])])
        return matches

    def parse_issues(self):
        return self._parse_source(MatchSource.ISSUE)

    def parse_issue_comments(self):
        return self._parse_source(MatchSource.ISSUE_COMMENT)

    def parse_prs(self):
        return self._parse_source(MatchSource.PR)
    
    def parse_pr_corpus(self):
        return self._parse_source(MatchSource.PR_CORPUS)
    
    def parse_pr_comments(self):
        return self._parse_source(MatchSource.PR_COMMENT)
    
    def parse_prs_related_issues(self):
        return self._parse_source(MatchSource.PR_RELATED_ISSUE)
    
    def parse_pr_related_issue_comments(self):
        return self._parse_source(MatchSource.PR_RELATED_ISSUE_COMMENT)
    
    def parse_releases(self):
        return self._parse_source(MatchSource.RELEASE)

