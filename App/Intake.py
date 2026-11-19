"""Imports a channel and its sources. Runs as a Job in a background thread so the page stays responsive.

ChannelImportCreate() records the Job and starts it; ChannelImportRun() does the work:
look the channel up, make sure the Person and Channel exist, then walk the sources newest-first.
Sources already known are refreshed (counts), new ones are added with their text.
"""
import hashlib
import json
import threading
import traceback
from datetime import date, datetime, timedelta

from . import Config, Database
from .Connectors import ConnectorGet, ConnectorError, ChannelInfo, SourceItem, ContentItem

# Fixed lookup IDs (see Database/Seed.sql).
JobTypeSourceDiscovery, JobTypeContentFetch = 902, 903
JobStatusQueued, JobStatusRunning, JobStatusSucceeded, JobStatusPartial, JobStatusFailed = 901, 902, 903, 904, 905
SourceStatusDiscovered, SourceStatusContentFetched = 301, 302
ContentTypeTextList = (301, 303, 304, 305)      # content that carries the actual statements


def ChannelImportCreate(Parameters: dict, UserCreator: int = Config.UserAdministrator) -> int:
    """Parameters: Input, Platform, Person (0 = new), PersonLabel, SourceTypes [], DateStart, DateEnd
    (YYYY-MM-DD or ''), Limit, ContentLoad, ClaimHeadlineAdd."""
    JobID = Database.RowAdd('Jobs', 'JobID', {
        'JobType': JobTypeSourceDiscovery, 'JobStatus': JobStatusQueued,
        'JobLabel': f"Import {Parameters.get('Input', '')}"[:320], 'JobPlatform': int(Parameters.get('Platform') or 0),
        'JobPerson': int(Parameters.get('Person') or 0), 'JobInput': Parameters.get('Input', '')[:1000],
        'JobParameters': json.dumps(Parameters), 'JobUserCreator': UserCreator})
    threading.Thread(target=ChannelImportRun, args=(JobID, Parameters), daemon=True, name=f'Job{JobID}').start()
    return JobID


def JobEdit(JobID: int, **Values):
    Database.RowEdit('Jobs', 'JobID', JobID, Values)


def ChannelImportRun(JobID: int, Parameters: dict):
    Found = Added = Problems = 0
    try:
        JobEdit(JobID, JobStatus=JobStatusRunning, JobDateStart=datetime.utcnow(), JobMessage='Looking up the channel ...')
        Connector = ConnectorGet(int(Parameters['Platform']))
        Channel = Connector.ChannelLookup(Parameters['Input'])
        PersonID, ChannelID = ChannelSave(Channel, int(Parameters.get('Person') or 0), Parameters.get('PersonLabel', ''))
        JobEdit(JobID, JobPerson=PersonID, JobChannel=ChannelID, JobMessage=f'Listing sources of {Channel.Label} ...')

        DateStart = DateParse(Parameters.get('DateStart'))
        DateEnd = DateParse(Parameters.get('DateEnd'), EndOfDay=True)
        Limit = int(Parameters.get('Limit') or 0)
        SourceTypes = [int(T) for T in Parameters.get('SourceTypes') or []]
        for Item in Connector.SourceListLoad(Channel, SourceTypes, DateStart, DateEnd, Limit):
            Found += 1
            try:
                SourceID, IsNew = SourceSave(ChannelID, Item, JobID)
                if IsNew:
                    Added += 1
                    HasText = any([SourceContentAdd(SourceID, Content) and Content.Type in ContentTypeTextList for Content in Item.Contents])
                    if Parameters.get('ContentLoad') and not HasText and not Item.IsPaywalled:
                        for Content in Connector.SourceContentListLoad(Channel, Item):
                            HasText = (SourceContentAdd(SourceID, Content) and Content.Type in ContentTypeTextList) or HasText
                    if HasText:
                        Database.RowEdit('Sources', 'SourceID', SourceID, {'SourceStatus': SourceStatusContentFetched})
                    if Parameters.get('ClaimHeadlineAdd'):
                        SourceClaimHeadlineAdd(SourceID, PersonID, Item.Label)
            except Exception as Error:      # one bad item must not stop the run
                Problems += 1
                JobEdit(JobID, JobMessage=f'Problem with "{Item.Label[:80]}": {Error}'[:4000])
            if Found % 5 == 0:
                JobEdit(JobID, JobItemCountFound=Found, JobItemCountAdded=Added)

        Complete = not (Limit and Found >= Limit) and (not SourceTypes or set(SourceTypes) >= set(Connector.SourceTypeList))
        if Complete:
            ChannelCoverageEdit(ChannelID, DateStart, DateEnd)
        Message = f'{Found} sources found, {Added} new' + (f', {Problems} with problems' if Problems else '') + '.'
        if not Complete:
            Message += ' Partial import (limit or type filter): the coverage period was not updated.'
        JobEdit(JobID, JobStatus=JobStatusPartial if Problems else JobStatusSucceeded, JobItemCountFound=Found,
                JobItemCountAdded=Added, JobMessage=Message, JobDateEnd=datetime.utcnow())
    except ConnectorError as Error:
        JobEdit(JobID, JobStatus=JobStatusFailed, JobItemCountFound=Found, JobItemCountAdded=Added,
                JobMessage=str(Error)[:4000], JobDateEnd=datetime.utcnow())
    except Exception as Error:
        traceback.print_exc()
        JobEdit(JobID, JobStatus=JobStatusFailed, JobItemCountFound=Found, JobItemCountAdded=Added,
                JobMessage=f'Unexpected error: {Error!r}'[:4000], JobDateEnd=datetime.utcnow())


def DateParse(Value, EndOfDay: bool = False) -> datetime | None:
    if not Value:
        return None
    Parsed = datetime.strptime(Value, '%Y-%m-%d')
    return Parsed + timedelta(days=1, seconds=-1) if EndOfDay else Parsed


def ChannelSave(Channel: ChannelInfo, PersonID: int, PersonLabel: str) -> tuple[int, int]:
    """Makes sure the Person and the Channel exist; returns (PersonID, ChannelID)."""
    Existing = Database.RowLoad('SELECT ChannelID, ChannelPerson FROM dbo.Channels WHERE ChannelPlatform = ? AND ChannelKey = ?',
                                Channel.Platform, Channel.Key)
    if Existing and not PersonID:
        PersonID = Existing['ChannelPerson']
    if not PersonID:
        PersonID = Database.RowAdd('Persons', 'PersonID', {
            'PersonType': 101, 'PersonStatus': 102, 'PersonLabel': (PersonLabel or Channel.PersonLabel or Channel.Label)[:320],
            'PersonUserCreator': Config.UserAdministrator})
    Values = {
        'ChannelLabel': Channel.Label[:320], 'ChannelPerson': PersonID, 'ChannelHandle': Channel.Handle[:100],
        'ChannelURL': Channel.URL[:500], 'ChannelDescription': Channel.Description[:4000],
        'ChannelFollowerCount': Channel.FollowerCount, 'ChannelSourceCount': Channel.SourceCount,
        'ChannelDateStart': Channel.DateStart, 'ChannelDateSynced': datetime.utcnow()}
    if Existing:
        Database.RowEdit('Channels', 'ChannelID', Existing['ChannelID'], Values)
        return PersonID, Existing['ChannelID']
    ChannelID = Database.RowAdd('Channels', 'ChannelID', {
        **Values, 'ChannelType': 201, 'ChannelStatus': 201, 'ChannelPlatform': Channel.Platform, 'ChannelKey': Channel.Key,
        'ChannelUserCreator': Config.UserAdministrator})
    return PersonID, ChannelID


def SourceSave(ChannelID: int, Item: SourceItem, JobID: int = 0) -> tuple[int, bool]:
    """Adds the source, or refreshes its counts when already known. Returns (SourceID, IsNew)."""
    Counts = {'SourceViewCount': Item.ViewCount, 'SourceLikeCount': Item.LikeCount, 'SourceCommentCount': Item.CommentCount,
              'SourceShareCount': Item.ShareCount, 'SourceDateSynced': datetime.utcnow()}
    SourceID = Database.ValueLoad('SELECT SourceID FROM dbo.Sources WHERE SourceChannel = ? AND SourceKey = ?', ChannelID, Item.Key)
    if SourceID:
        Database.RowEdit('Sources', 'SourceID', SourceID, Counts)
        return SourceID, False
    Master = 0
    if Item.MasterKey:
        Master = Database.ValueLoad('SELECT SourceID FROM dbo.Sources WHERE SourceChannel = ? AND SourceKey = ?', ChannelID, Item.MasterKey) or 0
    SourceID = Database.RowAdd('Sources', 'SourceID', {
        **Counts, 'SourceType': Item.Type, 'SourceStatus': SourceStatusDiscovered, 'SourceMaster': Master,
        'SourceLabel': Item.Label[:320] or '(untitled)', 'SourceChannel': ChannelID, 'SourceKey': Item.Key,
        'SourceURL': Item.URL[:1000], 'SourceThumbnailURL': Item.ThumbnailURL[:1000], 'SourceLanguage': Item.Language[:12],
        'SourceDuration': Item.Duration, 'SourceIsPaywalled': Item.IsPaywalled, 'SourceJob': JobID,
        'SourceDatePublished': Item.DatePublished, 'SourceUserCreator': Config.UserSystem})
    return SourceID, True


def SourceContentAdd(SourceID: int, Content: ContentItem) -> bool:
    """Stores one text of a source unless the identical text is already there. Returns True when text exists."""
    if not Content.Text:
        return False
    Hash = hashlib.sha256(Content.Text.encode('utf-8')).digest()
    Known = Database.ValueLoad('SELECT COUNT(*) FROM dbo.SourceContents WHERE SourceContentSource = ? AND SourceContentType = ? '
                               'AND SourceContentHash = ?', SourceID, Content.Type, Hash)
    if not Known:
        Database.RowAdd('SourceContents', 'SourceContentID', {
            'SourceContentType': Content.Type, 'SourceContentSource': SourceID, 'SourceContentLanguage': Content.Language[:12],
            'SourceContentOrigin': Content.Origin[:100], 'SourceContentText': Content.Text, 'SourceContentData': Content.Data,
            'SourceContentLength': len(Content.Text), 'SourceContentHash': Hash})
    return True


def SourceClaimHeadlineAdd(SourceID: int, PersonID: int, Label: str):
    """The generic starting claim of a source: its title, exactly as published, awaiting review."""
    Database.RowAdd('SourceClaims', 'SourceClaimID', {
        'SourceClaimType': 501, 'SourceClaimStatus': 501, 'SourceClaimLabel': Label[:320], 'SourceClaimSource': SourceID,
        'SourceClaimPerson': PersonID, 'SourceClaimPart': 401, 'SourceClaimIsPrimary': True, 'SourceClaimQuote': Label,
        'SourceClaimUserCreator': Config.UserSystem})


def ChannelCoverageEdit(ChannelID: int, DateStart: datetime | None, DateEnd: datetime | None):
    """Widens the period for which the channel is known to be completely imported."""
    Row = Database.RowLoad(
        'SELECT c.ChannelCoverageDateStart, c.ChannelCoverageDateEnd, '
        '(SELECT MIN(s.SourceDatePublished) FROM dbo.Sources s WHERE s.SourceChannel = c.ChannelID) AS SourceDateFirst '
        'FROM dbo.Channels c WHERE c.ChannelID = ?', ChannelID)
    Start = DateStart.date() if DateStart else (Row['SourceDateFirst'].date() if Row['SourceDateFirst'] else None)
    End = min(DateEnd.date(), date.today()) if DateEnd else date.today()
    if Start is None:
        return
    if Row['ChannelCoverageDateStart'] and Row['ChannelCoverageDateEnd'] \
            and Start <= Row['ChannelCoverageDateEnd'] and End >= Row['ChannelCoverageDateStart']:     # overlapping: merge
        Start, End = min(Start, Row['ChannelCoverageDateStart']), max(End, Row['ChannelCoverageDateEnd'])
    Database.RowEdit('Channels', 'ChannelID', ChannelID, {'ChannelCoverageDateStart': Start, 'ChannelCoverageDateEnd': End})


def SourceContentLoadRun(SourceID: int) -> int:
    """Fetches (again) the text of one stored source. Returns the number of texts now stored for it."""
    Row = Database.RowLoad(
        'SELECT s.SourceID, s.SourceType, s.SourceKey, s.SourceLabel, s.SourceURL, s.SourceLanguage, s.SourceDatePublished, '
        'c.ChannelPlatform, c.ChannelKey, c.ChannelLabel, c.ChannelHandle, c.ChannelURL '
        'FROM dbo.Sources s LEFT OUTER JOIN dbo.Channels c ON c.ChannelID = s.SourceChannel WHERE s.SourceID = ?', SourceID)
    if not Row or not Row['ChannelPlatform']:
        raise ConnectorError('This source has no channel on a platform with a connector.')
    Connector = ConnectorGet(Row['ChannelPlatform'])
    Channel = ChannelInfo(Platform=Row['ChannelPlatform'], Key=Row['ChannelKey'], Label=Row['ChannelLabel'],
                          Handle=Row['ChannelHandle'], URL=Row['ChannelURL'], Extra={'Base': Row['ChannelURL']})
    Item = SourceItem(Type=Row['SourceType'], Key=Row['SourceKey'], Label=Row['SourceLabel'], URL=Row['SourceURL'],
                      DatePublished=Row['SourceDatePublished'], Language=Row['SourceLanguage'])
    HasText = False
    for Content in Connector.SourceContentListLoad(Channel, Item):
        HasText = (SourceContentAdd(SourceID, Content) and Content.Type in ContentTypeTextList) or HasText
    if HasText:
        Database.StatementExecute('UPDATE dbo.Sources SET SourceStatus = ? WHERE SourceID = ? AND SourceStatus = ?',
                                  SourceStatusContentFetched, SourceID, SourceStatusDiscovered)
    return Database.ValueLoad('SELECT COUNT(*) FROM dbo.SourceContents WHERE SourceContentSource = ?', SourceID)
