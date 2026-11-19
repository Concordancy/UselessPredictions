"""Web application: management pages for all data, the intake page, and the analysis pages.

Start with Run.ps1 (or: python -m uvicorn App.Main:App --port 8765).
"""
import html
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from . import Analysis, Assessment, Config, Database, Intake, Registry
from .Connectors import ConnectorList, ConnectorGet, ConnectorDetect, ConnectorError

AppPath = Path(__file__).resolve().parent
App = FastAPI(title='Useless Predictions', docs_url=None, redoc_url=None)
App.mount('/Static', StaticFiles(directory=AppPath / 'Static'), name='Static')
Templates = Jinja2Templates(directory=AppPath / 'Templates')

PageSize = 50
# Tables that have a purpose-built page besides the generic editor.
ViewRouteMap = {'Persons': '/Persons/View/', 'Sources': '/Sources/View/', 'SourceClaims': '/SourceClaims/View/',
                'Reports': '/Reports/View/', 'Jobs': '/Jobs/View/'}
TableSortAscendingList = {'Lookups'}


# ---------------------------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------------------------

def WordsGet(Name: str) -> str:
    """'SourceClaimDueDateMax' -> 'Source Claim Due Date Max'."""
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', Name)


def ColumnTitleGet(Info: Registry.TableInfo, Name: str) -> str:
    """Column name without its class prefix, as words."""
    for Prefix in (Info.KeyColumn[:-2], Info.LabelColumn[:-5]):
        if Prefix and Name.startswith(Prefix) and len(Name) > len(Prefix):
            return WordsGet(Name[len(Prefix):])
    return WordsGet(Name)


def ValueTextGet(Value, Kind: str = '') -> str:
    if Value is None:
        return ''
    if isinstance(Value, bool):
        return 'Yes' if Value else 'No'
    if isinstance(Value, datetime):
        return Value.strftime('%Y-%m-%d %H:%M')
    if isinstance(Value, (bytes, bytearray)):
        return Value.hex()[:16] + ('...' if len(Value) > 8 else '')
    if isinstance(Value, Decimal):
        return f'{Value:.2f}'
    if isinstance(Value, int) and Kind == 'Number' and abs(Value) >= 10000:
        return f'{Value:,}'
    return str(Value)


def MarkdownHtmlGet(Text: str) -> Markup:
    """Small, safe Markdown subset (headings, lists, bold, italic) for model-written reports."""
    Lines, Out, InList = html.escape(Text or '').splitlines(), [], False
    for Line in Lines:
        Line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', Line)
        Line = re.sub(r'(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])', r'<em>\1</em>', Line)
        Line = re.sub(r'\[SC(\d+)\]', r'<a href="/SourceClaims/View/\1">[SC\1]</a>', Line)
        Item = re.match(r'\s*(?:[-*]|\d+\.)\s+(.*)', Line)
        if Item:
            if not InList:
                Out.append('<ul>')
                InList = True
            Out.append(f'<li>{Item.group(1)}</li>')
            continue
        if InList:
            Out.append('</ul>')
            InList = False
        Heading = re.match(r'(#{1,4})\s+(.*)', Line)
        if Heading:
            Level = min(len(Heading.group(1)) + 1, 5)
            Out.append(f'<h{Level}>{Heading.group(2)}</h{Level}>')
        elif Line.strip():
            Out.append(f'<p>{Line}</p>')
    if InList:
        Out.append('</ul>')
    return Markup('\n'.join(Out))


def RationaleHtmlGet(Text: str) -> Markup:
    """Verdict rationale with its [C123] markers linked to the citations listed on the same page."""
    return Markup(re.sub(r'\[C(\d+)\]', r'<a href="#C\1">[C\1]</a>', html.escape(Text or '')))


def DurationTextGet(Seconds: int) -> str:
    return f'{Seconds // 3600}:{Seconds % 3600 // 60:02d}:{Seconds % 60:02d}' if Seconds else ''


Templates.env.filters['Words'] = WordsGet
Templates.env.filters['Text'] = ValueTextGet
Templates.env.filters['Markdown'] = MarkdownHtmlGet
Templates.env.filters['Duration'] = DurationTextGet
Templates.env.filters['Rationale'] = RationaleHtmlGet


def PageRender(Request_: Request, Template: str, **Context):
    Menu = [(Group, [Table for Table, _ in Tables]) for Group, Tables in Registry.TableGroupList]
    return Templates.TemplateResponse(Request_, Template, {'Menu': Menu, 'ViewRouteMap': ViewRouteMap, **Context})


def ServiceStatusListGet() -> list:
    """(service, usable, note) for the home page."""
    Result = []
    for Item in ConnectorList:
        Usable, Note = Item.StatusGet()
        Result.append((Item.Label, Usable, Note or 'Key present (checked when used)' if Item.Platform != 3 else 'No key needed'))
    Usable, Note = Analysis.StatusGet()
    Result.append(('Claude (AI analysis)', Usable, Note or 'Key present (checked when used)'))
    return Result


# ---------------------------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------------------------

@App.get('/', response_class=HTMLResponse)
def HomeView(request: Request):
    Counts = Database.RowLoad(
        'SELECT (SELECT COUNT(*) FROM dbo.Persons WHERE PersonID > 0) AS Persons, '
        '(SELECT COUNT(*) FROM dbo.Channels WHERE ChannelID > 0) AS Channels, '
        '(SELECT COUNT(*) FROM dbo.Sources WHERE SourceID > 0) AS Sources, '
        '(SELECT COUNT(*) FROM dbo.SourceClaims WHERE SourceClaimID > 0 AND SourceClaimStatus <> 503) AS SourceClaims, '
        '(SELECT COUNT(*) FROM dbo.SourceClaims WHERE SourceClaimStatus = 501 AND SourceClaimID > 0) AS SourceClaimsUnreviewed, '
        '(SELECT COUNT(*) FROM dbo.Claims WHERE ClaimID > 0) AS Claims, '
        '(SELECT COUNT(*) FROM dbo.Assessments WHERE AssessmentIsCurrent = 1) AS Assessments, '
        '(SELECT COUNT(*) FROM dbo.Reports WHERE ReportID > 0) AS Reports')
    Persons = Database.RowListLoad(
        'SELECT TOP 25 s.*, (SELECT COUNT(*) FROM dbo.Channels c WHERE c.ChannelPerson = s.PersonID) AS PersonChannelCount, '
        '(SELECT COUNT(*) FROM dbo.Sources so LEFT OUTER JOIN dbo.Channels c ON c.ChannelID = so.SourceChannel '
        ' WHERE c.ChannelPerson = s.PersonID) AS PersonSourceCount '
        'FROM dbo.PersonScoreSummary s ORDER BY s.PersonID DESC')
    Jobs = Database.RowListLoad(
        'SELECT TOP 8 j.JobID, j.JobLabel, j.JobItemCountFound, j.JobItemCountAdded, j.JobDateCreated, st.StatusLabel '
        'FROM dbo.Jobs j LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = j.JobStatus WHERE j.JobID > 0 ORDER BY j.JobID DESC')
    return PageRender(request, 'Home.html', Title='Overview', Counts=Counts, Persons=Persons, Jobs=Jobs,
                      Services=ServiceStatusListGet())


# ---------------------------------------------------------------------------------------------
# Generic data manager
# ---------------------------------------------------------------------------------------------

def TableInfoGet(Table: str) -> Registry.TableInfo | None:
    try:
        return Registry.TableGet(Table)
    except KeyError:
        return None


@App.get('/Manage/{Table}', response_class=HTMLResponse)
def ManageListView(request: Request, Table: str, Search: str = '', Page: int = 1):
    Info = TableInfoGet(Table)
    if Info is None:
        return PageRender(request, 'Message.html', Title='Not found', Message=f'There is no table named {Table}.')
    Columns = [Info.ColumnGet(Name) for Name in Info.ListColumns if Info.ColumnGet(Name)]
    Where, Values, Filters = [], [], {}
    if Info.HasZeroRow:
        Where.append(f'x.[{Info.KeyColumn}] <> 0')
    for Name, Value in request.query_params.items():
        Column = Info.ColumnGet(Name)
        if Column is not None and Value != '' and Column.Kind in ('Reference', 'Number', 'Flag') and re.fullmatch(r'-?\d+', Value):
            Where.append(f'x.[{Column.Name}] = ?')
            Values.append(int(Value))
            Filters[Name] = int(Value)
    if Search.strip():
        Searchable = [C.Name for C in Info.Columns if C.Kind in ('Text', 'TextLong') and not C.IsComputed and C.TypeName not in ('ntext', 'text')]
        if Searchable:
            Where.append('(' + ' OR '.join(f'x.[{Name}] LIKE ?' for Name in Searchable) + ')')
            Values += [f'%{Search.strip()}%'] * len(Searchable)
    WhereSql = ('WHERE ' + ' AND '.join(Where)) if Where else ''
    Total = Database.ValueLoad(f'SELECT COUNT(*) FROM dbo.[{Table}] x {WhereSql}', *Values)
    Page = max(1, Page)
    Direction = 'ASC' if (Info.Group in TableSortAscendingList or Table in ('Types', 'Statuses', 'Users')) else 'DESC'
    Select = ', '.join(f'x.[{Name}]' for Name in dict.fromkeys([Info.KeyColumn, Info.LabelColumn] + [C.Name for C in Columns]) if Name)
    Rows = Database.RowListLoad(
        f'SELECT {Select} FROM dbo.[{Table}] x {WhereSql} ORDER BY x.[{Info.KeyColumn}] {Direction} '
        f'OFFSET ? ROWS FETCH NEXT ? ROWS ONLY', *Values, (Page - 1) * PageSize, PageSize)
    Labels = {C.Name: Registry.ReferenceLabelMapLoad(C, [Row[C.Name] for Row in Rows]) for C in Columns if C.Kind == 'Reference'}
    FilterOptions = []
    for Column in Columns:
        if Column.Kind == 'Reference' and (Column.Reference[1] is not None or Column.Reference[0] not in ViewRouteMap):
            Options = Registry.ReferenceOptionListLoad(Column)
            if Options is not None and len(Options) <= 80:
                FilterOptions.append((Column, ColumnTitleGet(Info, Column.Name), Options))
    FilterNotes = []
    for Name, Value in Filters.items():
        Column = Info.ColumnGet(Name)
        Label = Registry.ReferenceLabelMapLoad(Column, [Value]).get(Value, Value) if Column.Kind == 'Reference' else Value
        FilterNotes.append((ColumnTitleGet(Info, Name), Label))
    Query = {**Filters, **({'Search': Search} if Search else {})}
    return PageRender(request, 'ManageList.html', Title=WordsGet(Table), Info=Info, Columns=Columns, Rows=Rows, Labels=Labels,
                      Titles={C.Name: ColumnTitleGet(Info, C.Name) for C in Columns}, Total=Total, Page=Page,
                      PageCount=max(1, -(-Total // PageSize)), Search=Search, Filters=Filters, FilterOptions=FilterOptions,
                      FilterNotes=FilterNotes, QueryString=urlencode(Query), CreateQuery=urlencode(Filters),
                      FilterHidden={Name: Value for Name, Value in Filters.items() if Name not in [C.Name for C, _, _ in FilterOptions]})


def ManageFieldListGet(Info: Registry.TableInfo, Row: dict, IsNew: bool) -> list:
    Fields = []
    for Column in Info.Columns:
        Value = Row.get(Column.Name)
        ReadOnly = not Column.IsEditable or (Column.Name == Info.KeyColumn and not IsNew)
        if IsNew and ReadOnly:
            continue
        Field = {'Name': Column.Name, 'Title': ColumnTitleGet(Info, Column.Name), 'Kind': Column.Kind, 'Value': Value,
                 'ReadOnly': ReadOnly, 'Length': Column.Length, 'Options': None, 'ReferenceLabel': '', 'ReferenceTable': '',
                 'IsNullable': Column.IsNullable}
        if Column.Kind == 'Reference' and Column.Name != Info.KeyColumn:
            Field['ReferenceTable'] = Column.Reference[0]
            Field['Options'] = Registry.ReferenceOptionListLoad(Column, Value)
            if Field['Options'] is None and Value:
                Field['ReferenceLabel'] = Registry.ReferenceLabelMapLoad(Column, [Value]).get(Value, '')
        elif Column.Kind == 'Reference':
            Field['Kind'] = 'Number'
        if Column.Kind == 'DateTime' and isinstance(Value, datetime):
            Field['Value'] = Value.strftime('%Y-%m-%dT%H:%M:%S')
        if Column.Kind == 'Binary':
            Field['Value'] = ValueTextGet(Value)
        if Column.Kind == 'TextLong':
            Field['Rows'] = min(18, max(3, len(str(Value or '')) // 110 + 2))
        Fields.append(Field)
    return Fields


def ManageEditRender(request: Request, Info: Registry.TableInfo, Row: dict, IsNew: bool, Error: str = ''):
    Related = []
    if not IsNew:
        ID = Row[Info.KeyColumn]
        for OtherTable, ColumnName in Registry.ReferenceReverseListGet(Info.Table):
            Count = Database.ValueLoad(f'SELECT COUNT(*) FROM dbo.[{OtherTable}] WHERE [{ColumnName}] = ?', ID)
            if Count:
                Related.append((OtherTable, ColumnName, Count, ColumnTitleGet(Registry.TableGet(OtherTable), ColumnName)))
    Title = ('New ' + WordsGet(Info.KeyColumn[:-2])) if IsNew else (str(Row.get(Info.LabelColumn) or '')[:90] or WordsGet(Info.Table))
    return PageRender(request, 'ManageEdit.html', Title=Title, Info=Info, Fields=ManageFieldListGet(Info, Row, IsNew), IsNew=IsNew,
                      KeyValue=None if IsNew else Row[Info.KeyColumn], Related=Related, Error=Error)


@App.get('/Manage/{Table}/Create', response_class=HTMLResponse)
def ManageCreateView(request: Request, Table: str):
    Info = TableInfoGet(Table)
    if Info is None:
        return PageRender(request, 'Message.html', Title='Not found', Message=f'There is no table named {Table}.')
    Row = {}
    for Name, Value in request.query_params.items():        # preset references when coming from a filtered list
        if Info.ColumnGet(Name) is not None and re.fullmatch(r'-?\d+', Value):
            Row[Name] = int(Value)
    return ManageEditRender(request, Info, Row, True)


@App.get('/Manage/{Table}/Edit/{ID}', response_class=HTMLResponse)
def ManageEditView(request: Request, Table: str, ID: int):
    Info = TableInfoGet(Table)
    Row = Database.RowLoad(f'SELECT * FROM dbo.[{Table}] WHERE [{Info.KeyColumn}] = ?', ID) if Info else None
    if Row is None:
        return PageRender(request, 'Message.html', Title='Not found', Message='That record does not exist (any more).')
    return ManageEditRender(request, Info, Row, False)


def ManageValuesParse(Info: Registry.TableInfo, Form, IsNew: bool) -> tuple[dict, dict, str]:
    """Form -> (values to store, values to show again, first problem found)."""
    Values, Shown = {}, {}
    for Column in Info.Columns:
        if not Column.IsEditable or (Column.Name == Info.KeyColumn and not IsNew):
            continue
        Raw = (Form.get(Column.Name) or '').strip() if Column.Kind != 'Flag' else Form.get(Column.Name)
        Title = ColumnTitleGet(Info, Column.Name)
        try:
            if Column.Kind == 'Flag':
                Value = Raw is not None
            elif Column.Kind in ('Number', 'Reference'):
                Value = (None if Column.IsNullable else 0) if Raw == '' else int(Raw)
            elif Column.Kind == 'Decimal':
                Value = (None if Column.IsNullable else Decimal(0)) if Raw == '' else Decimal(Raw)
            elif Column.Kind == 'Date':
                Value = None if Raw == '' else date.fromisoformat(Raw)
            elif Column.Kind == 'DateTime':
                Value = None if Raw == '' else datetime.fromisoformat(Raw)
            else:
                Value = Form.get(Column.Name) or ''
                Value = Value.replace('\r\n', '\n') if Column.Kind == 'TextLong' else Value.strip()
                if 0 < Column.Length < len(Value):
                    return Values, Shown, f'{Title} is {len(Value)} characters long; at most {Column.Length} fit.'
        except (ValueError, InvalidOperation):
            return Values, Shown, f'{Title}: "{Raw}" is not a valid value.'
        Shown[Column.Name] = Value
        if Value is None and not Column.IsNullable:
            if IsNew and Column.Kind == 'DateTime':
                continue        # left blank on a new record: the database fills in "now"
            return Values, Shown, f'{Title} is required.'
        Values[Column.Name] = Value
    return Values, Shown, ''


@App.post('/Manage/{Table}/Save')
async def ManageSave(request: Request, Table: str):
    Info = TableInfoGet(Table)
    if Info is None:
        return PageRender(request, 'Message.html', Title='Not found', Message=f'There is no table named {Table}.')
    Form = await request.form()
    KeyText = Form.get('KeyValue') or ''
    IsNew = KeyText == ''
    Values, Shown, Error = ManageValuesParse(Info, Form, IsNew)

    def Work():
        if Error:
            return None, Error
        try:
            if IsNew:
                return Database.RowAdd(Table, Info.KeyColumn, Values), ''
            Database.RowEdit(Table, Info.KeyColumn, int(KeyText), Values)
            return int(KeyText), ''
        except Exception as Problem:
            Text = str(Problem)
            Match = re.search(r'\]([^\[\]]*?)\s*\(\d+\)\s*\(SQL', Text)
            return None, 'The database refused this: ' + (Match.group(1).strip() if Match else Text[:300])

    ID, Problem = await run_in_threadpool(Work)
    if Problem:
        Row = {**Shown, **({} if IsNew else {Info.KeyColumn: int(KeyText)})}
        if not IsNew:
            Stored = await run_in_threadpool(Database.RowLoad, f'SELECT * FROM dbo.[{Table}] WHERE [{Info.KeyColumn}] = ?', int(KeyText))
            Row = {**(Stored or {}), **Shown}
        return await run_in_threadpool(ManageEditRender, request, Info, Row, IsNew, Problem)
    return RedirectResponse(f'/Manage/{Table}/Edit/{ID}?Saved=1', status_code=303)


@App.post('/Manage/{Table}/Delete/{ID}')
def ManageDelete(request: Request, Table: str, ID: int):
    Info = TableInfoGet(Table)
    if Info is None or (ID == 0 and Info.HasZeroRow):
        return PageRender(request, 'Message.html', Title='Not possible', Message='Record 0 is the "none" placeholder and has to stay.')
    Database.RowDelete(Table, Info.KeyColumn, ID)
    return RedirectResponse(f'/Manage/{Table}', status_code=303)


# ---------------------------------------------------------------------------------------------
# Intake: add a channel and import its sources
# ---------------------------------------------------------------------------------------------

def IntakeRender(request: Request, **Context):
    Platforms = [(Item.Platform, Item.Label, Item.InputHint, *Item.StatusGet()) for Item in ConnectorList]
    Persons = Database.RowListLoad('SELECT PersonID, PersonLabel FROM dbo.Persons WHERE PersonID > 0 ORDER BY PersonLabel')
    return PageRender(request, 'Intake.html', Title='Add a channel', Platforms=Platforms, Persons=Persons,
                      **{'Input': '', 'Platform': 0, 'Channel': None, 'Error': '', 'SourceTypes': [], 'Known': None, **Context})


@App.get('/Intake', response_class=HTMLResponse)
def IntakeView(request: Request):
    return IntakeRender(request)


@App.post('/Intake/Lookup', response_class=HTMLResponse)
async def IntakeLookup(request: Request):
    Form = await request.form()
    Input, Platform = (Form.get('Input') or '').strip(), int(Form.get('Platform') or 0)

    def Work():
        if not Input:
            return IntakeRender(request, Error='Enter a channel URL, a Substack address or an account handle.')
        try:
            Connector = ConnectorGet(Platform) if Platform else ConnectorDetect(Input)
            if Connector is None:
                return IntakeRender(request, Input=Input, Error='I cannot tell the platform from that input (a bare @handle or a '
                                    'custom domain could be several). Choose the platform and look it up again.')
            Channel = Connector.ChannelLookup(Input)
        except ConnectorError as Problem:
            return IntakeRender(request, Input=Input, Platform=Platform, Error=str(Problem))
        Known = Database.RowLoad(
            'SELECT c.ChannelID, c.ChannelPerson, p.PersonLabel, c.ChannelCoverageDateStart, c.ChannelCoverageDateEnd, '
            '(SELECT COUNT(*) FROM dbo.Sources s WHERE s.SourceChannel = c.ChannelID) AS SourceCount '
            'FROM dbo.Channels c LEFT OUTER JOIN dbo.Persons p ON p.PersonID = c.ChannelPerson '
            'WHERE c.ChannelPlatform = ? AND c.ChannelKey = ?', Channel.Platform, Channel.Key)
        Types = Database.RowListLoad(
            f"SELECT SourceTypeID, SourceTypeLabel FROM dbo.SourceTypes WHERE SourceTypeID IN ({', '.join('?' for _ in Connector.SourceTypeList)}) "
            'ORDER BY SourceTypeOrder', *Connector.SourceTypeList)
        return IntakeRender(request, Input=Input, Platform=Connector.Platform, Channel=Channel, SourceTypes=Types, Known=Known)

    return await run_in_threadpool(Work)


@App.post('/Intake/Import')
async def IntakeImport(request: Request):
    Form = await request.form()
    Parameters = {
        'Input': (Form.get('Input') or '').strip(), 'Platform': int(Form.get('Platform') or 0),
        'Person': int(Form.get('Person') or 0), 'PersonLabel': (Form.get('PersonLabel') or '').strip(),
        'SourceTypes': [int(Value) for Value in Form.getlist('SourceTypes')],
        'DateStart': Form.get('DateStart') or '', 'DateEnd': Form.get('DateEnd') or '',
        'Limit': max(0, int(Form.get('Limit') or 0)), 'ContentLoad': Form.get('ContentLoad') is not None,
        'ClaimHeadlineAdd': Form.get('ClaimHeadlineAdd') is not None}
    JobID = await run_in_threadpool(Intake.ChannelImportCreate, Parameters)
    return RedirectResponse(f'/Jobs/View/{JobID}', status_code=303)


@App.get('/Jobs/View/{ID}', response_class=HTMLResponse)
def JobView(request: Request, ID: int):
    Job = Database.RowLoad(
        'SELECT j.*, st.StatusLabel, t.TypeLabel, c.ChannelLabel, p.PersonLabel FROM dbo.Jobs j '
        'LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = j.JobStatus LEFT OUTER JOIN dbo.Types t ON t.TypeID = j.JobType '
        'LEFT OUTER JOIN dbo.Channels c ON c.ChannelID = j.JobChannel LEFT OUTER JOIN dbo.Persons p ON p.PersonID = j.JobPerson '
        'WHERE j.JobID = ?', ID)
    if Job is None:
        return PageRender(request, 'Message.html', Title='Not found', Message='That job does not exist.')
    try:
        Parameters = json.loads(Job['JobParameters'] or '{}')
    except ValueError:
        Parameters = {}
    return PageRender(request, 'JobView.html', Title=Job['JobLabel'], Job=Job, Parameters=Parameters,
                      IsActive=Job['JobStatus'] in (901, 902))


# ---------------------------------------------------------------------------------------------
# Person, source and report pages
# ---------------------------------------------------------------------------------------------

@App.get('/Persons/View/{ID}', response_class=HTMLResponse)
def PersonView(request: Request, ID: int, Notice: str = ''):
    Person = Database.RowLoad(
        'SELECT p.*, t.TypeLabel, st.StatusLabel, cat.CategoryLabel FROM dbo.Persons p '
        'LEFT OUTER JOIN dbo.Types t ON t.TypeID = p.PersonType LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = p.PersonStatus '
        'LEFT OUTER JOIN dbo.Categories cat ON cat.CategoryID = p.PersonCategory WHERE p.PersonID = ? AND p.PersonID > 0', ID)
    if Person is None:
        return PageRender(request, 'Message.html', Title='Not found', Message='That person does not exist.')
    Score = Database.RowLoad('SELECT * FROM dbo.PersonScoreSummary WHERE PersonID = ?', ID)
    Channels = Database.RowListLoad(
        'SELECT c.*, pl.PlatformLabel, st.StatusLabel, (SELECT COUNT(*) FROM dbo.Sources s WHERE s.SourceChannel = c.ChannelID) AS SourceCountStored, '
        '(SELECT COUNT(*) FROM dbo.Sources s WHERE s.SourceChannel = c.ChannelID AND s.SourceStatus = 302) AS SourceCountReady '
        'FROM dbo.Channels c LEFT OUTER JOIN dbo.Platforms pl ON pl.PlatformID = c.ChannelPlatform '
        'LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = c.ChannelStatus WHERE c.ChannelPerson = ? ORDER BY c.ChannelID', ID)
    Claims = Database.RowListLoad(
        'SELECT TOP 60 l.* FROM dbo.SourceClaimList l WHERE l.PersonID = ? AND l.SourceClaimStatus <> 503 '
        'ORDER BY l.SourceDatePublished DESC, l.SourceClaimID DESC', ID)
    ClaimCount = Database.ValueLoad('SELECT COUNT(*) FROM dbo.SourceClaims WHERE SourceClaimPerson = ? AND SourceClaimStatus <> 503', ID)
    Reports = Database.RowListLoad(
        'SELECT TOP 10 r.ReportID, r.ReportLabel, r.ReportIsCurrent, r.ReportClaimCount, r.ReportDateCreated, r.ReportSummary, '
        'st.StatusLabel, t.TypeLabel FROM dbo.Reports r LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = r.ReportStatus '
        'LEFT OUTER JOIN dbo.Types t ON t.TypeID = r.ReportType WHERE r.ReportPerson = ? AND r.ReportID > 0 ORDER BY r.ReportID DESC', ID)
    Verdict = Database.RowListLoad(
        'SELECT d.DimensionLabel, rd.ReportDimensionScore, rd.ReportDimensionClaimCount, rd.ReportDimensionRationale, r.ReportID '
        'FROM dbo.Reports r LEFT OUTER JOIN dbo.ReportDimensions rd ON rd.ReportDimensionReport = r.ReportID '
        'LEFT OUTER JOIN dbo.Dimensions d ON d.DimensionID = rd.ReportDimensionDimension '
        'WHERE r.ReportPerson = ? AND r.ReportType = 1201 AND r.ReportIsCurrent = 1 AND rd.ReportDimensionID IS NOT NULL '
        'ORDER BY d.DimensionOrder', ID)
    Provisional = Database.RowLoad(
        'SELECT COUNT(*) AS Total, SUM(CASE WHEN l.AssessmentStatus = 601 THEN 1 ELSE 0 END) AS Proposed, '
        'SUM(CASE WHEN l.ClaimOutcomeIsCounted = 1 THEN 1 ELSE 0 END) AS Scored, '
        'SUM(CASE WHEN l.ClaimOutcomeGroupID = 2 THEN 1 ELSE 0 END) AS Correct, SUM(CASE WHEN l.ClaimOutcomeGroupID = 3 THEN 1 ELSE 0 END) AS Partial, '
        'SUM(CASE WHEN l.ClaimOutcomeGroupID = 4 THEN 1 ELSE 0 END) AS Incorrect, '
        'AVG(CASE WHEN l.ClaimOutcomeIsCounted = 1 THEN CAST(l.AssessmentScore AS DECIMAL(9,4)) END) AS ScoreAverage '
        'FROM dbo.SourceClaimList l WHERE l.PersonID = ? AND l.SourceClaimStatus <> 503 AND l.SourceClaimType IN (501, 502) '
        'AND l.AssessmentID IS NOT NULL', ID)
    return PageRender(request, 'PersonView.html', Title=Person['PersonLabel'], Person=Person, Score=Score, Channels=Channels,
                      Claims=Claims, ClaimCount=ClaimCount, Reports=Reports, Verdict=Verdict, Notice=Notice,
                      Provisional=Provisional, WaitingCount=len(Assessment.SourceClaimAssessListLoad(ID)),
                      AssessBatchCountMax=Config.AssessBatchCountMax, AnalysisStatus=Analysis.StatusGet())


@App.get('/Sources/View/{ID}', response_class=HTMLResponse)
def SourceView(request: Request, ID: int, Notice: str = '', Error: str = ''):
    Source = Database.RowLoad(
        'SELECT s.*, st.SourceTypeLabel, stat.StatusLabel, c.ChannelLabel, c.ChannelPerson, pl.PlatformLabel, p.PersonLabel '
        'FROM dbo.Sources s LEFT OUTER JOIN dbo.SourceTypes st ON st.SourceTypeID = s.SourceType '
        'LEFT OUTER JOIN dbo.Statuses stat ON stat.StatusID = s.SourceStatus '
        'LEFT OUTER JOIN dbo.Channels c ON c.ChannelID = s.SourceChannel '
        'LEFT OUTER JOIN dbo.Platforms pl ON pl.PlatformID = c.ChannelPlatform '
        'LEFT OUTER JOIN dbo.Persons p ON p.PersonID = c.ChannelPerson WHERE s.SourceID = ? AND s.SourceID > 0', ID)
    if Source is None:
        return PageRender(request, 'Message.html', Title='Not found', Message='That source does not exist.')
    Contents = Database.RowListLoad(
        'SELECT sc.SourceContentID, sc.SourceContentLanguage, sc.SourceContentOrigin, sc.SourceContentLength, sc.SourceContentDateFetched, '
        'sc.SourceContentText, sc.SourceContentType, t.TypeLabel FROM dbo.SourceContents sc '
        'LEFT OUTER JOIN dbo.Types t ON t.TypeID = sc.SourceContentType WHERE sc.SourceContentSource = ? ORDER BY sc.SourceContentType DESC', ID)
    Claims = Database.RowListLoad('SELECT l.* FROM dbo.SourceClaimList l WHERE l.SourceID = ? ORDER BY l.SourceClaimOffsetStart, l.SourceClaimID', ID)
    return PageRender(request, 'SourceView.html', Title=Source['SourceLabel'], Source=Source, Contents=Contents, Claims=Claims,
                      Notice=Notice, Error=Error, AnalysisStatus=Analysis.StatusGet())


@App.post('/Sources/ContentLoad/{ID}')
def SourceContentLoad(ID: int):
    try:
        Count = Intake.SourceContentLoadRun(ID)
        Query = {'Notice': f'{Count} text(s) stored for this source.' if Count else 'The platform offered no text for this source.'}
    except ConnectorError as Problem:
        Query = {'Error': str(Problem)}
    return RedirectResponse(f'/Sources/View/{ID}?{urlencode(Query)}', status_code=303)


@App.post('/Sources/ClaimExtract/{ID}')
def SourceClaimExtract(ID: int):
    try:
        Count = Analysis.SourceClaimExtractRun(ID)
        Query = {'Notice': f'{Count} claim(s) recorded; they await review.' if Count else 'No checkable claims were found in this source.'}
    except Analysis.AnalysisError as Problem:
        Query = {'Error': str(Problem)}
    return RedirectResponse(f'/Sources/View/{ID}?{urlencode(Query)}', status_code=303)


@App.post('/Channels/ClaimExtract/{ID}')
async def ChannelClaimExtract(request: Request, ID: int):
    Form = await request.form()

    def Work():
        Person = Database.ValueLoad('SELECT ChannelPerson FROM dbo.Channels WHERE ChannelID = ?', ID) or 0
        try:
            return f"/Jobs/View/{Analysis.ChannelClaimExtractCreate(ID, Form.get('DateStart') or '', Form.get('DateEnd') or '')}"
        except Analysis.AnalysisError as Problem:
            return f'/Persons/View/{Person}?{urlencode({"Notice": str(Problem)})}'

    return RedirectResponse(await run_in_threadpool(Work), status_code=303)


@App.get('/Reports/Create', response_class=HTMLResponse)
def ReportCreateView(request: Request, Person: int = 0, Type: int = Analysis.ReportTypeClaimAnalysis, Error: str = ''):
    Persons = Database.RowListLoad('SELECT PersonID, PersonLabel FROM dbo.Persons WHERE PersonID > 0 ORDER BY PersonLabel')
    Categories = Registry.ReferenceOptionListLoad(Registry.TableGet('Claims').ColumnGet('ClaimCategory'))
    return PageRender(request, 'ReportCreate.html', Title='New report', Persons=Persons, Categories=Categories, Person=Person, Type=Type,
                      Error=Error, Defaults=Analysis.InstructionDefault, AnalysisStatus=Analysis.StatusGet())


@App.post('/Reports/Create')
async def ReportCreate(request: Request):
    Form = await request.form()
    Type = int(Form.get('Type') or Analysis.ReportTypeClaimAnalysis)
    Parameters = {'Person': int(Form.get('Person') or 0), 'Category': int(Form.get('Category') or 0),
                  'DateStart': Form.get('DateStart') or '', 'DateEnd': Form.get('DateEnd') or '',
                  'ConfirmedOnly': Form.get('ConfirmedOnly') is not None, 'Instruction': (Form.get('Instruction') or '').strip()}
    if Type == Analysis.ReportTypePersonVerdict and not Parameters['Person']:
        return RedirectResponse(f'/Reports/Create?{urlencode({"Type": Type, "Error": "Choose the person the verdict is about."})}', status_code=303)
    try:
        ReportID = await run_in_threadpool(Analysis.ReportCreate, Type, Parameters)
    except Analysis.AnalysisError as Problem:
        return RedirectResponse(f'/Reports/Create?{urlencode({"Type": Type, "Person": Parameters["Person"], "Error": str(Problem)})}', status_code=303)
    return RedirectResponse(f'/Reports/View/{ReportID}', status_code=303)


@App.get('/Reports/View/{ID}', response_class=HTMLResponse)
def ReportView(request: Request, ID: int):
    Report = Database.RowLoad(
        'SELECT r.*, st.StatusLabel, t.TypeLabel, p.PersonLabel FROM dbo.Reports r '
        'LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = r.ReportStatus LEFT OUTER JOIN dbo.Types t ON t.TypeID = r.ReportType '
        'LEFT OUTER JOIN dbo.Persons p ON p.PersonID = r.ReportPerson WHERE r.ReportID = ? AND r.ReportID > 0', ID)
    if Report is None:
        return PageRender(request, 'Message.html', Title='Not found', Message='That report does not exist.')
    Dimensions = Database.RowListLoad(
        'SELECT d.DimensionLabel, d.DimensionDescription, rd.ReportDimensionScore, rd.ReportDimensionClaimCount, rd.ReportDimensionRationale, s.ScoreLabel '
        'FROM dbo.ReportDimensions rd LEFT OUTER JOIN dbo.Dimensions d ON d.DimensionID = rd.ReportDimensionDimension '
        'LEFT OUTER JOIN dbo.Scores s ON s.ScoreID = rd.ReportDimensionScore WHERE rd.ReportDimensionReport = ? ORDER BY d.DimensionOrder', ID)
    return PageRender(request, 'ReportView.html', Title=Report['ReportLabel'], Report=Report, Dimensions=Dimensions,
                      IsActive=Report['ReportStatus'] == Analysis.ReportStatusQueued)


# ---------------------------------------------------------------------------------------------
# Assertion review: quote, evidence, verdict
# ---------------------------------------------------------------------------------------------

@App.get('/SourceClaims/View/{ID}', response_class=HTMLResponse)
def SourceClaimView(request: Request, ID: int, Notice: str = '', Error: str = ''):
    Claim = Database.RowLoad(
        'SELECT sc.*, t.TypeLabel, st.StatusLabel, part.TypeLabel AS PartLabel, p.PersonLabel, cer.ClaimCertaintyLabel, tf.ClaimTimeframeLabel, '
        's.SourceLabel, s.SourceURL, s.SourceDatePublished, sty.SourceTypeLabel, ch.ChannelLabel, ch.ChannelPlatform, pl.PlatformLabel, '
        'c.ClaimLabel, c.ClaimStatement, c.ClaimCriteria, cat.CategoryLabel, v.ClaimValenceLabel, m.SourceClaimLabel AS MasterLabel '
        'FROM dbo.SourceClaims sc '
        'LEFT OUTER JOIN dbo.Types t ON t.TypeID = sc.SourceClaimType LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = sc.SourceClaimStatus '
        'LEFT OUTER JOIN dbo.Types part ON part.TypeID = sc.SourceClaimPart LEFT OUTER JOIN dbo.Persons p ON p.PersonID = sc.SourceClaimPerson '
        'LEFT OUTER JOIN dbo.ClaimCertainties cer ON cer.ClaimCertaintyID = sc.SourceClaimCertainty '
        'LEFT OUTER JOIN dbo.ClaimTimeframes tf ON tf.ClaimTimeframeID = sc.SourceClaimTimeframe '
        'LEFT OUTER JOIN dbo.Sources s ON s.SourceID = sc.SourceClaimSource LEFT OUTER JOIN dbo.SourceTypes sty ON sty.SourceTypeID = s.SourceType '
        'LEFT OUTER JOIN dbo.Channels ch ON ch.ChannelID = s.SourceChannel LEFT OUTER JOIN dbo.Platforms pl ON pl.PlatformID = ch.ChannelPlatform '
        'LEFT OUTER JOIN dbo.Claims c ON c.ClaimID = sc.SourceClaimClaim LEFT OUTER JOIN dbo.Categories cat ON cat.CategoryID = c.ClaimCategory '
        'LEFT OUTER JOIN dbo.ClaimValences v ON v.ClaimValenceID = c.ClaimValence '
        'LEFT OUTER JOIN dbo.SourceClaims m ON m.SourceClaimID = sc.SourceClaimMaster '
        'WHERE sc.SourceClaimID = ? AND sc.SourceClaimID > 0', ID)
    if Claim is None:
        return PageRender(request, 'Message.html', Title='Not found', Message='That assertion does not exist.')
    MomentURL = Claim['SourceURL'] or ''
    if Claim['ChannelPlatform'] == 1 and Claim['SourceClaimOffsetStart'] and MomentURL:
        MomentURL += f"&t={Claim['SourceClaimOffsetStart']}s"
    Tags = Database.RowListLoad(
        'SELECT ct.ClaimTypeLabel, g.ClaimTypeLabel AS GroupLabel FROM dbo.SourceClaimClaimTypes x '
        'LEFT OUTER JOIN dbo.ClaimTypes ct ON ct.ClaimTypeID = x.SCCTClaimType LEFT OUTER JOIN dbo.ClaimTypes g ON g.ClaimTypeID = ct.ClaimTypeMaster '
        'WHERE x.SCCTSourceClaim = ? ORDER BY ct.ClaimTypeMaster, ct.ClaimTypeOrder', ID)
    Assessments = Database.RowListLoad(
        'SELECT a.*, o.ClaimOutcomeLabel, g.ClaimOutcomeLabel AS GroupLabel, g.ClaimOutcomeID AS GroupID, sco.ScoreLabel, st.StatusLabel, t.TypeLabel '
        'FROM dbo.Assessments a LEFT OUTER JOIN dbo.ClaimOutcomes o ON o.ClaimOutcomeID = a.AssessmentOutcome '
        'LEFT OUTER JOIN dbo.ClaimOutcomes g ON g.ClaimOutcomeID = o.ClaimOutcomeMaster LEFT OUTER JOIN dbo.Scores sco ON sco.ScoreID = a.AssessmentScore '
        'LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = a.AssessmentStatus LEFT OUTER JOIN dbo.Types t ON t.TypeID = a.AssessmentType '
        'WHERE a.AssessmentSourceClaim = ? ORDER BY a.AssessmentIsCurrent DESC, a.AssessmentID DESC', ID)
    Citations = Database.RowListLoad(
        'SELECT cc.ClaimCitationID, cc.ClaimCitationExcerpt, cc.ClaimCitationNote, cc.ClaimCitationSourceClaim, stance.TypeLabel AS StanceLabel, '
        'cc.ClaimCitationType, c.CitationID, c.CitationLabel, c.CitationPublisher, c.CitationURL, c.CitationDatePublished, kind.TypeLabel AS KindLabel '
        'FROM dbo.ClaimCitations cc LEFT OUTER JOIN dbo.Citations c ON c.CitationID = cc.ClaimCitationCitation '
        'LEFT OUTER JOIN dbo.Types stance ON stance.TypeID = cc.ClaimCitationType LEFT OUTER JOIN dbo.Types kind ON kind.TypeID = c.CitationType '
        'WHERE cc.ClaimCitationSourceClaim = ? OR (cc.ClaimCitationSourceClaim = 0 AND cc.ClaimCitationClaim = ? AND cc.ClaimCitationClaim > 0) '
        'ORDER BY cc.ClaimCitationID', ID, Claim['SourceClaimClaim'])
    Related = Database.RowListLoad(
        "SELECT o.SourceClaimID, o.SourceClaimLabel, s.SourceDatePublished, t.TypeLabel AS RelationLabel, st.StatusLabel, r.SCRNote AS Note "
        'FROM dbo.SourceClaimRelations r LEFT OUTER JOIN dbo.SourceClaims o ON o.SourceClaimID = CASE WHEN r.SCRSourceClaim = ? THEN r.SCRSourceClaimRelated ELSE r.SCRSourceClaim END '
        'LEFT OUTER JOIN dbo.Sources s ON s.SourceID = o.SourceClaimSource LEFT OUTER JOIN dbo.Types t ON t.TypeID = r.SourceClaimRelationType '
        'LEFT OUTER JOIN dbo.Statuses st ON st.StatusID = r.SourceClaimRelationStatus '
        'WHERE (r.SCRSourceClaim = ? OR r.SCRSourceClaimRelated = ?) AND r.SourceClaimRelationStatus <> 1303 '
        "UNION ALL SELECT o.SourceClaimID, o.SourceClaimLabel, s.SourceDatePublished, t.TypeLabel + N' of this one', N'', N'' "
        'FROM dbo.SourceClaims o LEFT OUTER JOIN dbo.Sources s ON s.SourceID = o.SourceClaimSource LEFT OUTER JOIN dbo.Types t ON t.TypeID = o.SourceClaimType '
        'WHERE o.SourceClaimMaster = ? AND o.SourceClaimID > 0 ORDER BY SourceDatePublished', ID, ID, ID, ID)
    return PageRender(request, 'SourceClaimView.html', Title=Claim['SourceClaimLabel'], Claim=Claim, MomentURL=MomentURL, Tags=Tags,
                      Assessments=Assessments, Citations=Citations, Related=Related, Notice=Notice, Error=Error,
                      Today=date.today(), AnalysisStatus=Analysis.StatusGet())


@App.post('/SourceClaims/Review/{ID}')
async def SourceClaimReview(request: Request, ID: int):
    Form = await request.form()
    Status = {'Confirm': 502, 'Reject': 503, 'Reopen': 501}.get(Form.get('Action') or '')
    if Status:
        await run_in_threadpool(Database.RowEdit, 'SourceClaims', 'SourceClaimID', ID, {
            'SourceClaimStatus': Status, 'SourceClaimDateReviewed': datetime.utcnow(), 'SourceClaimUserReviewer': Config.UserAdministrator})
    return RedirectResponse(f'/SourceClaims/View/{ID}', status_code=303)


@App.post('/SourceClaims/Assess/{ID}')
def SourceClaimAssess(ID: int):
    try:
        Assessment.SourceClaimAssessRun(ID)
        Query = {'Notice': 'A verdict has been proposed from the evidence found. Read it, check the sources, then confirm or change it.'}
    except Analysis.AnalysisError as Problem:
        Query = {'Error': str(Problem)}
    return RedirectResponse(f'/SourceClaims/View/{ID}?{urlencode(Query)}', status_code=303)


@App.post('/Assessments/Review/{ID}')
async def AssessmentReview(request: Request, ID: int):
    Form = await request.form()
    Action = Form.get('Action') or ''

    def Work():
        Row = Database.RowLoad('SELECT AssessmentSourceClaim, AssessmentIsCurrent FROM dbo.Assessments WHERE AssessmentID = ?', ID)
        if Row is None:
            return 0
        if Action == 'Confirm' and Row['AssessmentIsCurrent']:
            Database.RowEdit('Assessments', 'AssessmentID', ID, {'AssessmentStatus': 602})
        elif Action == 'Discard':
            Database.RowEdit('Assessments', 'AssessmentID', ID, {'AssessmentStatus': 603, 'AssessmentIsCurrent': False})
        elif Action == 'Reopen':
            Database.RowEdit('Assessments', 'AssessmentID', ID, {'AssessmentStatus': 601})
        return Row['AssessmentSourceClaim']

    SourceClaimID = await run_in_threadpool(Work)
    return RedirectResponse(f'/SourceClaims/View/{SourceClaimID}' if SourceClaimID else '/Manage/Assessments', status_code=303)


@App.post('/Persons/Assess/{ID}')
def PersonAssess(ID: int):
    try:
        JobID = Assessment.PersonAssessCreate(ID)
    except Analysis.AnalysisError as Problem:
        return RedirectResponse(f'/Persons/View/{ID}?{urlencode({"Notice": str(Problem)})}', status_code=303)
    return RedirectResponse(f'/Jobs/View/{JobID}', status_code=303)
