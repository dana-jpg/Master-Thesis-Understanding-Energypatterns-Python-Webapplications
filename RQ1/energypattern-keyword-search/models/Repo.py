import re
from dataclasses import dataclass
from typing import Optional, TypedDict


class RepoDict(TypedDict):
    author: str
    name: str
    version: str
    wiki: Optional[str]


@dataclass
class Repo:
    BASE_GITHUB_URL = "https://github.com"

    author: str
    name: str
    version: str
    wiki: Optional[str] = None

    @classmethod
    def from_dict(cls, dct: RepoDict):
        return cls(**dct)

    @property
    def git_id(self) -> str:
        return f"{self.author}/{self.name}"

    @property
    def github_source_code_url(self) -> str:
        return f"{self.BASE_GITHUB_URL}/{self.git_id}/tree/{self.version}"

    @property
    def repo_name(self) -> str:
        return f"{self.author}.{self.name}"

    @property
    def wiki_dir(self) -> str:
        return re.split(r"https?://", self.wiki)[-1]

    def has_wiki(self) -> bool:
        return self.wiki is not None

    def _get_ref(self, delimiter="/") -> str:
        return delimiter.join([self.author, self.name, self.version])

    @property
    def dotted_ref(self) -> str:
        return self._get_ref(".")

    @property
    def id(self) -> str:
        return self._get_ref()
