-- Deterministic synthetic data (same rows on every machine): 400 customers, 12 services,
-- 24 months of billing. Values are derived from CRC32 hashes instead of RAND() so the
-- demo questions in the README always give the same answers.
USE telecom_dw;

SET SESSION cte_max_recursion_depth = 10000;

-- Services: 4 types x 3 plans
INSERT INTO dimservice (ServiceID, ServiceType, PlanType)
SELECT (t.n - 1) * 3 + p.n,
       ELT(t.n, 'Mobile', 'Internet', 'TV', 'Landline'),
       ELT(p.n, 'Basic', 'Standard', 'Premium')
FROM (SELECT 1 n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4) t
CROSS JOIN (SELECT 1 n UNION ALL SELECT 2 UNION ALL SELECT 3) p;

-- Dates: first day of each month, Jan 2024 - Dec 2025
INSERT INTO dimdate (DateID, FullDate, Day, Month, Quarter, Year)
WITH RECURSIVE months AS (
    SELECT DATE('2024-01-01') AS d
    UNION ALL
    SELECT d + INTERVAL 1 MONTH FROM months WHERE d < '2025-12-01'
)
SELECT CAST(DATE_FORMAT(d, '%Y%m%d') AS UNSIGNED), d, DAY(d), MONTH(d), QUARTER(d), YEAR(d)
FROM months;

-- Customers
INSERT INTO dimcustomer (CustomerID, Age, Gender, City, Region, ContractType, JoinDate)
WITH RECURSIVE ids AS (
    SELECT 1 AS id UNION ALL SELECT id + 1 FROM ids WHERE id < 400
),
h AS (
    SELECT id,
           CRC32(CONCAT('age', id))      AS h_age,
           CRC32(CONCAT('city', id))     AS h_city,
           CRC32(CONCAT('contract', id)) AS h_contract,
           CRC32(CONCAT('join', id))     AS h_join,
           CRC32(CONCAT('gender', id))   AS h_gender
    FROM ids
)
SELECT id,
       18 + MOD(h_age, 58),
       IF(MOD(h_gender, 2) = 0, 'Female', 'Male'),
       ELT(1 + MOD(h_city, 8), 'Nablus', 'Ramallah', 'Hebron', 'Jenin',
                               'Bethlehem', 'Tulkarm', 'Jericho', 'Qalqilya'),
       ELT(1 + MOD(h_city, 8), 'North', 'Center', 'South', 'North',
                               'South', 'North', 'Center', 'North'),
       CASE WHEN MOD(h_contract, 10) < 5 THEN 'Monthly'
            WHEN MOD(h_contract, 10) < 8 THEN 'One year'
            ELSE 'Two year' END,
       DATE('2019-01-01') + INTERVAL MOD(h_join, 1800) DAY
FROM h;

-- Billing: one bill per customer per month for their main service
INSERT INTO factbilling (BillingID, CustomerID, DateID, ServiceID, UsageMinutes, BillAmount,
                         PaymentStatus, LatePaymentFlag, PaymentDelayDays)
SELECT ROW_NUMBER() OVER (ORDER BY d.DateID, c.CustomerID),
       c.CustomerID,
       d.DateID,
       s.ServiceID,
       u.minutes,
       ROUND(
           CASE s.PlanType WHEN 'Basic' THEN 15 WHEN 'Standard' THEN 30 ELSE 55 END
           + u.minutes * 0.02
           + MOD(CRC32(CONCAT('extra', c.CustomerID, d.DateID)), 1000) / 100, 2),
       CASE WHEN p.r < 80 THEN 'Paid' WHEN p.r < 95 THEN 'Late' ELSE 'Unpaid' END,
       IF(p.r >= 80, 1, 0),
       CASE WHEN p.r < 80 THEN 0 WHEN p.r < 95 THEN 1 + MOD(p.r * 7, 30) ELSE 30 + MOD(p.r, 60) END
FROM dimcustomer c
CROSS JOIN dimdate d
JOIN dimservice s ON s.ServiceID = 1 + MOD(CRC32(CONCAT('svc', c.CustomerID)), 12)
-- Monthly-contract customers pay late more often, so the data has a story to find.
CROSS JOIN LATERAL (
    SELECT CAST(MOD(CRC32(CONCAT('pay', c.CustomerID, d.DateID)), 100) AS SIGNED)
           - IF(c.ContractType = 'Monthly', 0, 8) AS r
) p
CROSS JOIN LATERAL (
    SELECT 100 + MOD(CRC32(CONCAT('use', c.CustomerID, d.DateID)), 900)
           + IF(d.Month IN (7, 8, 12), 150, 0) AS minutes
) u
WHERE d.FullDate >= DATE_FORMAT(c.JoinDate, '%Y-%m-01');
