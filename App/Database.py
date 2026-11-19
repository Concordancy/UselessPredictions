"""Thin data access layer over pyodbc. No ORM: SQL stays visible and follows the naming conventions.

Table and column names passed to the Row* helpers must come from the Registry (never from user
input); all values travel as parameters.
"""
from contextlib import contextmanager

import pyodbc

from . import Config

pyodbc.pooling = True


@contextmanager
def ConnectionOpen():
    Connection = pyodbc.connect(Config.DatabaseConnectionStringGet(), timeout=15)
    try:
        yield Connection
        Connection.commit()
    except Exception:
        Connection.rollback()
        raise
    finally:
        Connection.close()


def RowListLoad(Sql: str, *Parameters) -> list[dict]:
    with ConnectionOpen() as Connection:
        Cursor = Connection.execute(Sql, *Parameters)
        Columns = [Column[0] for Column in Cursor.description]
        return [dict(zip(Columns, Row)) for Row in Cursor.fetchall()]


def RowLoad(Sql: str, *Parameters) -> dict | None:
    Rows = RowListLoad(Sql, *Parameters)
    return Rows[0] if Rows else None


def ValueLoad(Sql: str, *Parameters):
    with ConnectionOpen() as Connection:
        Row = Connection.execute(Sql, *Parameters).fetchone()
        return Row[0] if Row else None


def StatementExecute(Sql: str, *Parameters) -> int:
    with ConnectionOpen() as Connection:
        return Connection.execute(Sql, *Parameters).rowcount


def RowAdd(Table: str, KeyColumn: str, Values: dict) -> int:
    """Inserts one row and returns its new ID."""
    Columns = list(Values)
    if Columns:
        Sql = (f"INSERT INTO dbo.[{Table}] ({', '.join(f'[{C}]' for C in Columns)}) "
               f"OUTPUT INSERTED.[{KeyColumn}] VALUES ({', '.join('?' for _ in Columns)})")
    else:
        Sql = f'INSERT INTO dbo.[{Table}] OUTPUT INSERTED.[{KeyColumn}] DEFAULT VALUES'
    with ConnectionOpen() as Connection:
        return Connection.execute(Sql, *[Values[C] for C in Columns]).fetchone()[0]


def RowEdit(Table: str, KeyColumn: str, KeyValue, Values: dict) -> int:
    if not Values:
        return 0
    Columns = list(Values)
    Sql = f"UPDATE dbo.[{Table}] SET {', '.join(f'[{C}] = ?' for C in Columns)} WHERE [{KeyColumn}] = ?"
    return StatementExecute(Sql, *[Values[C] for C in Columns], KeyValue)


def RowDelete(Table: str, KeyColumn: str, KeyValue) -> int:
    return StatementExecute(f'DELETE FROM dbo.[{Table}] WHERE [{KeyColumn}] = ?', KeyValue)
