"""Reads the old SQL Server database (read-only). Needs `pip install pyodbc` + Microsoft's ODBC driver."""

# Dates are converted to text ('1396-09-14') in SQL: the old database keeps JALALI dates inside date columns,
# and plain text is the same thing whether you run this from Python or export it from SSMS as CSV.
TLD_QUERY = """\
SELECT  t.TLDID, t.PersonnelID, t.DoseID, t.MeasureD, t.Uncertinty, t.DateID, t.Descriptions, t.JobType,
        CONVERT(varchar(10), d.Date1, 120) AS Date1,
        CONVERT(varchar(10), d.Date2, 120) AS Date2,
        d.NumberofTest, d.LabID,
        p.firstName, p.LastName, p.PNumber
FROM    [HealthPhysics].[dbo].[TLD]        AS t
JOIN    [HealthPhysics].[dbo].[DateD]      AS d ON d.DateID      = t.DateID
JOIN    [HealthPhysics].[dbo].[Personnels] AS p ON p.PersonnelID = t.PersonnelID
ORDER BY t.DateID, t.PersonnelID, t.DoseID;
"""

# Operation = PlaceofActivity.PlaceName, location = Center.Name + Address. Time-of-day is exported as text (hh:mi:ss).
ONLINE_QUERY = """\
SELECT  o.OnDoseID, o.PersonnelID,
        CONVERT(varchar(10), o.[DateTime], 120)  AS [DateTime],
        CONVERT(varchar(8),  o.DureofTime, 108)  AS DureofTime,
        o.Dose, o.PlaceID, pl.PlaceName,
        c.[Name] AS CenterName, c.[Address] AS CenterAddress,
        p.firstName, p.LastName, p.PNumber
FROM    [HealthPhysics].[dbo].[OnlineDose]       AS o
JOIN    [HealthPhysics].[dbo].[Personnels]       AS p  ON p.PersonnelID = o.PersonnelID
LEFT JOIN [HealthPhysics].[dbo].[PlaceofActivity] AS pl ON pl.PlaceID    = o.PlaceID
LEFT JOIN [HealthPhysics].[dbo].[Center]         AS c  ON c.CenterID     = pl.CenterID
ORDER BY o.[DateTime], o.PlaceID, o.OnDoseID;
"""

QUERIES = {"tld": TLD_QUERY, "online": ONLINE_QUERY}


def fetch(connection_string, query, timeout=30):
    """Run one SELECT and return a list of dicts with lower-case column names plus a 1-based 'row' number."""
    try:
        import pyodbc
    except ImportError as e:                                     # pragma: no cover
        raise RuntimeError("pyodbc is not installed. Run: pip install pyodbc "
                           "(and install 'ODBC Driver 17 (or 18) for SQL Server')") from e
    connection = pyodbc.connect(connection_string, timeout=timeout, readonly=True)
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        columns = [c[0].lower() for c in cursor.description]
        return [{**dict(zip(columns, values)), "row": n} for n, values in enumerate(cursor.fetchall(), 1)]
    finally:
        connection.close()
