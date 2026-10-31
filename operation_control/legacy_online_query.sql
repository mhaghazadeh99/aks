-- Old system (HealthPhysics) -> flat online-dose export for  Operation control > Operation dose records > Import from the old system.
-- Run in SSMS, then: right-click the result grid > Save Results As... > CSV (UTF-8 if offered). Read-only.
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
