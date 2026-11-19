"""Credentials and settings.

Secrets live in a text file OUTSIDE the repository (default: ..\\UPCredentials.txt next to the
project folder). The file is read on every request for a value, so keys can be replaced without
restarting the app. Each key line is "<label words> <value>"; the value is the last word.
"""
import os
import re
from pathlib import Path

CredentialsPath = Path(os.environ.get('UPCredentialsPath') or Path(__file__).resolve().parents[2] / 'UPCredentials.txt')

# Models and effort levels for the AI steps. Each can be overridden through an environment
# variable of the same name with the prefix UP (for example UPModelReport=claude-opus-5-5).
ModelExtract = os.environ.get('UPModelExtract', 'claude-sonnet-5-5')     # reading a source, quoting its claims
ModelAssess = os.environ.get('UPModelAssess', 'claude-sonnet-5-5')       # evidence search and proposed verdict
ModelReport = os.environ.get('UPModelReport', 'claude-sonnet-5-5')       # person verdicts and written reports
EffortExtract = os.environ.get('UPEffortExtract', 'medium')
EffortAssess = os.environ.get('UPEffortAssess', 'medium')
EffortReport = os.environ.get('UPEffortReport', 'high')

# Evidence search: the most web searches one verdict may use (searches are billed per use),
# and the most assertions one batch job works through.
AssessSearchCountMax = int(os.environ.get('UPAssessSearchCountMax', '8'))
AssessBatchCountMax = int(os.environ.get('UPAssessBatchCountMax', '25'))

# Fixed User IDs (see Database/Seed.sql).
UserSystem = 0
UserAdministrator = 1
UserAIAnalyst = 2


def CredentialLineListLoad() -> list[str]:
    if not CredentialsPath.exists():
        return []
    return CredentialsPath.read_text(encoding='utf-8', errors='replace').splitlines()


def CredentialListLoad() -> list[tuple[str, str]]:
    """(label, value) for every entry. Two line shapes are understood:
    'NAME = value' (value optionally quoted) and '<label words> <value>'."""
    Result = []
    for Line in CredentialLineListLoad():
        Match = re.match(r'\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*$', Line)
        if Match:
            Result.append((Match.group(1), Match.group(2).strip('"\'')))
            continue
        Words = Line.split()
        if len(Words) > 1:
            Result.append((' '.join(Words[:-1]), Words[-1]))
    return Result


def CredentialValueGet(LabelPattern: str, ValuePattern: str = '', Last: bool = False) -> str:
    """Value of the first (or last) entry whose label and value match the regular expressions."""
    Values = [Value for Label, Value in CredentialListLoad()
              if re.search(LabelPattern, Label, re.I) and re.match(ValuePattern, Value)]
    return (Values[-1] if Last else Values[0]) if Values else ''


def DatabaseConnectionStringGet() -> str:
    """Converts the ADO / OLE DB style 'DBUPData = "..."' entry into an ODBC connection string."""
    for Line in CredentialLineListLoad():
        Match = re.match(r'\s*DBUPData\s*=\s*"(.+)"', Line)
        if Match:
            Settings = {}
            for Part in Match.group(1).split(';'):
                if '=' in Part:
                    Name, Value = Part.split('=', 1)
                    Settings[Name.strip().lower()] = Value.strip()
            return (
                'DRIVER={ODBC Driver 18 for SQL Server};'
                f"SERVER={Settings.get('data source', '')};DATABASE={Settings.get('initial catalog', '')};"
                f"UID={Settings.get('user id', '')};PWD={{{Settings.get('password', '')}}};"
                'Encrypt=yes;TrustServerCertificate=yes;'
            )
    raise RuntimeError(f'No DBUPData entry found in {CredentialsPath}')


def YouTubeKeyGet() -> str:
    """A standard Google API key (they start with 'AIza'); the last one listed wins. Other Google
    credentials in the file (OAuth client IDs / secrets, 'AQ.' keys) do not work for YouTube data."""
    return CredentialValueGet(r'api key', r'AIza', Last=True)


def XBearerTokenGet() -> str:
    return CredentialValueGet(r'bearer')


def AnthropicKeyGet() -> str:
    """A regular Claude API key. Admin keys ('sk-ant-admin...') manage an organisation and cannot call models."""
    Key = os.environ.get('ANTHROPIC_API_KEY') or CredentialValueGet(r'anthropic|claude', r'sk-ant-(?!admin)')
    return '' if Key.startswith('sk-ant-admin') else Key


def AnthropicKeyIsAdmin() -> bool:
    return bool(CredentialValueGet(r'anthropic|claude', r'sk-ant-admin')) and not AnthropicKeyGet()
