-- Old system (HealthPhysics) -> flat TLD export for  Operation control > TLD reports > Import from the old system.
-- Run in SSMS, then: right-click the result grid > Save Results As... > CSV (UTF-8 if offered).
-- Read-only: it only SELECTs. Date1/Date2 are Jalali dates kept in date columns; they are exported as text.
SELECT  t.TLDID, t.PersonnelID, t.DoseID, t.MeasureD, t.Uncertinty, t.DateID, t.Descriptions, t.JobType,
        CONVERT(varchar(10), d.Date1, 120) AS Date1,
        CONVERT(varchar(10), d.Date2, 120) AS Date2,
        d.NumberofTest, d.LabID,
        p.firstName, p.LastName, p.PNumber
FROM    [HealthPhysics].[dbo].[TLD]        AS t
JOIN    [HealthPhysics].[dbo].[DateD]      AS d ON d.DateID      = t.DateID
JOIN    [HealthPhysics].[dbo].[Personnels] AS p ON p.PersonnelID = t.PersonnelID
ORDER BY t.DateID, t.PersonnelID, t.DoseID;
