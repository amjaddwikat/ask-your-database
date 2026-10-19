-- Star schema for the sample telecom data warehouse.
CREATE DATABASE IF NOT EXISTS telecom_dw CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS app CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

USE telecom_dw;

CREATE TABLE dimcustomer (
    CustomerID   INT PRIMARY KEY,
    Age          INT          NOT NULL,
    Gender       VARCHAR(10)  NOT NULL,
    City         VARCHAR(50)  NOT NULL,
    Region       VARCHAR(20)  NOT NULL,
    ContractType VARCHAR(20)  NOT NULL COMMENT 'Monthly, One year, Two year',
    JoinDate     DATE         NOT NULL
);

CREATE TABLE dimdate (
    DateID   INT PRIMARY KEY COMMENT 'yyyymmdd',
    FullDate DATE NOT NULL,
    Day      INT  NOT NULL,
    Month    INT  NOT NULL,
    Quarter  INT  NOT NULL,
    Year     INT  NOT NULL
);

CREATE TABLE dimservice (
    ServiceID   INT PRIMARY KEY,
    ServiceType VARCHAR(20) NOT NULL COMMENT 'Mobile, Internet, TV, Landline',
    PlanType    VARCHAR(20) NOT NULL COMMENT 'Basic, Standard, Premium'
);

CREATE TABLE factbilling (
    BillingID        INT PRIMARY KEY,
    CustomerID       INT           NOT NULL,
    DateID           INT           NOT NULL,
    ServiceID        INT           NOT NULL,
    UsageMinutes     INT           NOT NULL,
    BillAmount       DECIMAL(10,2) NOT NULL,
    PaymentStatus    VARCHAR(10)   NOT NULL COMMENT 'Paid, Late, Unpaid',
    LatePaymentFlag  TINYINT(1)    NOT NULL,
    PaymentDelayDays INT           NOT NULL,
    CONSTRAINT fk_billing_customer FOREIGN KEY (CustomerID) REFERENCES dimcustomer (CustomerID),
    CONSTRAINT fk_billing_date     FOREIGN KEY (DateID)     REFERENCES dimdate (DateID),
    CONSTRAINT fk_billing_service  FOREIGN KEY (ServiceID)  REFERENCES dimservice (ServiceID),
    INDEX ix_billing_date (DateID),
    INDEX ix_billing_customer (CustomerID)
);
