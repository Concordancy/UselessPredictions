"""Common shapes for platform connectors.

A connector turns what the user typed (URL / handle) into a channel, lists that channel's sources
and fetches their text. Adding a platform = adding one module with a Connector subclass and
registering it in Connectors/__init__.py.
"""
import html
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser

import requests

# Fixed lookup IDs (see Database/Seed.sql).
PlatformYouTube, PlatformX, PlatformSubstack = 1, 2, 3
SourceTypeVideo, SourceTypeShort, SourceTypeLivestream, SourceTypePodcast = 1, 2, 3, 4
SourceTypeArticle, SourceTypeNewsletter, SourceTypePost, SourceTypeThread, SourceTypeReply = 5, 6, 7, 8, 9
ContentTypeBody, ContentTypeDescription = 301, 302
ContentTypeTranscriptPublisher, ContentTypeTranscriptAuto = 303, 304

UserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36'


class ConnectorError(Exception):
    """A problem the user can act on (bad input, key refused, quota). The message is shown as-is."""


@dataclass
class ChannelInfo:
    Platform: int
    Key: str                    # the platform's immutable ID
    Label: str
    Handle: str = ''
    URL: str = ''
    Description: str = ''
    FollowerCount: int = 0
    SourceCount: int = 0
    DateStart: datetime | None = None
    PersonLabel: str = ''       # the platform's idea of who is behind it, as a suggestion
    Extra: dict = field(default_factory=dict)   # connector-private values (base URL, playlist ids ...)


@dataclass
class ContentItem:
    Type: int                   # Types (class SourceContent)
    Text: str
    Language: str = ''
    Origin: str = ''
    Data: str = ''              # original with timings (JSON), when there is one


@dataclass
class SourceItem:
    Type: int                   # SourceTypes
    Key: str
    Label: str
    URL: str
    DatePublished: datetime     # UTC
    ThumbnailURL: str = ''
    Language: str = ''
    Duration: int = 0
    ViewCount: int = 0
    LikeCount: int = 0
    CommentCount: int = 0
    ShareCount: int = 0
    IsPaywalled: bool = False
    MasterKey: str = ''         # key of the source this one belongs to (thread root, replied-to post)
    Contents: list = field(default_factory=list)    # ContentItems already at hand after listing
    Extra: dict = field(default_factory=dict)


class Connector:
    Platform: int = 0
    Label: str = ''
    InputHint: str = ''
    SourceTypeList: list = []       # SourceType IDs this platform can deliver
    RequestPause: float = 0.4       # seconds between calls, to stay polite

    def InputMatch(self, Input: str) -> bool:
        """True when the input unmistakably belongs to this platform (used for auto-detection)."""
        raise NotImplementedError

    def StatusGet(self) -> tuple[bool, str]:
        """(usable, note) - whether the connector can run right now (key present ...)."""
        return True, ''

    def ChannelLookup(self, Input: str) -> ChannelInfo:
        raise NotImplementedError

    def SourceListLoad(self, Channel: ChannelInfo, SourceTypes: list, DateStart: datetime | None,
                       DateEnd: datetime | None, Limit: int):
        """Yields SourceItems, newest first, within the date range, at most Limit (0 = all)."""
        raise NotImplementedError

    def SourceContentListLoad(self, Channel: ChannelInfo, Source: SourceItem) -> list:
        """Fetches the text of one source (article body, transcript). Returns ContentItems."""
        return []

    # ---- shared helpers -------------------------------------------------------------------
    def JsonLoad(self, URL: str, Parameters: dict | None = None, Headers: dict | None = None, Attempts: int = 4):
        """GET returning parsed JSON; waits and retries on rate limits and server errors."""
        Response = None
        for Attempt in range(Attempts):
            Response = requests.get(URL, params=Parameters, headers={'User-Agent': UserAgent, **(Headers or {})}, timeout=30)
            if Response.status_code in (429, 500, 502, 503, 504) and Attempt < Attempts - 1:
                Wait = Response.headers.get('Retry-After', '')
                time.sleep(min(int(Wait), 60) if Wait.isdigit() else 2 ** (Attempt + 1))
                continue
            break
        time.sleep(self.RequestPause)
        return Response


class HtmlTextParser(HTMLParser):
    """Reduces article HTML to readable plain text, keeping paragraph breaks and link targets."""
    BlockTags = {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'tr', 'figcaption', 'pre'}
    SkipTags = {'script', 'style', 'noscript', 'svg', 'button', 'form'}

    def __init__(self, SkipTags=None):
        super().__init__(convert_charrefs=True)
        self.Parts, self.SkipDepth = [], 0
        self.SkipTags = self.SkipTags | set(SkipTags or ())

    def handle_starttag(self, Tag, Attributes):
        if Tag in self.SkipTags:
            self.SkipDepth += 1
        elif Tag in self.BlockTags:
            self.Parts.append('\n')
        if Tag == 'li':
            self.Parts.append('- ')

    def handle_endtag(self, Tag):
        if Tag in self.SkipTags:
            self.SkipDepth = max(0, self.SkipDepth - 1)
        elif Tag in self.BlockTags:
            self.Parts.append('\n')

    def handle_data(self, Data):
        if not self.SkipDepth:
            self.Parts.append(Data)


def HtmlTextGet(Html: str, SkipTags=None) -> str:
    Parser = HtmlTextParser(SkipTags)
    Parser.feed(Html or '')
    Text = html.unescape(''.join(Parser.Parts)).replace('\xa0', ' ')
    Text = re.sub(r'[ \t]+', ' ', Text)
    Text = re.sub(r' ?\n ?', '\n', Text)
    return re.sub(r'\n{3,}', '\n\n', Text).strip()


def DateParse(Value: str) -> datetime | None:
    """ISO 8601 timestamp -> naive UTC datetime."""
    if not Value:
        return None
    from datetime import timezone
    Parsed = datetime.fromisoformat(Value.replace('Z', '+00:00'))
    if Parsed.tzinfo is not None:
        Parsed = Parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return Parsed.replace(microsecond=0)
