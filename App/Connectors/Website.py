"""Any website or blog that publishes a sitemap (Ghost, WordPress and most other publishing systems).

Posts are found through the sitemap; each post page is read once for its title, publication
date and article text. Pages without a publication date (about pages, tag lists) are skipped.
No key needed. Members-only posts yield only the preview the site shows to everyone.
"""
import hashlib
import html
import json
import re
from urllib.parse import urlsplit

from .Base import (Connector, ConnectorError, ChannelInfo, SourceItem, ContentItem, HtmlTextGet, DateParse,
                   SourceTypeArticle, ContentTypeBody, ContentTypeDescription)

PlatformWebsite = 4
ArticleTypeList = ('Article', 'BlogPosting', 'NewsArticle', 'Report', 'TechArticle', 'OpinionNewsArticle', 'AnalysisNewsArticle')


class WebsiteConnector(Connector):
    Platform = PlatformWebsite
    Label = 'Website / blog'
    InputHint = 'the address of a blog or newsletter site, e.g. https://www.example.com'
    SourceTypeList = [SourceTypeArticle]
    RequestPause = 0.4

    def InputMatch(self, Input: str) -> bool:
        """Catch-all for web addresses; registered last so the specific platforms get first pick."""
        return bool(re.match(r'(https?://)?[\w\-]+(\.[\w\-]+)+(/|$)', Input.strip(), re.I))

    def PageLoad(self, URL: str):
        Response = self.JsonLoad(URL)       # plain GET with retry; the name is historical
        return Response

    def ChannelLookup(self, Input: str) -> ChannelInfo:
        Input = Input.strip()
        Parts = urlsplit(Input if re.match(r'https?://', Input, re.I) else 'https://' + Input)
        if not Parts.netloc:
            raise ConnectorError('Enter the address of the website.')
        Base = f'{Parts.scheme}://{Parts.netloc}'
        Home = self.PageLoad(Base + '/')
        if not Home.ok:
            raise ConnectorError(f'{Base} could not be opened (HTTP {Home.status_code}).')
        Probe = self.PageLoad(Base + '/api/v1/archive?sort=new&limit=1')
        if Probe.ok and Probe.text.lstrip().startswith('{"posts"'):
            raise ConnectorError('This site is a Substack publication. Choose Substack as the platform and look it up again.')
        Posts = self.PostListLoad(Base)
        if not Posts:
            raise ConnectorError(f'{Base} publishes no sitemap of its posts, so its articles cannot be listed automatically.')
        Label = (MetaGet(Home.text, 'og:site_name') or TitleGet(Home.text) or Parts.netloc)[:320]
        return ChannelInfo(Platform=self.Platform, Key=Parts.netloc.lower().removeprefix('www.'), Label=Label, Handle=Parts.netloc.lower(),
                           URL=Base, Description=(MetaGet(Home.text, 'description') or MetaGet(Home.text, 'og:description'))[:4000],
                           SourceCount=len(Posts), PersonLabel=Label, Extra={'Base': Base})

    def PostListLoad(self, Base: str) -> list:
        """(URL, last modified) of every post, newest change first. Prefers the sitemap(s) that hold posts."""
        Candidates = [Base + '/sitemap.xml', Base + '/sitemap_index.xml', Base + '/wp-sitemap.xml']
        Robots = self.PageLoad(Base + '/robots.txt')
        if Robots.ok:
            Candidates = re.findall(r'(?im)^sitemap:\s*(\S+)', Robots.text) + Candidates
        for Candidate in dict.fromkeys(Candidates):
            Response = self.PageLoad(Candidate)
            if not Response.ok or '<loc>' not in Response.text:
                continue
            Children = re.findall(r'<sitemap>\s*<loc>([^<]+)</loc>', Response.text)
            if Children:
                Wanted = [C for C in Children if re.search(r'post', C, re.I)] or \
                         [C for C in Children if not re.search(r'page|author|tag|categor|image|video', C, re.I)]
                Texts = [R.text for R in (self.PageLoad(html.unescape(C)) for C in Wanted) if R.ok]
            else:
                Texts = [Response.text]
            Posts = {}
            for Text in Texts:
                for Entry in re.findall(r'<url>(.*?)</url>', Text, re.S):
                    Loc = re.search(r'<loc>([^<]+)</loc>', Entry)
                    Modified = re.search(r'<lastmod>([^<]+)</lastmod>', Entry)
                    if Loc and urlsplit(html.unescape(Loc.group(1))).path.strip('/'):
                        Posts[html.unescape(Loc.group(1)).strip()] = DateParse(Modified.group(1).strip()) if Modified else None
            if Posts:
                return sorted(Posts.items(), key=lambda P: (P[1] is not None, P[1]), reverse=True)
        return []

    def SourceListLoad(self, Channel, SourceTypes, DateStart, DateEnd, Limit):
        Count = 0
        for URL, Modified in self.PostListLoad(Channel.Extra.get('Base') or Channel.URL):
            if DateStart and Modified and Modified < DateStart:
                continue        # last changed before the period, so it was published before it too
            Response = self.PageLoad(URL)
            if not Response.ok:
                continue
            Item = self.SourceItemGet(URL, Response.text)
            if Item is None or (DateStart and Item.DatePublished < DateStart) or (DateEnd and Item.DatePublished > DateEnd):
                continue
            yield Item
            Count += 1
            if Limit and Count >= Limit:
                return

    def SourceItemGet(self, URL: str, Page: str) -> SourceItem | None:
        """Reads one post page. Returns None when the page is not a dated article."""
        Data = {}
        for Block in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', Page, re.S):
            try:
                Parsed = json.loads(Block)
            except ValueError:
                continue
            for Node in (Parsed if isinstance(Parsed, list) else Parsed.get('@graph', [Parsed]) if isinstance(Parsed, dict) else []):
                Types = Node.get('@type') if isinstance(Node, dict) else None
                if isinstance(Node, dict) and any(T in ArticleTypeList for T in (Types if isinstance(Types, list) else [Types])):
                    Data = Node
        Published = DateParseSafe(Data.get('datePublished') or MetaGet(Page, 'article:published_time'))
        if Published is None:
            return None
        Title = (Data.get('headline') or MetaGet(Page, 'og:title') or TitleGet(Page) or '(untitled)').strip()
        Fragment = ElementGet(Page, 'article') or ElementGet(Page, 'main')
        Text = HtmlTextGet(Fragment, SkipTags={'nav', 'aside', 'footer', 'figure', 'iframe', 'header'}) if Fragment else ''
        Opening = re.search(r'<article\b[^>]*>', Page)
        Path = urlsplit(URL).path.strip('/')
        Item = SourceItem(
            Type=SourceTypeArticle, Key=Path if len(Path) <= 100 else hashlib.sha1(Path.encode()).hexdigest(),
            Label=html.unescape(Title)[:320], URL=URL, DatePublished=Published, ThumbnailURL=MetaGet(Page, 'og:image')[:1000],
            Language=(re.search(r'<html[^>]+lang="([\w\-]+)"', Page) or [None, ''])[1][:12],
            IsPaywalled=bool(Opening and re.search(r'post-access-(paid|members|tiers)|paywall', Opening.group(0))))
        if Text:
            Item.Contents.append(ContentItem(Type=ContentTypeBody, Text=Text, Language=Item.Language, Origin='website-html'))
        Summary = MetaGet(Page, 'description')
        if Summary and not Text:
            Item.Contents.append(ContentItem(Type=ContentTypeDescription, Text=Summary, Origin='website-html'))
        return Item

    def SourceContentListLoad(self, Channel, Source):
        Response = self.PageLoad(Source.URL)
        Item = self.SourceItemGet(Source.URL, Response.text) if Response.ok else None
        return Item.Contents if Item else []


def MetaGet(Page: str, Name: str) -> str:
    """Content of a <meta> tag by name or property, whichever attribute order the site uses."""
    Escaped = re.escape(Name)
    Match = (re.search(rf'<meta[^>]+(?:name|property)="{Escaped}"[^>]+content="([^"]*)"', Page, re.I)
             or re.search(rf'<meta[^>]+content="([^"]*)"[^>]+(?:name|property)="{Escaped}"', Page, re.I))
    return html.unescape(Match.group(1)).strip() if Match else ''


def TitleGet(Page: str) -> str:
    Match = re.search(r'<title[^>]*>(.*?)</title>', Page, re.S | re.I)
    return html.unescape(Match.group(1)).strip() if Match else ''


def DateParseSafe(Value):
    try:
        return DateParse(Value) if Value else None
    except ValueError:
        return None


def ElementGet(Page: str, Tag: str) -> str:
    """The first <Tag>...</Tag> element including nested elements of the same tag."""
    Start = re.search(rf'<{Tag}\b', Page, re.I)
    if not Start:
        return ''
    Depth = 0
    for Match in re.finditer(rf'<(/?){Tag}\b[^>]*>', Page[Start.start():], re.I):
        Depth += -1 if Match.group(1) else 1
        if Depth == 0:
            return Page[Start.start():Start.start() + Match.end()]
    return Page[Start.start():]
