"""X (Twitter): API v2 with the app-only bearer token.

The timeline endpoint reaches back roughly 3,200 posts per account; older history needs
full-archive search, which depends on the plan of the developer account.
"""
import re

from .. import Config
from .Base import (Connector, ConnectorError, ChannelInfo, SourceItem, ContentItem, DateParse, PlatformX,
                   SourceTypePost, SourceTypeReply, ContentTypeBody)

Api = 'https://api.x.com/2'


class XConnector(Connector):
    Platform = PlatformX
    Label = 'X (Twitter)'
    InputHint = 'x.com/handle or @handle'
    SourceTypeList = [SourceTypePost, SourceTypeReply]
    RequestPause = 1.0

    def InputMatch(self, Input: str) -> bool:
        return bool(re.search(r'(?:^|[/.])(?:x|twitter)\.com/', Input, re.I))

    def StatusGet(self):
        return (True, '') if Config.XBearerTokenGet() else (False, 'No X bearer token in the credentials file.')

    def ApiLoad(self, Path: str, Parameters: dict) -> dict:
        Token = Config.XBearerTokenGet()
        if not Token:
            raise ConnectorError('No X bearer token in the credentials file.')
        Response = self.JsonLoad(f'{Api}/{Path}', Parameters, {'Authorization': f'Bearer {Token}'})
        if not Response.ok:
            try:
                Error = Response.json()
                Message = Error.get('detail') or Error.get('title') or ''
                Reason = Error.get('reason', '')
            except ValueError:
                Message, Reason = Response.text[:200], ''
            raise ConnectorError(f'X refused the request (HTTP {Response.status_code} {Reason}): {Message}')
        return Response.json()

    def ChannelLookup(self, Input: str) -> ChannelInfo:
        Match = re.search(r'(?:x|twitter)\.com/@?(\w{1,15})', Input, re.I) or re.fullmatch(r'@?(\w{1,15})', Input.strip())
        if not Match:
            raise ConnectorError('Enter an X profile URL or an @handle.')
        Data = self.ApiLoad(f'users/by/username/{Match.group(1)}',
                            {'user.fields': 'created_at,description,public_metrics,verified'})
        User = Data.get('data')
        if not User:
            raise ConnectorError(f'No X account named @{Match.group(1)} (suspended, renamed or mistyped).')
        Metrics = User.get('public_metrics', {})
        return ChannelInfo(
            Platform=self.Platform, Key=User['id'], Label=User.get('name', ''), Handle=User.get('username', ''),
            URL=f"https://x.com/{User.get('username', '')}", Description=User.get('description', ''),
            FollowerCount=int(Metrics.get('followers_count') or 0), SourceCount=int(Metrics.get('tweet_count') or 0),
            DateStart=DateParse(User.get('created_at')), PersonLabel=User.get('name', ''))

    def SourceListLoad(self, Channel, SourceTypes, DateStart, DateEnd, Limit):
        Count, Token = 0, None
        Exclude = ['retweets'] + ([] if (not SourceTypes or SourceTypeReply in SourceTypes) else ['replies'])
        while True:
            Parameters = {'max_results': 100, 'exclude': ','.join(Exclude),
                          'tweet.fields': 'created_at,public_metrics,conversation_id,referenced_tweets,lang,note_tweet'}
            if DateStart:
                Parameters['start_time'] = DateStart.strftime('%Y-%m-%dT%H:%M:%SZ')
            if DateEnd:
                Parameters['end_time'] = DateEnd.strftime('%Y-%m-%dT%H:%M:%SZ')
            if Token:
                Parameters['pagination_token'] = Token
            Page = self.ApiLoad(f'users/{Channel.Key}/tweets', Parameters)
            for Post in Page.get('data') or []:
                References = {R['type']: R['id'] for R in Post.get('referenced_tweets') or []}
                Type = SourceTypeReply if ('replied_to' in References or 'quoted' in References) else SourceTypePost
                if SourceTypes and Type not in SourceTypes:
                    continue
                Text = (Post.get('note_tweet') or {}).get('text') or Post.get('text', '')
                Metrics = Post.get('public_metrics', {})
                Item = SourceItem(
                    Type=Type, Key=Post['id'], Label=' '.join(Text.split())[:320] or '(no text)',
                    URL=f"https://x.com/{Channel.Handle}/status/{Post['id']}", DatePublished=DateParse(Post.get('created_at')),
                    Language=Post.get('lang', '') if Post.get('lang') not in ('und', 'zxx', 'qme') else '',
                    ViewCount=int(Metrics.get('impression_count') or 0), LikeCount=int(Metrics.get('like_count') or 0),
                    CommentCount=int(Metrics.get('reply_count') or 0),
                    ShareCount=int(Metrics.get('retweet_count') or 0) + int(Metrics.get('quote_count') or 0),
                    MasterKey=References.get('replied_to') or (Post.get('conversation_id') if Post.get('conversation_id') != Post['id'] else ''))
                Item.Contents.append(ContentItem(Type=ContentTypeBody, Text=Text, Language=Item.Language, Origin='x-api-v2'))
                yield Item
                Count += 1
                if Limit and Count >= Limit:
                    return
            Token = (Page.get('meta') or {}).get('next_token')
            if not Token:
                return
