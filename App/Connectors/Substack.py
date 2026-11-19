"""Substack: public JSON endpoints of each publication. No key needed.

Paid posts are listed (title, date) but only their free preview text is available.
"""
import re

from .Base import (Connector, ConnectorError, ChannelInfo, SourceItem, ContentItem, HtmlTextGet, DateParse,
                   PlatformSubstack, SourceTypeNewsletter, SourceTypePodcast, SourceTypeVideo, SourceTypeThread,
                   ContentTypeBody, ContentTypeDescription)

PageSize = 25   # the archive endpoint refuses more


class SubstackConnector(Connector):
    Platform = PlatformSubstack
    Label = 'Substack'
    InputHint = 'name.substack.com, a custom domain, or substack.com/@profile'
    SourceTypeList = [SourceTypeNewsletter, SourceTypePodcast, SourceTypeVideo, SourceTypeThread]
    TypeMap = {'newsletter': SourceTypeNewsletter, 'podcast': SourceTypePodcast, 'video': SourceTypeVideo,
               'thread': SourceTypeThread}

    def InputMatch(self, Input: str) -> bool:
        return 'substack.com' in Input.lower()

    def ChannelLookup(self, Input: str) -> ChannelInfo:
        Input = Input.strip()
        PersonLabel, Handle, Base = '', '', ''
        Profile = re.search(r'substack\.com/@([\w\-]+)', Input, re.I) or re.fullmatch(r'@([\w\-]+)', Input)
        if Profile:
            Response = self.JsonLoad(f'https://substack.com/api/v1/user/{Profile.group(1)}/public_profile')
            if not Response.ok:
                raise ConnectorError(f'Substack profile "@{Profile.group(1)}" was not found.')
            Data = Response.json()
            Publication = Data.get('primaryPublication') or {}
            if not Publication:
                raise ConnectorError(f'Substack profile "@{Profile.group(1)}" has no publication of its own.')
            PersonLabel = Data.get('name') or ''
            Handle = Publication.get('subdomain') or ''
            Base = 'https://' + (Publication.get('custom_domain') or f'{Handle}.substack.com')
        else:
            Host = re.sub(r'^https?://', '', Input, flags=re.I).split('/')[0].lower()
            if not Host:
                raise ConnectorError('Enter a Substack address such as name.substack.com.')
            if '.' not in Host:
                Host = f'{Host}.substack.com'
            Base = f'https://{Host}'
            Subdomain = re.fullmatch(r'([\w\-]+)\.substack\.com', Host)
            Handle = Subdomain.group(1) if Subdomain else ''

        Response = self.JsonLoad(f'{Base}/api/v1/archive', {'sort': 'new', 'limit': 1})
        if not Response.ok or 'posts' not in Response.text[:200]:
            raise ConnectorError(f'{Base} does not answer like a Substack publication (HTTP {Response.status_code}).')
        Posts = Response.json().get('posts') or []
        if not Posts:
            raise ConnectorError(f'{Base} has no public posts.')
        PublicationID = str(Posts[0].get('publication_id') or '')

        Label, Description = Handle or Base, ''
        Detail = self.JsonLoad(f"{Base}/api/v1/posts/{Posts[0]['slug']}")
        if Detail.ok:
            Bylines = Detail.json().get('publishedBylines') or []
            if Bylines and not PersonLabel:
                PersonLabel = Bylines[0].get('name') or ''
            for Byline in Bylines:
                for Membership in Byline.get('publicationUsers') or []:
                    Publication = Membership.get('publication') or {}
                    if str(Publication.get('id')) == PublicationID:
                        Label = Publication.get('name') or Label
                        Description = Publication.get('hero_text') or ''
                        Handle = Handle or Publication.get('subdomain') or ''
        return ChannelInfo(Platform=self.Platform, Key=PublicationID, Label=Label, Handle=Handle, URL=Base,
                           Description=Description, PersonLabel=PersonLabel, Extra={'Base': Base})

    def SourceListLoad(self, Channel, SourceTypes, DateStart, DateEnd, Limit):
        Base, Cursor, Count = Channel.Extra.get('Base') or Channel.URL, None, 0
        while True:
            Parameters = {'sort': 'new', 'limit': PageSize}
            if Cursor:
                Parameters['cursor'] = Cursor
            Response = self.JsonLoad(f'{Base}/api/v1/archive', Parameters)
            if not Response.ok:
                raise ConnectorError(f'Substack archive request failed (HTTP {Response.status_code}).')
            Data = Response.json()
            Posts = Data.get('posts') or []
            for Post in Posts:
                Published = DateParse(Post.get('post_date'))
                if Published is None or (DateEnd and Published > DateEnd):
                    continue
                if DateStart and Published < DateStart:
                    return
                Type = self.TypeMap.get(Post.get('type'), SourceTypeNewsletter)
                if SourceTypes and Type not in SourceTypes:
                    continue
                Item = SourceItem(
                    Type=Type, Key=str(Post['id']), Label=(Post.get('title') or '(untitled)')[:320],
                    URL=Post.get('canonical_url') or f"{Base}/p/{Post.get('slug')}", DatePublished=Published,
                    ThumbnailURL=Post.get('cover_image') or '',
                    Duration=int(Post.get('podcast_duration') or 0),
                    LikeCount=sum((Post.get('reactions') or {}).values()),
                    CommentCount=int(Post.get('comment_count') or 0), ShareCount=int(Post.get('restacks') or 0),
                    IsPaywalled=(Post.get('audience') not in (None, 'everyone')),
                    Extra={'Slug': Post.get('slug')})
                Summary = ' '.join(filter(None, [Post.get('subtitle'), Post.get('description')])).strip()
                if Summary and Summary != '...':
                    Item.Contents.append(ContentItem(Type=ContentTypeDescription, Text=Summary, Origin='substack-archive'))
                yield Item
                Count += 1
                if Limit and Count >= Limit:
                    return
            Cursor = Data.get('nextCursor')
            if not Cursor or not Posts:
                return

    def SourceContentListLoad(self, Channel, Source):
        Base = Channel.Extra.get('Base') or Channel.URL
        Slug = Source.Extra.get('Slug') or Source.URL.rstrip('/').rsplit('/p/', 1)[-1]
        Response = self.JsonLoad(f'{Base}/api/v1/posts/{Slug}')
        if not Response.ok:
            return []
        Text = HtmlTextGet(Response.json().get('body_html') or '')
        return [ContentItem(Type=ContentTypeBody, Text=Text, Origin='substack-post')] if Text else []
