"""Managing canonical claims: merging duplicates under a master, changing them in bulk, deleting them.

A master claim and the claims merged into it (ClaimMaster = the master's ID) count as ONE distinct
claim. Merging keeps the hierarchy one level deep. Assertions stay attached to the claim they were
recorded under, so a merge can always be undone.
"""
from . import Database

AssertionTableList = [      # (table, column that points at an assertion) - rows to remove along with an assertion
    ('Assessments', 'AssessmentSourceClaim'), ('ClaimCitations', 'ClaimCitationSourceClaim'),
    ('SourceClaimClaimTypes', 'SCCTSourceClaim'), ('SourceClaimRelations', 'SCRSourceClaim'),
    ('SourceClaimRelations', 'SCRSourceClaimRelated'), ('ReportSourceClaims', 'RSCSourceClaim')]


def IdListGet(Values) -> list:
    return sorted({int(Value) for Value in Values if int(Value) > 0})


def MarkGet(IDs: list) -> str:
    return ', '.join('?' for _ in IDs)


def ClaimFamilyListGet(ClaimIDs, IncludeChildren: bool = True) -> list:
    """The given claims plus, when asked, every claim merged into one of them."""
    IDs = IdListGet(ClaimIDs)
    if not IDs or not IncludeChildren:
        return IDs
    Children = [Row['ClaimID'] for Row in Database.RowListLoad(
        f'SELECT ClaimID FROM dbo.Claims WHERE ClaimMaster IN ({MarkGet(IDs)})', *IDs)]
    return sorted(set(IDs) | set(Children))


def ClaimMergeRun(ClaimIDs, Master: int) -> int:
    """Makes Master the master of the other given claims (and of anything merged into those).
    Returns how many claims now sit under the master because of this call."""
    IDs = IdListGet(ClaimIDs)
    Others = [ID for ID in IDs if ID != Master]
    if Master <= 0 or not Others or not Database.ValueLoad('SELECT COUNT(*) FROM dbo.Claims WHERE ClaimID = ?', Master):
        return 0
    Database.StatementExecute('UPDATE dbo.Claims SET ClaimMaster = 0, ClaimDateEdited = SYSUTCDATETIME() WHERE ClaimID = ? AND ClaimMaster <> 0', Master)
    return Database.StatementExecute(
        f'UPDATE dbo.Claims SET ClaimMaster = ?, ClaimDateEdited = SYSUTCDATETIME() '
        f'WHERE ClaimID <> ? AND ClaimID > 0 AND (ClaimID IN ({MarkGet(Others)}) OR ClaimMaster IN ({MarkGet(Others)}))',
        Master, Master, *Others, *Others)


def ClaimUnmergeRun(ClaimIDs, IncludeChildren: bool = True) -> int:
    """Makes the given claims independent again; with IncludeChildren also releases what was merged into them."""
    IDs = IdListGet(ClaimIDs)
    if not IDs:
        return 0
    Where = f'ClaimID IN ({MarkGet(IDs)})' + (f' OR ClaimMaster IN ({MarkGet(IDs)})' if IncludeChildren else '')
    return Database.StatementExecute(
        f'UPDATE dbo.Claims SET ClaimMaster = 0, ClaimDateEdited = SYSUTCDATETIME() WHERE ClaimMaster <> 0 AND ({Where})',
        *IDs, *(IDs if IncludeChildren else []))


def ClaimEditRun(ClaimIDs, Values: dict) -> int:
    """Sets ClaimType / ClaimValence / ClaimStatus (whichever are given) on exactly the given claims."""
    IDs = IdListGet(ClaimIDs)
    Values = {Name: int(Value) for Name, Value in Values.items() if Name in ('ClaimType', 'ClaimValence', 'ClaimStatus') and Value not in (None, '')}
    if not IDs or not Values:
        return 0
    return Database.StatementExecute(
        f"UPDATE dbo.Claims SET {', '.join(f'[{Name}] = ?' for Name in Values)}, ClaimDateEdited = SYSUTCDATETIME() WHERE ClaimID IN ({MarkGet(IDs)})",
        *Values.values(), *IDs)


def ClaimDeleteRun(ClaimIDs) -> tuple[int, int]:
    """Deletes exactly the given claims together with their assertions, and those assertions'
    verdicts, evidence links and tags. Claims merged into a deleted claim but not deleted
    themselves become independent. Returns (claims deleted, assertions deleted)."""
    IDs = IdListGet(ClaimIDs)
    if not IDs:
        return 0, 0
    Marks = MarkGet(IDs)
    Picked = f'SELECT sc.SourceClaimID FROM dbo.SourceClaims sc WHERE sc.SourceClaimClaim IN ({Marks})'
    with Database.ConnectionOpen() as Connection:       # one transaction: all of it or none
        for Table, Column in AssertionTableList:
            Connection.execute(f'DELETE FROM dbo.[{Table}] WHERE [{Column}] IN ({Picked})', *IDs)
        Connection.execute(f'DELETE FROM dbo.ClaimCitations WHERE ClaimCitationClaim IN ({Marks})', *IDs)
        Connection.execute(f'UPDATE dbo.SourceClaims SET SourceClaimMaster = 0 WHERE SourceClaimMaster IN ({Picked})', *IDs)
        Assertions = Connection.execute(f'DELETE FROM dbo.SourceClaims WHERE SourceClaimClaim IN ({Marks})', *IDs).rowcount
        Connection.execute(f'UPDATE dbo.Claims SET ClaimMaster = 0 WHERE ClaimMaster IN ({Marks}) AND ClaimID NOT IN ({Marks})', *IDs, *IDs)
        Claims = Connection.execute(f'DELETE FROM dbo.Claims WHERE ClaimID IN ({Marks})', *IDs).rowcount
    return Claims, Assertions
