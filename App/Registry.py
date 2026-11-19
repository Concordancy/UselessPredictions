"""Describes every table so that one generic set of pages can manage all of them.

Column facts (type, length, nullable, identity, computed) are read from the database catalog.
What the catalog cannot know - which table a reference column points to - is declared here.
"""
from dataclasses import dataclass, field
from functools import lru_cache

from . import Database

# Menu groups: (group label, [(table, list columns)]). List columns = what the list page shows.
TableGroupList = [
    ('People', [
        ('Persons', ['PersonLabel', 'PersonType', 'PersonStatus', 'PersonCategory', 'PersonCountry', 'PersonDateCreated']),
        ('Channels', ['ChannelLabel', 'ChannelPerson', 'ChannelPlatform', 'ChannelStatus', 'ChannelHandle', 'ChannelFollowerCount', 'ChannelDateSynced']),
    ]),
    ('Content', [
        ('Sources', ['SourceLabel', 'SourceType', 'SourceStatus', 'SourceChannel', 'SourceDatePublished', 'SourceViewCount']),
        ('SourceContents', ['SourceContentSource', 'SourceContentType', 'SourceContentLanguage', 'SourceContentLength', 'SourceContentOrigin', 'SourceContentDateFetched']),
    ]),
    ('Claims', [
        ('SourceClaims', ['SourceClaimLabel', 'SourceClaimPerson', 'SourceClaimSource', 'SourceClaimClaim', 'SourceClaimType', 'SourceClaimStatus', 'SourceClaimDueDateMin', 'SourceClaimDueDateMax']),
        ('Claims', ['ClaimLabel', 'ClaimType', 'ClaimStatus', 'ClaimMaster', 'ClaimCategory', 'ClaimValence']),
        ('SourceClaimClaimTypes', ['SCCTSourceClaim', 'SCCTClaimType']),
        ('SourceClaimRelations', ['SCRSourceClaim', 'SCRSourceClaimRelated', 'SourceClaimRelationType', 'SourceClaimRelationStatus', 'SCRNote']),
    ]),
    ('Verdicts', [
        ('Assessments', ['AssessmentLabel', 'AssessmentSourceClaim', 'AssessmentOutcome', 'AssessmentScore', 'AssessmentStatus', 'AssessmentIsCurrent', 'AssessmentDateAssessed']),
        ('Citations', ['CitationLabel', 'CitationType', 'CitationPublisher', 'CitationDatePublished', 'CitationURL']),
        ('ClaimCitations', ['ClaimCitationClaim', 'ClaimCitationSourceClaim', 'ClaimCitationCitation', 'ClaimCitationType', 'ClaimCitationExcerpt']),
        ('Reports', ['ReportLabel', 'ReportType', 'ReportStatus', 'ReportPerson', 'ReportClaimCount', 'ReportModel', 'ReportDateCreated']),
        ('ReportDimensions', ['ReportDimensionReport', 'ReportDimensionDimension', 'ReportDimensionScore', 'ReportDimensionMetric', 'ReportDimensionClaimCount']),
        ('ReportSourceClaims', ['RSCReport', 'RSCSourceClaim']),
        ('ReportSources', ['ReportSourceReport', 'ReportSourceSource']),
    ]),
    ('Lookups', [
        ('Platforms', ['PlatformLabel', 'PlatformType', 'PlatformStatus', 'PlatformURL', 'PlatformHasAPI']),
        ('SourceTypes', ['SourceTypeLabel', 'SourceTypeDescription', 'SourceTypeIsTimed']),
        ('ClaimTypes', ['ClaimTypeLabel', 'ClaimTypeMaster', 'ClaimTypeDescription']),
        ('ClaimValences', ['ClaimValenceLabel', 'ClaimValenceValue', 'ClaimValenceDescription']),
        ('ClaimCertainties', ['ClaimCertaintyLabel', 'ClaimCertaintyValue', 'ClaimCertaintyDescription']),
        ('ClaimTimeframes', ['ClaimTimeframeLabel', 'ClaimTimeframeIsExplicit', 'ClaimTimeframeMonthsMin', 'ClaimTimeframeMonthsMax', 'ClaimTimeframeDescription']),
        ('ClaimOutcomes', ['ClaimOutcomeLabel', 'ClaimOutcomeMaster', 'ClaimOutcomeIsCounted', 'ClaimOutcomeDescription']),
        ('Scores', ['ScoreLabel', 'ScoreDescription']),
        ('Dimensions', ['DimensionLabel', 'DimensionDescription']),
        ('Categories', ['CategoryLabel', 'CategoryMaster']),
    ]),
    ('System', [
        ('Jobs', ['JobLabel', 'JobType', 'JobStatus', 'JobChannel', 'JobItemCountFound', 'JobItemCountAdded', 'JobDateCreated']),
        ('Types', ['TypeClass', 'TypeLabel', 'TypeDescription']),
        ('Statuses', ['StatusClass', 'StatusLabel', 'StatusDescription']),
        ('Users', ['UserLabel', 'UserType', 'UserStatus']),
    ]),
]

# Reference columns: column -> (table it points to, Type/Status class filter or None).
ReferenceMap = {
    'UserType': ('Types', 'User'), 'UserStatus': ('Statuses', 'User'),
    'TypeStatus': ('Statuses', 'Lookup'),
    'CategoryStatus': ('Statuses', 'Lookup'), 'CategoryMaster': ('Categories', None),
    'PlatformType': ('Types', 'Platform'), 'PlatformStatus': ('Statuses', 'Lookup'),
    'SourceTypeStatus': ('Statuses', 'Lookup'),
    'ClaimTypeStatus': ('Statuses', 'Lookup'), 'ClaimTypeMaster': ('ClaimTypes', None),
    'ClaimOutcomeMaster': ('ClaimOutcomes', None),
    'DimensionStatus': ('Statuses', 'Lookup'),
    'PersonType': ('Types', 'Person'), 'PersonStatus': ('Statuses', 'Person'), 'PersonMaster': ('Persons', None),
    'PersonCategory': ('Categories', None), 'PersonUserCreator': ('Users', None),
    'ChannelType': ('Types', 'Channel'), 'ChannelStatus': ('Statuses', 'Channel'), 'ChannelPerson': ('Persons', None),
    'ChannelPlatform': ('Platforms', None), 'ChannelUserCreator': ('Users', None),
    'JobType': ('Types', 'Job'), 'JobStatus': ('Statuses', 'Job'), 'JobMaster': ('Jobs', None), 'JobPerson': ('Persons', None),
    'JobChannel': ('Channels', None), 'JobPlatform': ('Platforms', None), 'JobUserCreator': ('Users', None),
    'SourceType': ('SourceTypes', None), 'SourceStatus': ('Statuses', 'Source'), 'SourceMaster': ('Sources', None),
    'SourceChannel': ('Channels', None), 'SourceJob': ('Jobs', None), 'SourceUserCreator': ('Users', None),
    'SourceContentType': ('Types', 'SourceContent'), 'SourceContentSource': ('Sources', None),
    'ClaimType': ('ClaimTypes', None), 'ClaimStatus': ('Statuses', 'Claim'), 'ClaimMaster': ('Claims', None),
    'ClaimCategory': ('Categories', None), 'ClaimValence': ('ClaimValences', None), 'ClaimUserCreator': ('Users', None),
    'SourceClaimType': ('Types', 'SourceClaim'), 'SourceClaimStatus': ('Statuses', 'SourceClaim'),
    'SourceClaimMaster': ('SourceClaims', None), 'SourceClaimSource': ('Sources', None), 'SourceClaimClaim': ('Claims', None),
    'SourceClaimPerson': ('Persons', None), 'SourceClaimPart': ('Types', 'SourcePart'),
    'SourceClaimCertainty': ('ClaimCertainties', None), 'SourceClaimTimeframe': ('ClaimTimeframes', None),
    'SourceClaimUserCreator': ('Users', None), 'SourceClaimUserReviewer': ('Users', None),
    'SCCTSourceClaim': ('SourceClaims', None), 'SCCTClaimType': ('ClaimTypes', None),
    'SourceClaimRelationType': ('Types', 'SourceClaimRelation'), 'SourceClaimRelationStatus': ('Statuses', 'SourceClaimRelation'),
    'SCRSourceClaim': ('SourceClaims', None), 'SCRSourceClaimRelated': ('SourceClaims', None), 'SCRUserCreator': ('Users', None),
    'AssessmentType': ('Types', 'Assessment'), 'AssessmentStatus': ('Statuses', 'Assessment'),
    'AssessmentSourceClaim': ('SourceClaims', None), 'AssessmentOutcome': ('ClaimOutcomes', None),
    'AssessmentScore': ('Scores', None), 'AssessmentUserCreator': ('Users', None),
    'CitationType': ('Types', 'Citation'), 'CitationStatus': ('Statuses', 'Citation'), 'CitationUserCreator': ('Users', None),
    'ClaimCitationType': ('Types', 'ClaimCitation'), 'ClaimCitationClaim': ('Claims', None),
    'ClaimCitationSourceClaim': ('SourceClaims', None), 'ClaimCitationCitation': ('Citations', None),
    'ClaimCitationUserCreator': ('Users', None),
    'ReportType': ('Types', 'Report'), 'ReportStatus': ('Statuses', 'Report'), 'ReportCategory': ('Categories', None),
    'ReportPerson': ('Persons', None), 'ReportChannel': ('Channels', None), 'ReportJob': ('Jobs', None),
    'ReportUserCreator': ('Users', None),
    'ReportDimensionReport': ('Reports', None), 'ReportDimensionDimension': ('Dimensions', None),
    'ReportDimensionScore': ('Scores', None),
    'RSCReport': ('Reports', None), 'RSCSourceClaim': ('SourceClaims', None),
    'ReportSourceReport': ('Reports', None), 'ReportSourceSource': ('Sources', None),
}

# A reference shown as a dropdown up to this many rows; beyond that as an ID box with the label beside it.
ReferenceOptionCountMax = 400


@dataclass
class ColumnInfo:
    Name: str
    TypeName: str
    Length: int            # characters; -1 = unlimited
    IsNullable: bool
    IsIdentity: bool
    IsComputed: bool
    Kind: str = 'Text'     # Reference, Flag, Number, Decimal, Date, DateTime, Text, TextLong, Binary
    Reference: tuple | None = None

    @property
    def IsEditable(self) -> bool:
        return not (self.IsIdentity or self.IsComputed or self.Kind == 'Binary')


@dataclass
class TableInfo:
    Table: str
    Group: str
    ListColumns: list
    KeyColumn: str = ''
    LabelColumn: str = ''
    MasterColumn: str = ''
    HasZeroRow: bool = True     # row 0 is the "none" placeholder (hidden from lists)
    Columns: list = field(default_factory=list)

    def ColumnGet(self, Name: str) -> ColumnInfo | None:
        return next((C for C in self.Columns if C.Name == Name), None)


def ColumnKindGet(TypeName: str, Length: int) -> str:
    if TypeName == 'bit':
        return 'Flag'
    if TypeName in ('int', 'smallint', 'bigint', 'tinyint'):
        return 'Number'
    if TypeName in ('decimal', 'numeric', 'float', 'real'):
        return 'Decimal'
    if TypeName == 'date':
        return 'Date'
    if TypeName.startswith('datetime'):
        return 'DateTime'
    if TypeName in ('varbinary', 'binary'):
        return 'Binary'
    if TypeName in ('ntext', 'text') or Length == -1 or Length > 400:
        return 'TextLong'
    return 'Text'


@lru_cache(maxsize=1)
def RegistryLoad() -> dict:
    """Table name -> TableInfo, in menu order."""
    Registry = {}
    for Group, Tables in TableGroupList:
        for Table, ListColumns in Tables:
            Registry[Table] = TableInfo(Table=Table, Group=Group, ListColumns=ListColumns)
    Rows = Database.RowListLoad(
        "SELECT t.name AS TableName, c.name AS ColumnName, ty.name AS TypeName, c.max_length AS ByteLength, "
        "c.is_nullable AS IsNullable, c.is_identity AS IsIdentity, c.is_computed AS IsComputed, "
        "CASE WHEN ic.column_id IS NULL THEN 0 ELSE 1 END AS IsKey "
        "FROM sys.tables t "
        "INNER JOIN sys.columns c ON c.object_id = t.object_id "
        "INNER JOIN sys.types ty ON ty.user_type_id = c.user_type_id "
        "LEFT OUTER JOIN sys.indexes i ON i.object_id = t.object_id AND i.is_primary_key = 1 "
        "LEFT OUTER JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.column_id = c.column_id "
        "ORDER BY t.name, c.column_id")
    for Row in Rows:
        Info = Registry.get(Row['TableName'])
        if Info is None:
            continue
        Length = Row['ByteLength']
        if Row['TypeName'] in ('nvarchar', 'nchar') and Length > 0:
            Length //= 2
        if Row['TypeName'] in ('ntext', 'text'):
            Length = -1
        Column = ColumnInfo(Name=Row['ColumnName'], TypeName=Row['TypeName'], Length=Length,
                            IsNullable=bool(Row['IsNullable']), IsIdentity=bool(Row['IsIdentity']),
                            IsComputed=bool(Row['IsComputed']))
        Column.Kind = ColumnKindGet(Column.TypeName, Column.Length)
        if Column.Name in ReferenceMap:
            Column.Kind, Column.Reference = 'Reference', ReferenceMap[Column.Name]
        Info.Columns.append(Column)
        if Row['IsKey']:
            Info.KeyColumn = Column.Name
        elif Column.Name.endswith('Label') and not Info.LabelColumn:
            Info.LabelColumn = Column.Name
        elif Column.Name.endswith('Master') and Column.Reference and Column.Reference[0] == Info.Table:
            Info.MasterColumn = Column.Name
    Registry['Scores'].HasZeroRow = False       # 0 is a real score
    return Registry


def TableGet(Table: str) -> TableInfo:
    Info = RegistryLoad().get(Table)
    if Info is None or not Info.Columns:
        raise KeyError(Table)
    return Info


def LabelSqlGet(Info: TableInfo, Alias: str = 'x') -> str:
    """SQL expression for a row's display label; hierarchical tables show 'Parent > Child'."""
    return f'{Alias}.[{Info.LabelColumn}]'


def ReferenceOptionListLoad(Column: ColumnInfo, Current=None) -> list | None:
    """(ID, label) choices for a reference column, or None when the table is too large for a dropdown."""
    Table, Class = Column.Reference
    Info = TableGet(Table)
    Where, Parameters = '', []
    if Class is not None:
        Where = f"WHERE x.[{Table[:-2] if Table == 'Statuses' else Table[:-1]}Class] IN ('', ?)"
        Parameters = [Class]
    elif Database.ValueLoad(f'SELECT COUNT(*) FROM dbo.[{Table}]') > ReferenceOptionCountMax:
        return None
    Order = f'x.[{Info.KeyColumn}]'
    if Table in ('Types', 'Statuses'):
        Order = f"x.[{Table[:-2] if Table == 'Statuses' else Table[:-1]}Order], x.[{Info.KeyColumn}]"
    if Info.MasterColumn:
        Sql = (f"SELECT x.[{Info.KeyColumn}] AS OptionID, CASE WHEN m.[{Info.KeyColumn}] IS NULL OR x.[{Info.MasterColumn}] = 0 "
               f"THEN x.[{Info.LabelColumn}] ELSE m.[{Info.LabelColumn}] + N' > ' + x.[{Info.LabelColumn}] END AS OptionLabel "
               f"FROM dbo.[{Table}] x LEFT OUTER JOIN dbo.[{Table}] m ON m.[{Info.KeyColumn}] = x.[{Info.MasterColumn}] "
               f"AND x.[{Info.MasterColumn}] <> x.[{Info.KeyColumn}] {Where} "
               f"ORDER BY CASE WHEN x.[{Info.MasterColumn}] = 0 THEN x.[{Info.KeyColumn}] ELSE x.[{Info.MasterColumn}] END, "
               f"CASE WHEN x.[{Info.MasterColumn}] = 0 THEN 0 ELSE 1 END, x.[{Info.KeyColumn}]")
    else:
        Sql = (f"SELECT x.[{Info.KeyColumn}] AS OptionID, x.[{Info.LabelColumn}] AS OptionLabel "
               f"FROM dbo.[{Table}] x {Where} ORDER BY {Order}")
    Options = [(Row['OptionID'], Row['OptionLabel']) for Row in Database.RowListLoad(Sql, *Parameters)]
    if Table == 'Scores':
        Options = [(ID, f'{ID:+d}  {Label}' if ID else f' 0  {Label}') for ID, Label in Options]
    if Current is not None and Current not in [ID for ID, _ in Options]:
        Options.append((Current, f'#{Current}'))
    return Options


def ReferenceLabelMapLoad(Column: ColumnInfo, IDs) -> dict:
    """ID -> label for the given IDs of the table a reference column points to."""
    IDs = sorted({ID for ID in IDs if ID is not None})
    if not IDs:
        return {}
    Info = TableGet(Column.Reference[0])
    Rows = Database.RowListLoad(
        f"SELECT x.[{Info.KeyColumn}] AS OptionID, x.[{Info.LabelColumn}] AS OptionLabel FROM dbo.[{Info.Table}] x "
        f"WHERE x.[{Info.KeyColumn}] IN ({', '.join('?' for _ in IDs)})", *IDs)
    return {Row['OptionID']: Row['OptionLabel'] for Row in Rows}


def ReferenceReverseListGet(Table: str) -> list:
    """(other table, column) pairs that point at this table: used for 'related records' links."""
    Result = []
    for Info in RegistryLoad().values():
        for Column in Info.Columns:
            if Column.Reference and Column.Reference[0] == Table and Table not in ('Types', 'Statuses', 'Users'):
                Result.append((Info.Table, Column.Name))
    return Result
