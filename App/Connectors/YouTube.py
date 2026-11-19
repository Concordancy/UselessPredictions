"""YouTube: Data API v3 for channels and videos (needs a standard API key with that API enabled),
public caption tracks for transcripts (no key).

Quota: listing costs 1 unit per 50 videos plus 1 unit per 50 video details; search is avoided.
"""
import json
import re

from .. import Config
from .Base import (Connector, ConnectorError, ChannelInfo, SourceItem, ContentItem, DateParse, PlatformYouTube,
                   SourceTypeVideo, SourceTypeShort, SourceTypeLivestream, ContentTypeDescription,
                   ContentTypeTranscriptPublisher, ContentTypeTranscriptAuto)

Api = 'https://www.googleapis.com/youtube/v3'

# Every channel has hidden playlists per kind of upload: the channel ID with another prefix.
PlaylistPrefixMap = {SourceTypeVideo: 'UULF', SourceTypeShort: 'UUSH', SourceTypeLivestream: 'UULV'}


class YouTubeConnector(Connector):
    Platform = PlatformYouTube
    Label = 'YouTube'
    InputHint = 'youtube.com/@handle, youtube.com/channel/UC..., or @handle'
    SourceTypeList = [SourceTypeVideo, SourceTypeShort, SourceTypeLivestream]
    RequestPause = 0.1

    def InputMatch(self, Input: str) -> bool:
        return bool(re.search(r'youtube\.com|youtu\.be', Input, re.I)) or bool(re.fullmatch(r'UC[\w\-]{22}', Input.strip()))

    def StatusGet(self):
        return (True, '') if Config.YouTubeKeyGet() else (False, 'No Google API key in the credentials file.')

    def ApiLoad(self, Resource: str, Parameters: dict) -> dict:
        Key = Config.YouTubeKeyGet()
        if not Key:
            raise ConnectorError('No Google API key in the credentials file.')
        Response = self.JsonLoad(f'{Api}/{Resource}', Parameters, {'X-Goog-Api-Key': Key})
        if not Response.ok:
            try:
                Error = Response.json().get('error', {})
                Message = Error.get('message', '')
                Reason = (Error.get('errors') or [{}])[0].get('reason', '') or Error.get('status', '')
            except ValueError:
                Message, Reason = Response.text[:200], ''
            raise ConnectorError(f'YouTube refused the request (HTTP {Response.status_code} {Reason}): {Message}')
        return Response.json()

    def ChannelLookup(self, Input: str) -> ChannelInfo:
        Input = Input.strip()
        Parts = 'snippet,statistics,contentDetails'
        Match = re.search(r'(UC[\w\-]{22})', Input)
        Handle = re.search(r'@([\w\.\-]+)', Input)
        Legacy = re.search(r'youtube\.com/(?:c|user)/([^/?#]+)', Input, re.I)
        Video = re.search(r'(?:v=|youtu\.be/|/shorts/|/live/)([\w\-]{11})', Input)
        if Match:
            Data = self.ApiLoad('channels', {'part': Parts, 'id': Match.group(1)})
        elif Handle:
            Data = self.ApiLoad('channels', {'part': Parts, 'forHandle': '@' + Handle.group(1)})
        elif Video:
            Videos = self.ApiLoad('videos', {'part': 'snippet', 'id': Video.group(1)}).get('items') or []
            if not Videos:
                raise ConnectorError('That video was not found.')
            Data = self.ApiLoad('channels', {'part': Parts, 'id': Videos[0]['snippet']['channelId']})
        elif Legacy:
            Data = self.ApiLoad('channels', {'part': Parts, 'forUsername': Legacy.group(1)})
            if not Data.get('items'):
                Data = self.ApiLoad('channels', {'part': Parts, 'forHandle': '@' + Legacy.group(1)})
        else:
            raise ConnectorError('Enter a YouTube channel URL, a video URL, or an @handle.')
        Items = Data.get('items') or []
        if not Items:
            raise ConnectorError('No YouTube channel matches that input.')
        Item = Items[0]
        Snippet, Statistics = Item.get('snippet', {}), Item.get('statistics', {})
        return ChannelInfo(
            Platform=self.Platform, Key=Item['id'], Label=Snippet.get('title', ''),
            Handle=Snippet.get('customUrl', ''), URL=f"https://www.youtube.com/channel/{Item['id']}",
            Description=Snippet.get('description', '')[:4000],
            FollowerCount=int(Statistics.get('subscriberCount') or 0), SourceCount=int(Statistics.get('videoCount') or 0),
            DateStart=DateParse(Snippet.get('publishedAt')), PersonLabel=Snippet.get('title', ''))

    def SourceListLoad(self, Channel, SourceTypes, DateStart, DateEnd, Limit):
        Count = 0
        for Type in (SourceTypes or self.SourceTypeList):
            Prefix = PlaylistPrefixMap.get(Type)
            if not Prefix:
                continue
            Playlist, Token = Prefix + Channel.Key[2:], None
            while True:
                Parameters = {'part': 'contentDetails', 'playlistId': Playlist, 'maxResults': 50}
                if Token:
                    Parameters['pageToken'] = Token
                try:
                    Page = self.ApiLoad('playlistItems', Parameters)
                except ConnectorError as Error:
                    if 'playlistNotFound' in str(Error) or '404' in str(Error):
                        break       # the channel has no uploads of this kind
                    raise
                Entries = [(E['contentDetails']['videoId'], DateParse(E['contentDetails'].get('videoPublishedAt')))
                           for E in Page.get('items', [])]
                Wanted = [ID for ID, Published in Entries
                          if Published and not (DateEnd and Published > DateEnd) and not (DateStart and Published < DateStart)]
                Details = self.ApiLoad('videos', {'part': 'snippet,contentDetails,statistics', 'id': ','.join(Wanted),
                                                  'maxResults': 50}).get('items', []) if Wanted else []
                for Video in Details:
                    yield self.SourceItemGet(Video, Type)
                    Count += 1
                    if Limit and Count >= Limit:
                        return
                Reached = any(Published and DateStart and Published < DateStart for _, Published in Entries)
                Token = Page.get('nextPageToken')
                if not Token or Reached:
                    break

    def SourceItemGet(self, Video: dict, Type: int) -> SourceItem:
        Snippet, Statistics = Video.get('snippet', {}), Video.get('statistics', {})
        Thumbnails = Snippet.get('thumbnails', {})
        Thumbnail = (Thumbnails.get('maxres') or Thumbnails.get('high') or Thumbnails.get('default') or {}).get('url', '')
        Item = SourceItem(
            Type=Type, Key=Video['id'], Label=Snippet.get('title', '')[:320],
            URL=f"https://www.youtube.com/watch?v={Video['id']}", DatePublished=DateParse(Snippet.get('publishedAt')),
            ThumbnailURL=Thumbnail, Language=Snippet.get('defaultAudioLanguage') or Snippet.get('defaultLanguage') or '',
            Duration=DurationParse(Video.get('contentDetails', {}).get('duration', '')),
            ViewCount=int(Statistics.get('viewCount') or 0), LikeCount=int(Statistics.get('likeCount') or 0),
            CommentCount=int(Statistics.get('commentCount') or 0))
        if Snippet.get('description'):
            Item.Contents.append(ContentItem(Type=ContentTypeDescription, Text=Snippet['description'], Origin='youtube-data-api'))
        return Item

    def SourceContentListLoad(self, Channel, Source):
        """Transcript from the public caption tracks; prefers captions the publisher uploaded."""
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import CouldNotRetrieveTranscript
        try:
            Tracks = YouTubeTranscriptApi().list(Source.Key)
            Languages = [Source.Language[:2]] if Source.Language else []
            Languages += [L for L in ('en',) if L not in Languages]
            try:
                Track = Tracks.find_manually_created_transcript(Languages)
            except CouldNotRetrieveTranscript:
                try:
                    Track = Tracks.find_generated_transcript(Languages)
                except CouldNotRetrieveTranscript:
                    Track = next(iter(Tracks), None)
            if Track is None:
                return []
            Fetched = Track.fetch()
        except CouldNotRetrieveTranscript:
            return []       # captions disabled, video private, or access blocked
        Segments = [{'Start': round(S.start, 2), 'Duration': round(S.duration, 2), 'Text': S.text} for S in Fetched.snippets]
        Text = '\n'.join(f"[{TimestampGet(S['Start'])}] {S['Text']}" for S in Segments)
        return [ContentItem(
            Type=ContentTypeTranscriptAuto if Fetched.is_generated else ContentTypeTranscriptPublisher,
            Text=Text, Language=Fetched.language_code, Origin='youtube-captions', Data=json.dumps(Segments, ensure_ascii=False))]


def DurationParse(Value: str) -> int:
    """ISO 8601 duration (PT1H2M3S) -> seconds."""
    Match = re.fullmatch(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', Value or '')
    if not Match:
        return 0
    Days, Hours, Minutes, Seconds = (int(G or 0) for G in Match.groups())
    return Days * 86400 + Hours * 3600 + Minutes * 60 + Seconds


def TimestampGet(Seconds: float) -> str:
    Seconds = int(Seconds)
    return f'{Seconds // 3600}:{Seconds % 3600 // 60:02d}:{Seconds % 60:02d}'
