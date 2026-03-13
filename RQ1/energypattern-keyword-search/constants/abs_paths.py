import os
from pathlib import Path

from constants.foldernames import FolderNames

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class AbsDirPath:
    """
    Defines absolute file system paths for key directories within the project.
    All paths are constructed relative to the dynamically determined PROJECT_ROOT.
    """
    # DIRS

    ROOT = PROJECT_ROOT

    DATA = PROJECT_ROOT / "data"
    DOCS = PROJECT_ROOT / "docs"
    CONFIG = PROJECT_ROOT / "cfg"
    CONSTANTS = PROJECT_ROOT / "constants"
    RESOURCES = PROJECT_ROOT / "resources"
    STAGES = PROJECT_ROOT / "stages"

    TEMP = PROJECT_ROOT / ".tmp"
    CACHE = PROJECT_ROOT / ".cache"
    LOGS = PROJECT_ROOT / ".logs"

    # SUB DIRS
    QUERIES = RESOURCES / "queries"
    ANALYSIS = STAGES / "analysis"
    # KEYWORDS = DATA / "keywords"
    KEYWORDS = DATA / "keywords_2"
    TACTICS = CONFIG / "tactics"
    SAMPLES = DATA / "samples"
    SAMPLES_VERIFIED = SAMPLES / "verified"
 

    WIKIS = TEMP / "docs"
    SOURCE_CODE = TEMP / "source"

    # ANALYSIS DIRS
    REPO_TOPICS = ANALYSIS / "repo_topics"
    REPOS = ANALYSIS / "repos"
    KEYWORD_ANALYSIS = ANALYSIS / "keywords"

    # KEYWORD DIRS
    SECOND_KEYWORDS_MATCHING = KEYWORDS / FolderNames.SECOND_MATCHING
    PR_KEYWORDS_MATCHING = KEYWORDS / FolderNames.PR_MATCHING
    SMALL_REPOS_KEYWORDS_MATCHING = KEYWORDS / FolderNames.SMALL_REPOS
    FRAPPE_WEBLATE_KEYWORDS_MATCHING = KEYWORDS / FolderNames.FRAPPE_WEBLATE_MATCHING
    OPENDX_KEYWORDS_MATCHING = KEYWORDS / FolderNames.OPENDX_MATCHING


    