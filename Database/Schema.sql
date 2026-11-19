/* =====================================================================================
   UselessPredictions - Database Schema
   Target: SQL Server 2022, database "UselessPredictions", schema dbo

   Follows "Naming Conventions & Fundamentals.md":
     - PascalCase everywhere, no underscores (constraints and indexes included)
     - <Class>ID identifiers, <Class>Label labels, <Class>Master for hierarchies
     - Column order: ID, Type, Status, Master, Category, Label, ..., UserCreator
     - Joins only on INT / SMALLINT; no NULLs except dates and the score (where 0 is valid)
     - Optional references use 0, and every referenced table carries a row 0
     - No foreign key constraints yet (development freedom); reference columns are indexed
     - All timestamps are UTC

   Data flow:
     Persons -> Channels (on a Platform) -> Sources (+ SourceContents)
       -> SourceClaims (one assertion, quoted and dated) -> Claims (canonical proposition)
       -> Assessments (outcome + score -5..+5), backed by ClaimCitations -> Citations
   ===================================================================================== */

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* =====================================================================================
   GENERIC CLASSES
   ===================================================================================== */

IF OBJECT_ID(N'dbo.Users', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Users (
        UserID              INT IDENTITY(0,1) NOT NULL CONSTRAINT PKUsers PRIMARY KEY,
        UserType            SMALLINT        NOT NULL CONSTRAINT DFUserType DEFAULT (0),          -- Types (class User)
        UserStatus          SMALLINT        NOT NULL CONSTRAINT DFUserStatus DEFAULT (0),        -- Statuses (class User)
        UserLabel           NVARCHAR(320)   NOT NULL,
        UserEmail           VARCHAR(320)    NOT NULL CONSTRAINT DFUserEmail DEFAULT (''),
        UserDateCreated     DATETIME2(0)    NOT NULL CONSTRAINT DFUserDateCreated DEFAULT (SYSUTCDATETIME())
    );
END
GO

-- Generic types for every class that has no dedicated type table. IDs are fixed (referenced by code).
IF OBJECT_ID(N'dbo.Types', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Types (
        TypeID              SMALLINT        NOT NULL CONSTRAINT PKTypes PRIMARY KEY,
        TypeStatus          SMALLINT        NOT NULL CONSTRAINT DFTypeStatus DEFAULT (1),
        TypeClass           VARCHAR(40)     NOT NULL CONSTRAINT DFTypeClass DEFAULT (''),        -- Object Class the type belongs to
        TypeLabel           NVARCHAR(320)   NOT NULL,
        TypeDescription     NVARCHAR(1000)  NOT NULL CONSTRAINT DFTypeDescription DEFAULT (N''),
        TypeOrder           SMALLINT        NOT NULL CONSTRAINT DFTypeOrder DEFAULT (0)
    );
    CREATE INDEX IXTypeClass ON dbo.Types (TypeClass, TypeOrder);
END
GO

-- Generic statuses for every class. IDs are fixed (referenced by code).
IF OBJECT_ID(N'dbo.Statuses', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Statuses (
        StatusID            SMALLINT        NOT NULL CONSTRAINT PKStatuses PRIMARY KEY,
        StatusClass         VARCHAR(40)     NOT NULL CONSTRAINT DFStatusClass DEFAULT (''),
        StatusLabel         NVARCHAR(320)   NOT NULL,
        StatusDescription   NVARCHAR(1000)  NOT NULL CONSTRAINT DFStatusDescription DEFAULT (N''),
        StatusOrder         SMALLINT        NOT NULL CONSTRAINT DFStatusOrder DEFAULT (0)
    );
    CREATE INDEX IXStatusClass ON dbo.Statuses (StatusClass, StatusOrder);
END
GO

-- Subject taxonomy (Economy > Housing, Technology > AI, ...). Used by Claims and Persons.
IF OBJECT_ID(N'dbo.Categories', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Categories (
        CategoryID          INT IDENTITY(0,1) NOT NULL CONSTRAINT PKCategories PRIMARY KEY,
        CategoryStatus      SMALLINT        NOT NULL CONSTRAINT DFCategoryStatus DEFAULT (1),
        CategoryMaster      INT             NOT NULL CONSTRAINT DFCategoryMaster DEFAULT (0),
        CategoryLabel       NVARCHAR(320)   NOT NULL,
        CategoryDescription NVARCHAR(1000)  NOT NULL CONSTRAINT DFCategoryDescription DEFAULT (N''),
        CategoryOrder       SMALLINT        NOT NULL CONSTRAINT DFCategoryOrder DEFAULT (0)
    );
    CREATE INDEX IXCategoryMaster ON dbo.Categories (CategoryMaster);
END
GO

/* =====================================================================================
   LOOKUPS
   ===================================================================================== */

-- Platforms / websites on which tracked people publish (YouTube, X, Substack, ...).
IF OBJECT_ID(N'dbo.Platforms', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Platforms (
        PlatformID                  SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKPlatforms PRIMARY KEY,
        PlatformType                SMALLINT        NOT NULL CONSTRAINT DFPlatformType DEFAULT (0),      -- Types (class Platform)
        PlatformStatus              SMALLINT        NOT NULL CONSTRAINT DFPlatformStatus DEFAULT (1),
        PlatformLabel               NVARCHAR(320)   NOT NULL,
        PlatformURL                 VARCHAR(200)    NOT NULL CONSTRAINT DFPlatformURL DEFAULT (''),
        PlatformChannelURLFormat    VARCHAR(300)    NOT NULL CONSTRAINT DFPlatformChannelURLFormat DEFAULT (''),  -- {key} / {handle} placeholders
        PlatformSourceURLFormat     VARCHAR(300)    NOT NULL CONSTRAINT DFPlatformSourceURLFormat DEFAULT (''),
        PlatformHasAPI              BIT             NOT NULL CONSTRAINT DFPlatformHasAPI DEFAULT (0),    -- an ingestion connector exists
        PlatformNotes               NVARCHAR(1000)  NOT NULL CONSTRAINT DFPlatformNotes DEFAULT (N'')
    );
END
GO

-- Kind of published item: video, short, article, post, thread, ...
IF OBJECT_ID(N'dbo.SourceTypes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SourceTypes (
        SourceTypeID            SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKSourceTypes PRIMARY KEY,
        SourceTypeStatus        SMALLINT        NOT NULL CONSTRAINT DFSourceTypeStatus DEFAULT (1),
        SourceTypeLabel         NVARCHAR(320)   NOT NULL,
        SourceTypeDescription   NVARCHAR(1000)  NOT NULL CONSTRAINT DFSourceTypeDescription DEFAULT (N''),
        SourceTypeIsTimed       BIT             NOT NULL CONSTRAINT DFSourceTypeIsTimed DEFAULT (0),     -- audio/video: claims carry a time offset
        SourceTypeOrder         SMALLINT        NOT NULL CONSTRAINT DFSourceTypeOrder DEFAULT (0)
    );
END
GO

-- Nature of a claim. Two groups (via ClaimTypeMaster): what is predicted, and how it is framed.
IF OBJECT_ID(N'dbo.ClaimTypes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ClaimTypes (
        ClaimTypeID             SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKClaimTypes PRIMARY KEY,
        ClaimTypeStatus         SMALLINT        NOT NULL CONSTRAINT DFClaimTypeStatus DEFAULT (1),
        ClaimTypeMaster         SMALLINT        NOT NULL CONSTRAINT DFClaimTypeMaster DEFAULT (0),
        ClaimTypeLabel          NVARCHAR(320)   NOT NULL,
        ClaimTypeDescription    NVARCHAR(1000)  NOT NULL CONSTRAINT DFClaimTypeDescription DEFAULT (N''),
        ClaimTypeOrder          SMALLINT        NOT NULL CONSTRAINT DFClaimTypeOrder DEFAULT (0)
    );
END
GO

-- Direction of the predicted world-state: doom (-2) ... boom (+2).
IF OBJECT_ID(N'dbo.ClaimValences', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ClaimValences (
        ClaimValenceID          SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKClaimValences PRIMARY KEY,
        ClaimValenceLabel       NVARCHAR(320)   NOT NULL,
        ClaimValenceValue       SMALLINT        NOT NULL CONSTRAINT DFClaimValenceValue DEFAULT (0),
        ClaimValenceDescription NVARCHAR(1000)  NOT NULL CONSTRAINT DFClaimValenceDescription DEFAULT (N''),
        CONSTRAINT CKClaimValenceValue CHECK (ClaimValenceValue BETWEEN -2 AND 2)
    );
END
GO

-- How sure the speaker presented themselves. A hedged claim that fails is not judged like a "guaranteed" one.
IF OBJECT_ID(N'dbo.ClaimCertainties', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ClaimCertainties (
        ClaimCertaintyID            SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKClaimCertainties PRIMARY KEY,
        ClaimCertaintyLabel         NVARCHAR(320)   NOT NULL,
        ClaimCertaintyValue         SMALLINT        NOT NULL CONSTRAINT DFClaimCertaintyValue DEFAULT (0),
        ClaimCertaintyDescription   NVARCHAR(1000)  NOT NULL CONSTRAINT DFClaimCertaintyDescription DEFAULT (N'')
    );
END
GO

-- Rulebook that turns timing language into a due window, so deadlines are assigned consistently for everyone.
IF OBJECT_ID(N'dbo.ClaimTimeframes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ClaimTimeframes (
        ClaimTimeframeID            SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKClaimTimeframes PRIMARY KEY,
        ClaimTimeframeLabel         NVARCHAR(320)   NOT NULL,
        ClaimTimeframeIsExplicit    BIT             NOT NULL CONSTRAINT DFClaimTimeframeIsExplicit DEFAULT (0),  -- speaker named a date or period
        ClaimTimeframeMonthsMin     SMALLINT        NOT NULL CONSTRAINT DFClaimTimeframeMonthsMin DEFAULT (0),   -- default window, months after publication
        ClaimTimeframeMonthsMax     SMALLINT        NOT NULL CONSTRAINT DFClaimTimeframeMonthsMax DEFAULT (0),
        ClaimTimeframeDescription   NVARCHAR(1000)  NOT NULL CONSTRAINT DFClaimTimeframeDescription DEFAULT (N'')
    );
END
GO

-- Verdict categories. Top-level rows (ClaimOutcomeMaster = 0) are the reporting groups.
IF OBJECT_ID(N'dbo.ClaimOutcomes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ClaimOutcomes (
        ClaimOutcomeID          SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKClaimOutcomes PRIMARY KEY,
        ClaimOutcomeMaster      SMALLINT        NOT NULL CONSTRAINT DFClaimOutcomeMaster DEFAULT (0),
        ClaimOutcomeLabel       NVARCHAR(320)   NOT NULL,
        ClaimOutcomeDescription NVARCHAR(1000)  NOT NULL CONSTRAINT DFClaimOutcomeDescription DEFAULT (N''),
        ClaimOutcomeIsCounted   BIT             NOT NULL CONSTRAINT DFClaimOutcomeIsCounted DEFAULT (0),   -- part of the accuracy denominator
        ClaimOutcomeOrder       SMALLINT        NOT NULL CONSTRAINT DFClaimOutcomeOrder DEFAULT (0)
    );
END
GO

-- Rubric for the -5 .. +5 score. ScoreID is the score itself.
IF OBJECT_ID(N'dbo.Scores', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Scores (
        ScoreID             SMALLINT        NOT NULL CONSTRAINT PKScores PRIMARY KEY,
        ScoreLabel          NVARCHAR(320)   NOT NULL,
        ScoreDescription    NVARCHAR(1000)  NOT NULL CONSTRAINT DFScoreDescription DEFAULT (N''),
        CONSTRAINT CKScoreID CHECK (ScoreID BETWEEN -5 AND 5)
    );
END
GO

/* =====================================================================================
   CORE: WHO PUBLISHED WHAT
   ===================================================================================== */

-- Personalities / YouTubers / influencers (individuals, shows or outlets).
IF OBJECT_ID(N'dbo.Persons', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Persons (
        PersonID            INT IDENTITY(0,1) NOT NULL CONSTRAINT PKPersons PRIMARY KEY,
        PersonType          SMALLINT        NOT NULL CONSTRAINT DFPersonType DEFAULT (0),        -- Types (class Person)
        PersonStatus        SMALLINT        NOT NULL CONSTRAINT DFPersonStatus DEFAULT (0),      -- Statuses (class Person)
        PersonMaster        INT             NOT NULL CONSTRAINT DFPersonMaster DEFAULT (0),      -- member of a group / outlet
        PersonCategory      INT             NOT NULL CONSTRAINT DFPersonCategory DEFAULT (0),    -- main subject area
        PersonLabel         NVARCHAR(320)   NOT NULL,                                            -- public name
        PersonDescription   NVARCHAR(2000)  NOT NULL CONSTRAINT DFPersonDescription DEFAULT (N''),
        PersonCountry       VARCHAR(2)      NOT NULL CONSTRAINT DFPersonCountry DEFAULT (''),    -- ISO 3166-1 alpha-2
        PersonInclusion     NVARCHAR(1000)  NOT NULL CONSTRAINT DFPersonInclusion DEFAULT (N''), -- why this person is tracked (selection transparency)
        PersonNotes         NVARCHAR(4000)  NOT NULL CONSTRAINT DFPersonNotes DEFAULT (N''),
        PersonDateCreated   DATETIME2(0)    NOT NULL CONSTRAINT DFPersonDateCreated DEFAULT (SYSUTCDATETIME()),
        PersonDateEdited    DATETIME2(0)    NOT NULL CONSTRAINT DFPersonDateEdited DEFAULT (SYSUTCDATETIME()),
        PersonUserCreator   INT             NOT NULL CONSTRAINT DFPersonUserCreator DEFAULT (0)
    );
    CREATE INDEX IXPersonMaster ON dbo.Persons (PersonMaster);
END
GO

-- An account / outlet of a Person on a Platform: YouTube channel, X account, Substack, website, ...
IF OBJECT_ID(N'dbo.Channels', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Channels (
        ChannelID                   INT IDENTITY(0,1) NOT NULL CONSTRAINT PKChannels PRIMARY KEY,
        ChannelType                 SMALLINT        NOT NULL CONSTRAINT DFChannelType DEFAULT (0),       -- Types (class Channel)
        ChannelStatus               SMALLINT        NOT NULL CONSTRAINT DFChannelStatus DEFAULT (0),     -- Statuses (class Channel)
        ChannelLabel                NVARCHAR(320)   NOT NULL,
        ChannelPerson               INT             NOT NULL CONSTRAINT DFChannelPerson DEFAULT (0),
        ChannelPlatform             SMALLINT        NOT NULL CONSTRAINT DFChannelPlatform DEFAULT (0),
        ChannelKey                  VARCHAR(100)    NOT NULL CONSTRAINT DFChannelKey DEFAULT (''),       -- the platform's immutable ID (UC..., numeric user id)
        ChannelHandle               NVARCHAR(100)   NOT NULL CONSTRAINT DFChannelHandle DEFAULT (N''),   -- @handle / subdomain (can change)
        ChannelURL                  NVARCHAR(500)   NOT NULL CONSTRAINT DFChannelURL DEFAULT (N''),
        ChannelDescription          NVARCHAR(4000)  NOT NULL CONSTRAINT DFChannelDescription DEFAULT (N''),
        ChannelFollowerCount        BIGINT          NOT NULL CONSTRAINT DFChannelFollowerCount DEFAULT (0),
        ChannelSourceCount          INT             NOT NULL CONSTRAINT DFChannelSourceCount DEFAULT (0), -- items the platform reports
        ChannelDateStart            DATETIME2(0)    NULL,                                                -- account created on the platform
        ChannelDateEnd              DATETIME2(0)    NULL,                                                -- account closed / removed
        ChannelCoverageDateStart    DATE            NULL,                                                -- period for which ALL sources were ingested
        ChannelCoverageDateEnd      DATE            NULL,
        ChannelDateSynced           DATETIME2(0)    NULL,
        ChannelSyncCursor           VARCHAR(400)    NOT NULL CONSTRAINT DFChannelSyncCursor DEFAULT (''), -- paging token / since-id of the connector
        ChannelDateCreated          DATETIME2(0)    NOT NULL CONSTRAINT DFChannelDateCreated DEFAULT (SYSUTCDATETIME()),
        ChannelUserCreator          INT             NOT NULL CONSTRAINT DFChannelUserCreator DEFAULT (0)
    );
    CREATE INDEX IXChannelPerson ON dbo.Channels (ChannelPerson);
    CREATE UNIQUE INDEX UXChannelPlatformKey ON dbo.Channels (ChannelPlatform, ChannelKey) WHERE ChannelKey <> '';
END
GO

-- Ingestion runs started from the "add channel / search" page. Records scope, progress and API quota.
IF OBJECT_ID(N'dbo.Jobs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Jobs (
        JobID               INT IDENTITY(0,1) NOT NULL CONSTRAINT PKJobs PRIMARY KEY,
        JobType             SMALLINT        NOT NULL CONSTRAINT DFJobType DEFAULT (0),           -- Types (class Job)
        JobStatus           SMALLINT        NOT NULL CONSTRAINT DFJobStatus DEFAULT (0),         -- Statuses (class Job)
        JobMaster           INT             NOT NULL CONSTRAINT DFJobMaster DEFAULT (0),
        JobLabel            NVARCHAR(320)   NOT NULL,
        JobPerson           INT             NOT NULL CONSTRAINT DFJobPerson DEFAULT (0),
        JobChannel          INT             NOT NULL CONSTRAINT DFJobChannel DEFAULT (0),
        JobPlatform         SMALLINT        NOT NULL CONSTRAINT DFJobPlatform DEFAULT (0),
        JobInput            NVARCHAR(1000)  NOT NULL CONSTRAINT DFJobInput DEFAULT (N''),        -- URL / handle as entered
        JobParameters       NVARCHAR(4000)  NOT NULL CONSTRAINT DFJobParameters DEFAULT (N''),   -- JSON: date range, source types, limits
        JobItemCountFound   INT             NOT NULL CONSTRAINT DFJobItemCountFound DEFAULT (0),
        JobItemCountAdded   INT             NOT NULL CONSTRAINT DFJobItemCountAdded DEFAULT (0),
        JobQuotaUsed        INT             NOT NULL CONSTRAINT DFJobQuotaUsed DEFAULT (0),
        JobMessage          NVARCHAR(4000)  NOT NULL CONSTRAINT DFJobMessage DEFAULT (N''),
        JobDateStart        DATETIME2(0)    NULL,
        JobDateEnd          DATETIME2(0)    NULL,
        JobDateCreated      DATETIME2(0)    NOT NULL CONSTRAINT DFJobDateCreated DEFAULT (SYSUTCDATETIME()),
        JobUserCreator      INT             NOT NULL CONSTRAINT DFJobUserCreator DEFAULT (0)
    );
    CREATE INDEX IXJobStatus ON dbo.Jobs (JobStatus, JobDateCreated);
    CREATE INDEX IXJobChannel ON dbo.Jobs (JobChannel);
END
GO

-- Every video / article / post. Always dated. The Platform and the Person follow from the Channel.
IF OBJECT_ID(N'dbo.Sources', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Sources (
        SourceID            INT IDENTITY(0,1) NOT NULL CONSTRAINT PKSources PRIMARY KEY,
        SourceType          SMALLINT        NOT NULL CONSTRAINT DFSourceType DEFAULT (0),        -- SourceTypes
        SourceStatus        SMALLINT        NOT NULL CONSTRAINT DFSourceStatus DEFAULT (0),      -- Statuses (class Source)
        SourceMaster        INT             NOT NULL CONSTRAINT DFSourceMaster DEFAULT (0),      -- thread root, replied-to post, full video of a clip
        SourceLabel         NVARCHAR(320)   NOT NULL,                                            -- title (or the opening words of a post)
        SourceChannel       INT             NOT NULL CONSTRAINT DFSourceChannel DEFAULT (0),
        SourceKey           VARCHAR(100)    NOT NULL CONSTRAINT DFSourceKey DEFAULT (''),        -- the platform's ID (video id, post id)
        SourceURL           NVARCHAR(1000)  NOT NULL CONSTRAINT DFSourceURL DEFAULT (N''),
        SourceArchiveURL    NVARCHAR(1000)  NOT NULL CONSTRAINT DFSourceArchiveURL DEFAULT (N''),-- Wayback / archive copy as lasting evidence
        SourceThumbnailURL  NVARCHAR(1000)  NOT NULL CONSTRAINT DFSourceThumbnailURL DEFAULT (N''),
        SourceLanguage      VARCHAR(12)     NOT NULL CONSTRAINT DFSourceLanguage DEFAULT (''),   -- BCP 47
        SourceDuration      INT             NOT NULL CONSTRAINT DFSourceDuration DEFAULT (0),    -- seconds
        SourceViewCount     BIGINT          NOT NULL CONSTRAINT DFSourceViewCount DEFAULT (0),
        SourceLikeCount     BIGINT          NOT NULL CONSTRAINT DFSourceLikeCount DEFAULT (0),
        SourceCommentCount  BIGINT          NOT NULL CONSTRAINT DFSourceCommentCount DEFAULT (0),
        SourceShareCount    BIGINT          NOT NULL CONSTRAINT DFSourceShareCount DEFAULT (0),
        SourceIsPaywalled   BIT             NOT NULL CONSTRAINT DFSourceIsPaywalled DEFAULT (0),
        SourceJob           INT             NOT NULL CONSTRAINT DFSourceJob DEFAULT (0),         -- ingestion run that found it
        SourceNotes         NVARCHAR(2000)  NOT NULL CONSTRAINT DFSourceNotes DEFAULT (N''),
        SourceDatePublished DATETIME2(0)    NOT NULL,
        SourceDateSynced    DATETIME2(0)    NULL,                                                -- last metadata / metrics refresh
        SourceDateCreated   DATETIME2(0)    NOT NULL CONSTRAINT DFSourceDateCreated DEFAULT (SYSUTCDATETIME()),
        SourceUserCreator   INT             NOT NULL CONSTRAINT DFSourceUserCreator DEFAULT (0)
    );
    CREATE UNIQUE INDEX UXSourceChannelKey ON dbo.Sources (SourceChannel, SourceKey) WHERE SourceKey <> '';
    CREATE INDEX IXSourceDatePublished ON dbo.Sources (SourceDatePublished);
    CREATE INDEX IXSourceStatus ON dbo.Sources (SourceStatus);
    CREATE INDEX IXSourceMaster ON dbo.Sources (SourceMaster);
END
GO

-- Text of a source: article body, description, transcript(s). One source can have several.
IF OBJECT_ID(N'dbo.SourceContents', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SourceContents (
        SourceContentID             INT IDENTITY(1,1) NOT NULL CONSTRAINT PKSourceContents PRIMARY KEY,
        SourceContentType           SMALLINT        NOT NULL CONSTRAINT DFSourceContentType DEFAULT (0),     -- Types (class SourceContent)
        SourceContentStatus         SMALLINT        NOT NULL CONSTRAINT DFSourceContentStatus DEFAULT (0),
        SourceContentLabel          AS (N'Source Content ' + CAST(SourceContentID AS NVARCHAR(12))),
        SourceContentSource         INT             NOT NULL,
        SourceContentLanguage       VARCHAR(12)     NOT NULL CONSTRAINT DFSourceContentLanguage DEFAULT (''),
        SourceContentOrigin         VARCHAR(100)    NOT NULL CONSTRAINT DFSourceContentOrigin DEFAULT (''),  -- connector / tool that produced it
        SourceContentText           NTEXT           NOT NULL CONSTRAINT DFSourceContentText DEFAULT (N''),   -- plain text
        SourceContentData           NTEXT           NOT NULL CONSTRAINT DFSourceContentData DEFAULT (N''),   -- original with timings (JSON / VTT), if any
        SourceContentLength         INT             NOT NULL CONSTRAINT DFSourceContentLength DEFAULT (0),   -- characters in SourceContentText
        SourceContentHash           VARBINARY(32)   NOT NULL CONSTRAINT DFSourceContentHash DEFAULT (0x),    -- SHA-256 of the text, detects later edits
        SourceContentDateFetched    DATETIME2(0)    NOT NULL CONSTRAINT DFSourceContentDateFetched DEFAULT (SYSUTCDATETIME())
    );
    CREATE INDEX IXSourceContentSource ON dbo.SourceContents (SourceContentSource, SourceContentType);
END
GO

/* =====================================================================================
   CORE: WHAT WAS CLAIMED
   ===================================================================================== */

-- Canonical, person-independent proposition ("The US enters a recession"). Many people can assert the
-- same Claim many times; evidence and resolution criteria are kept here once and apply to all of them.
IF OBJECT_ID(N'dbo.Claims', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Claims (
        ClaimID             INT IDENTITY(0,1) NOT NULL CONSTRAINT PKClaims PRIMARY KEY,
        ClaimType           SMALLINT        NOT NULL CONSTRAINT DFClaimType DEFAULT (0),         -- ClaimTypes (primary nature)
        ClaimStatus         SMALLINT        NOT NULL CONSTRAINT DFClaimStatus DEFAULT (0),       -- Statuses (class Claim)
        ClaimMaster         INT             NOT NULL CONSTRAINT DFClaimMaster DEFAULT (0),       -- generic claim this one specialises
        ClaimCategory       INT             NOT NULL CONSTRAINT DFClaimCategory DEFAULT (0),     -- Categories
        ClaimLabel          NVARCHAR(320)   NOT NULL,                                            -- short neutral wording
        ClaimValence        SMALLINT        NOT NULL CONSTRAINT DFClaimValence DEFAULT (0),      -- ClaimValences
        ClaimStatement      NVARCHAR(2000)  NOT NULL CONSTRAINT DFClaimStatement DEFAULT (N''),  -- precise, testable proposition
        ClaimCriteria       NVARCHAR(4000)  NOT NULL CONSTRAINT DFClaimCriteria DEFAULT (N''),   -- what observable facts make it true / false, and which authority decides
        ClaimNotes          NVARCHAR(2000)  NOT NULL CONSTRAINT DFClaimNotes DEFAULT (N''),
        ClaimDateCreated    DATETIME2(0)    NOT NULL CONSTRAINT DFClaimDateCreated DEFAULT (SYSUTCDATETIME()),
        ClaimDateEdited     DATETIME2(0)    NOT NULL CONSTRAINT DFClaimDateEdited DEFAULT (SYSUTCDATETIME()),
        ClaimUserCreator    INT             NOT NULL CONSTRAINT DFClaimUserCreator DEFAULT (0)
    );
    CREATE INDEX IXClaimMaster ON dbo.Claims (ClaimMaster);
    CREATE INDEX IXClaimCategory ON dbo.Claims (ClaimCategory);
END
GO

-- One assertion of a Claim in one Source: the scoreable unit. Quoted verbatim, attributed to the
-- person who actually said it, with the window in which a reasonable person would expect it to happen.
IF OBJECT_ID(N'dbo.SourceClaims', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SourceClaims (
        SourceClaimID               INT IDENTITY(0,1) NOT NULL CONSTRAINT PKSourceClaims PRIMARY KEY,
        SourceClaimType             SMALLINT        NOT NULL CONSTRAINT DFSourceClaimType DEFAULT (0),       -- Types (class SourceClaim): original, repeat, revision, retraction, ...
        SourceClaimStatus           SMALLINT        NOT NULL CONSTRAINT DFSourceClaimStatus DEFAULT (0),     -- Statuses (class SourceClaim)
        SourceClaimMaster           INT             NOT NULL CONSTRAINT DFSourceClaimMaster DEFAULT (0),     -- earlier assertion this one repeats / revises / retracts
        SourceClaimLabel            NVARCHAR(320)   NOT NULL,                                                -- what was asserted, in one neutral sentence
        SourceClaimSource           INT             NOT NULL,
        SourceClaimClaim            INT             NOT NULL CONSTRAINT DFSourceClaimClaim DEFAULT (0),      -- Claims (0 = not yet matched)
        SourceClaimPerson           INT             NOT NULL CONSTRAINT DFSourceClaimPerson DEFAULT (0),     -- the speaker (a guest is not the host)
        SourceClaimPart             SMALLINT        NOT NULL CONSTRAINT DFSourceClaimPart DEFAULT (0),       -- Types (class SourcePart): title, thumbnail, body, ...
        SourceClaimCertainty        SMALLINT        NOT NULL CONSTRAINT DFSourceClaimCertainty DEFAULT (0),  -- ClaimCertainties
        SourceClaimTimeframe        SMALLINT        NOT NULL CONSTRAINT DFSourceClaimTimeframe DEFAULT (0),  -- ClaimTimeframes
        SourceClaimIsPrimary        BIT             NOT NULL CONSTRAINT DFSourceClaimIsPrimary DEFAULT (0),  -- the source's headline / generic claim
        SourceClaimQuote            NVARCHAR(4000)  NOT NULL CONSTRAINT DFSourceClaimQuote DEFAULT (N''),    -- verbatim
        SourceClaimContext          NVARCHAR(4000)  NOT NULL CONSTRAINT DFSourceClaimContext DEFAULT (N''),  -- surrounding caveats the speaker gave
        SourceClaimCondition        NVARCHAR(1000)  NOT NULL CONSTRAINT DFSourceClaimCondition DEFAULT (N''),-- "if X ..." precondition, when stated
        SourceClaimTimeframeQuote   NVARCHAR(500)   NOT NULL CONSTRAINT DFSourceClaimTimeframeQuote DEFAULT (N''), -- the speaker's own timing words
        SourceClaimTimeframeNote    NVARCHAR(1000)  NOT NULL CONSTRAINT DFSourceClaimTimeframeNote DEFAULT (N''),  -- why this window was assigned
        SourceClaimOffsetStart      INT             NOT NULL CONSTRAINT DFSourceClaimOffsetStart DEFAULT (0),      -- seconds into the audio / video
        SourceClaimOffsetEnd        INT             NOT NULL CONSTRAINT DFSourceClaimOffsetEnd DEFAULT (0),
        SourceClaimDueDateMin       DATE            NULL,                                                    -- earliest date it should have shown (strict reading)
        SourceClaimDueDateMax       DATE            NULL,                                                    -- latest date (charitable reading); after this it has failed
        SourceClaimModel            VARCHAR(100)    NOT NULL CONSTRAINT DFSourceClaimModel DEFAULT (''),     -- AI model that extracted it, if any
        SourceClaimDateCreated      DATETIME2(0)    NOT NULL CONSTRAINT DFSourceClaimDateCreated DEFAULT (SYSUTCDATETIME()),
        SourceClaimDateReviewed     DATETIME2(0)    NULL,
        SourceClaimUserCreator      INT             NOT NULL CONSTRAINT DFSourceClaimUserCreator DEFAULT (0),
        SourceClaimUserReviewer     INT             NOT NULL CONSTRAINT DFSourceClaimUserReviewer DEFAULT (0),
        CONSTRAINT CKSourceClaimDueDate CHECK (SourceClaimDueDateMax IS NULL OR SourceClaimDueDateMin IS NULL OR SourceClaimDueDateMax >= SourceClaimDueDateMin)
    );
    CREATE INDEX IXSourceClaimSource ON dbo.SourceClaims (SourceClaimSource);
    CREATE INDEX IXSourceClaimClaim ON dbo.SourceClaims (SourceClaimClaim);
    CREATE INDEX IXSourceClaimPerson ON dbo.SourceClaims (SourceClaimPerson, SourceClaimStatus);
    CREATE INDEX IXSourceClaimMaster ON dbo.SourceClaims (SourceClaimMaster);
    CREATE INDEX IXSourceClaimDueDateMax ON dbo.SourceClaims (SourceClaimDueDateMax);
END
GO

-- All natures / framings that apply to one assertion (disaster + imminent + "nobody is aware" ...).
IF OBJECT_ID(N'dbo.SourceClaimClaimTypes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SourceClaimClaimTypes (
        SourceClaimClaimTypeID  INT IDENTITY(1,1) NOT NULL CONSTRAINT PKSourceClaimClaimTypes PRIMARY KEY,
        SCCTLabel               AS (N'Source Claim Claim Type ' + CAST(SourceClaimClaimTypeID AS NVARCHAR(12))),
        SCCTSourceClaim         INT             NOT NULL,
        SCCTClaimType           SMALLINT        NOT NULL
    );
    CREATE UNIQUE INDEX UXSCCTSourceClaimClaimType ON dbo.SourceClaimClaimTypes (SCCTSourceClaim, SCCTClaimType);
    CREATE INDEX IXSCCTClaimType ON dbo.SourceClaimClaimTypes (SCCTClaimType);
END
GO

/* =====================================================================================
   CORE: WHAT ACTUALLY HAPPENED
   ===================================================================================== */

-- A verdict on one assertion. Kept as history: AI proposes, a human confirms, pending ones are redone later.
IF OBJECT_ID(N'dbo.Assessments', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Assessments (
        AssessmentID            INT IDENTITY(1,1) NOT NULL CONSTRAINT PKAssessments PRIMARY KEY,
        AssessmentType          SMALLINT        NOT NULL CONSTRAINT DFAssessmentType DEFAULT (0),        -- Types (class Assessment)
        AssessmentStatus        SMALLINT        NOT NULL CONSTRAINT DFAssessmentStatus DEFAULT (0),      -- Statuses (class Assessment)
        AssessmentLabel         NVARCHAR(320)   NOT NULL CONSTRAINT DFAssessmentLabel DEFAULT (N''),     -- one-line verdict
        AssessmentSourceClaim   INT             NOT NULL,
        AssessmentOutcome       SMALLINT        NOT NULL CONSTRAINT DFAssessmentOutcome DEFAULT (0),     -- ClaimOutcomes
        AssessmentScore         SMALLINT        NULL,                                                    -- Scores: -5 .. +5 (0 is a valid score, so NULL = not scored)
        AssessmentConfidence    SMALLINT        NOT NULL CONSTRAINT DFAssessmentConfidence DEFAULT (0),  -- assessor's confidence in the verdict, 0-100
        AssessmentIsCurrent     BIT             NOT NULL CONSTRAINT DFAssessmentIsCurrent DEFAULT (0),
        AssessmentRationale     NVARCHAR(4000)  NOT NULL CONSTRAINT DFAssessmentRationale DEFAULT (N''), -- reasoning, referring to the citations used
        AssessmentModel         VARCHAR(100)    NOT NULL CONSTRAINT DFAssessmentModel DEFAULT (''),
        AssessmentDateResolved  DATE            NULL,                                                    -- when it materialised, or when the window lapsed
        AssessmentDateAssessed  DATETIME2(0)    NOT NULL CONSTRAINT DFAssessmentDateAssessed DEFAULT (SYSUTCDATETIME()),
        AssessmentUserCreator   INT             NOT NULL CONSTRAINT DFAssessmentUserCreator DEFAULT (0),
        CONSTRAINT CKAssessmentScore CHECK (AssessmentScore BETWEEN -5 AND 5),
        CONSTRAINT CKAssessmentConfidence CHECK (AssessmentConfidence BETWEEN 0 AND 100)
    );
    CREATE INDEX IXAssessmentSourceClaim ON dbo.Assessments (AssessmentSourceClaim);
    CREATE UNIQUE INDEX UXAssessmentCurrent ON dbo.Assessments (AssessmentSourceClaim) WHERE AssessmentIsCurrent = 1;
END
GO

-- An external piece of evidence: statistic, dataset, report, filing, the person's own later statement.
IF OBJECT_ID(N'dbo.Citations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Citations (
        CitationID              INT IDENTITY(0,1) NOT NULL CONSTRAINT PKCitations PRIMARY KEY,
        CitationType            SMALLINT        NOT NULL CONSTRAINT DFCitationType DEFAULT (0),          -- Types (class Citation)
        CitationStatus          SMALLINT        NOT NULL CONSTRAINT DFCitationStatus DEFAULT (0),        -- Statuses (class Citation)
        CitationLabel           NVARCHAR(320)   NOT NULL,                                                -- title
        CitationPublisher       NVARCHAR(320)   NOT NULL CONSTRAINT DFCitationPublisher DEFAULT (N''),
        CitationAuthor          NVARCHAR(320)   NOT NULL CONSTRAINT DFCitationAuthor DEFAULT (N''),
        CitationURL             NVARCHAR(1000)  NOT NULL CONSTRAINT DFCitationURL DEFAULT (N''),
        CitationArchiveURL      NVARCHAR(1000)  NOT NULL CONSTRAINT DFCitationArchiveURL DEFAULT (N''),
        CitationNotes           NVARCHAR(2000)  NOT NULL CONSTRAINT DFCitationNotes DEFAULT (N''),
        CitationDatePublished   DATE            NULL,
        CitationDateAccessed    DATETIME2(0)    NOT NULL CONSTRAINT DFCitationDateAccessed DEFAULT (SYSUTCDATETIME()),
        CitationUserCreator     INT             NOT NULL CONSTRAINT DFCitationUserCreator DEFAULT (0)
    );
END
GO

-- Links evidence to a Claim (shared by everyone who asserted it) or to one specific assertion.
IF OBJECT_ID(N'dbo.ClaimCitations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ClaimCitations (
        ClaimCitationID             INT IDENTITY(1,1) NOT NULL CONSTRAINT PKClaimCitations PRIMARY KEY,
        ClaimCitationType           SMALLINT        NOT NULL CONSTRAINT DFClaimCitationType DEFAULT (0),     -- Types (class ClaimCitation): supports, contradicts, context
        ClaimCitationLabel          AS (N'Claim Citation ' + CAST(ClaimCitationID AS NVARCHAR(12))),
        ClaimCitationClaim          INT             NOT NULL CONSTRAINT DFClaimCitationClaim DEFAULT (0),
        ClaimCitationSourceClaim    INT             NOT NULL CONSTRAINT DFClaimCitationSourceClaim DEFAULT (0), -- 0 = applies to every assertion of the Claim
        ClaimCitationCitation       INT             NOT NULL,
        ClaimCitationExcerpt        NVARCHAR(4000)  NOT NULL CONSTRAINT DFClaimCitationExcerpt DEFAULT (N''),   -- quoted passage or data point relied on
        ClaimCitationNote           NVARCHAR(2000)  NOT NULL CONSTRAINT DFClaimCitationNote DEFAULT (N''),
        ClaimCitationDateStart      DATE            NULL,                                                       -- period the fact refers to
        ClaimCitationDateEnd        DATE            NULL,
        ClaimCitationDateCreated    DATETIME2(0)    NOT NULL CONSTRAINT DFClaimCitationDateCreated DEFAULT (SYSUTCDATETIME()),
        ClaimCitationUserCreator    INT             NOT NULL CONSTRAINT DFClaimCitationUserCreator DEFAULT (0)
    );
    CREATE INDEX IXClaimCitationClaim ON dbo.ClaimCitations (ClaimCitationClaim);
    CREATE INDEX IXClaimCitationSourceClaim ON dbo.ClaimCitations (ClaimCitationSourceClaim);
    CREATE INDEX IXClaimCitationCitation ON dbo.ClaimCitations (ClaimCitationCitation);
END
GO

/* =====================================================================================
   PERSON-LEVEL VERDICTS AND AI REPORTS
   ===================================================================================== */

-- Contradictions and other links between two assertions of DIFFERENT claims (coherence / consistency).
-- Lineage of the SAME claim (repeat, revision, retraction) lives in SourceClaims.SourceClaimMaster.
IF OBJECT_ID(N'dbo.SourceClaimRelations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SourceClaimRelations (
        SourceClaimRelationID       INT IDENTITY(1,1) NOT NULL CONSTRAINT PKSourceClaimRelations PRIMARY KEY,
        SourceClaimRelationType     SMALLINT        NOT NULL CONSTRAINT DFSourceClaimRelationType DEFAULT (0),   -- Types (class SourceClaimRelation)
        SourceClaimRelationStatus   SMALLINT        NOT NULL CONSTRAINT DFSourceClaimRelationStatus DEFAULT (0), -- Statuses (class SourceClaimRelation)
        SCRLabel                    AS (N'Source Claim Relation ' + CAST(SourceClaimRelationID AS NVARCHAR(12))),
        SCRSourceClaim              INT             NOT NULL,                                                    -- the later assertion
        SCRSourceClaimRelated       INT             NOT NULL,                                                    -- the earlier assertion it relates to
        SCRNote                     NVARCHAR(2000)  NOT NULL CONSTRAINT DFSCRNote DEFAULT (N''),                 -- why the two conflict / connect
        SCRModel                    VARCHAR(100)    NOT NULL CONSTRAINT DFSCRModel DEFAULT (''),
        SCRDateCreated              DATETIME2(0)    NOT NULL CONSTRAINT DFSCRDateCreated DEFAULT (SYSUTCDATETIME()),
        SCRUserCreator              INT             NOT NULL CONSTRAINT DFSCRUserCreator DEFAULT (0)
    );
    CREATE INDEX IXSCRSourceClaim ON dbo.SourceClaimRelations (SCRSourceClaim);
    CREATE INDEX IXSCRSourceClaimRelated ON dbo.SourceClaimRelations (SCRSourceClaimRelated);
END
GO

-- The qualities on which a person's record is judged: accuracy, coherence, consistency, accountability, ...
IF OBJECT_ID(N'dbo.Dimensions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Dimensions (
        DimensionID             SMALLINT IDENTITY(0,1) NOT NULL CONSTRAINT PKDimensions PRIMARY KEY,
        DimensionStatus         SMALLINT        NOT NULL CONSTRAINT DFDimensionStatus DEFAULT (1),
        DimensionLabel          NVARCHAR(320)   NOT NULL,
        DimensionDescription    NVARCHAR(2000)  NOT NULL CONSTRAINT DFDimensionDescription DEFAULT (N''),  -- what it measures
        DimensionMethod         NVARCHAR(2000)  NOT NULL CONSTRAINT DFDimensionMethod DEFAULT (N''),       -- how it is derived from the data
        DimensionOrder          SMALLINT        NOT NULL CONSTRAINT DFDimensionOrder DEFAULT (0)
    );
END
GO

-- An analysis written by an AI model (or a person) over a selection of claims / sources:
-- the overall verdict on a person, or a free-form report on any list of assertions.
IF OBJECT_ID(N'dbo.Reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Reports (
        ReportID                INT IDENTITY(0,1) NOT NULL CONSTRAINT PKReports PRIMARY KEY,
        ReportType              SMALLINT        NOT NULL CONSTRAINT DFReportType DEFAULT (0),            -- Types (class Report)
        ReportStatus            SMALLINT        NOT NULL CONSTRAINT DFReportStatus DEFAULT (0),          -- Statuses (class Report)
        ReportCategory          INT             NOT NULL CONSTRAINT DFReportCategory DEFAULT (0),        -- limited to one subject area, if any
        ReportLabel             NVARCHAR(320)   NOT NULL,
        ReportPerson            INT             NOT NULL CONSTRAINT DFReportPerson DEFAULT (0),
        ReportChannel           INT             NOT NULL CONSTRAINT DFReportChannel DEFAULT (0),
        ReportIsCurrent         BIT             NOT NULL CONSTRAINT DFReportIsCurrent DEFAULT (0),       -- latest report of its type for the person
        ReportSummary           NVARCHAR(4000)  NOT NULL CONSTRAINT DFReportSummary DEFAULT (N''),       -- the paragraph or two
        ReportText              NTEXT           NOT NULL CONSTRAINT DFReportText DEFAULT (N''),          -- full report (Markdown)
        ReportInstruction       NVARCHAR(4000)  NOT NULL CONSTRAINT DFReportInstruction DEFAULT (N''),   -- what the model was asked
        ReportParameters        NVARCHAR(4000)  NOT NULL CONSTRAINT DFReportParameters DEFAULT (N''),    -- JSON: how the material was selected
        ReportModel             VARCHAR(100)    NOT NULL CONSTRAINT DFReportModel DEFAULT (''),
        ReportClaimCount        INT             NOT NULL CONSTRAINT DFReportClaimCount DEFAULT (0),
        ReportSourceCount       INT             NOT NULL CONSTRAINT DFReportSourceCount DEFAULT (0),
        ReportJob               INT             NOT NULL CONSTRAINT DFReportJob DEFAULT (0),
        ReportCoverageDateStart DATE            NULL,                                                    -- period of the material covered
        ReportCoverageDateEnd   DATE            NULL,
        ReportDateCreated       DATETIME2(0)    NOT NULL CONSTRAINT DFReportDateCreated DEFAULT (SYSUTCDATETIME()),
        ReportUserCreator       INT             NOT NULL CONSTRAINT DFReportUserCreator DEFAULT (0)
    );
    CREATE INDEX IXReportPerson ON dbo.Reports (ReportPerson, ReportType);
END
GO

-- Score per Dimension within a Report, on the same -5 .. +5 scale as claims.
IF OBJECT_ID(N'dbo.ReportDimensions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportDimensions (
        ReportDimensionID           INT IDENTITY(1,1) NOT NULL CONSTRAINT PKReportDimensions PRIMARY KEY,
        ReportDimensionLabel        AS (N'Report Dimension ' + CAST(ReportDimensionID AS NVARCHAR(12))),
        ReportDimensionReport       INT             NOT NULL,
        ReportDimensionDimension    SMALLINT        NOT NULL,
        ReportDimensionScore        SMALLINT        NULL,                                                    -- Scores: -5 .. +5; NULL = too little data to judge
        ReportDimensionMetric       DECIMAL(9,4)    NULL,                                                    -- the measured figure behind the score (e.g. share correct)
        ReportDimensionClaimCount   INT             NOT NULL CONSTRAINT DFReportDimensionClaimCount DEFAULT (0), -- assertions the score rests on
        ReportDimensionRationale    NVARCHAR(4000)  NOT NULL CONSTRAINT DFReportDimensionRationale DEFAULT (N''),
        CONSTRAINT CKReportDimensionScore CHECK (ReportDimensionScore BETWEEN -5 AND 5)
    );
    CREATE UNIQUE INDEX UXReportDimension ON dbo.ReportDimensions (ReportDimensionReport, ReportDimensionDimension);
END
GO

-- Exactly which assertions a Report was based on (so every report can be traced and reproduced).
IF OBJECT_ID(N'dbo.ReportSourceClaims', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportSourceClaims (
        ReportSourceClaimID     INT IDENTITY(1,1) NOT NULL CONSTRAINT PKReportSourceClaims PRIMARY KEY,
        RSCLabel                AS (N'Report Source Claim ' + CAST(ReportSourceClaimID AS NVARCHAR(12))),
        RSCReport               INT             NOT NULL,
        RSCSourceClaim          INT             NOT NULL
    );
    CREATE UNIQUE INDEX UXRSCReportSourceClaim ON dbo.ReportSourceClaims (RSCReport, RSCSourceClaim);
    CREATE INDEX IXRSCSourceClaim ON dbo.ReportSourceClaims (RSCSourceClaim);
END
GO

-- Sources whose text or summary was given to a Report directly (not only through their claims).
IF OBJECT_ID(N'dbo.ReportSources', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportSources (
        ReportSourceID          INT IDENTITY(1,1) NOT NULL CONSTRAINT PKReportSources PRIMARY KEY,
        ReportSourceLabel       AS (N'Report Source ' + CAST(ReportSourceID AS NVARCHAR(12))),
        ReportSourceReport      INT             NOT NULL,
        ReportSourceSource      INT             NOT NULL
    );
    CREATE UNIQUE INDEX UXReportSource ON dbo.ReportSources (ReportSourceReport, ReportSourceSource);
END
GO

/* =====================================================================================
   VIEWS
   ===================================================================================== */

-- Every assertion with its source, speaker, canonical claim and current verdict.
CREATE OR ALTER VIEW dbo.SourceClaimList
AS
SELECT
    sc.SourceClaimID, sc.SourceClaimLabel, sc.SourceClaimQuote, sc.SourceClaimIsPrimary,
    sc.SourceClaimType, sct.TypeLabel AS SourceClaimTypeLabel,
    sc.SourceClaimStatus, scs.StatusLabel AS SourceClaimStatusLabel,
    sc.SourceClaimOffsetStart, sc.SourceClaimDueDateMin, sc.SourceClaimDueDateMax,
    cer.ClaimCertaintyLabel, tf.ClaimTimeframeLabel,
    s.SourceID, s.SourceLabel, s.SourceURL, s.SourceDatePublished, st.SourceTypeLabel,
    ch.ChannelID, ch.ChannelLabel, pl.PlatformID, pl.PlatformLabel,
    p.PersonID, p.PersonLabel,
    c.ClaimID, c.ClaimLabel, ct.ClaimTypeLabel, cat.CategoryID, cat.CategoryLabel,
    v.ClaimValenceLabel, v.ClaimValenceValue,
    a.AssessmentID, a.AssessmentStatus, ast.StatusLabel AS AssessmentStatusLabel, a.AssessmentLabel, a.AssessmentConfidence,
    a.AssessmentScore, sco.ScoreLabel,
    a.AssessmentDateResolved, a.AssessmentDateAssessed,
    o.ClaimOutcomeID, o.ClaimOutcomeLabel, o.ClaimOutcomeIsCounted,
    og.ClaimOutcomeID AS ClaimOutcomeGroupID, og.ClaimOutcomeLabel AS ClaimOutcomeGroupLabel
FROM dbo.SourceClaims sc
LEFT OUTER JOIN dbo.Types sct            ON sct.TypeID = sc.SourceClaimType
LEFT OUTER JOIN dbo.Statuses scs         ON scs.StatusID = sc.SourceClaimStatus
LEFT OUTER JOIN dbo.ClaimCertainties cer ON cer.ClaimCertaintyID = sc.SourceClaimCertainty
LEFT OUTER JOIN dbo.ClaimTimeframes tf   ON tf.ClaimTimeframeID = sc.SourceClaimTimeframe
LEFT OUTER JOIN dbo.Sources s            ON s.SourceID = sc.SourceClaimSource
LEFT OUTER JOIN dbo.SourceTypes st       ON st.SourceTypeID = s.SourceType
LEFT OUTER JOIN dbo.Channels ch          ON ch.ChannelID = s.SourceChannel
LEFT OUTER JOIN dbo.Platforms pl         ON pl.PlatformID = ch.ChannelPlatform
LEFT OUTER JOIN dbo.Persons p            ON p.PersonID = sc.SourceClaimPerson
LEFT OUTER JOIN dbo.Claims c             ON c.ClaimID = sc.SourceClaimClaim
LEFT OUTER JOIN dbo.ClaimTypes ct        ON ct.ClaimTypeID = c.ClaimType
LEFT OUTER JOIN dbo.Categories cat       ON cat.CategoryID = c.ClaimCategory
LEFT OUTER JOIN dbo.ClaimValences v      ON v.ClaimValenceID = c.ClaimValence
LEFT OUTER JOIN dbo.Assessments a        ON a.AssessmentSourceClaim = sc.SourceClaimID AND a.AssessmentIsCurrent = 1
LEFT OUTER JOIN dbo.Scores sco           ON sco.ScoreID = a.AssessmentScore
LEFT OUTER JOIN dbo.Statuses ast         ON ast.StatusID = a.AssessmentStatus
LEFT OUTER JOIN dbo.ClaimOutcomes o      ON o.ClaimOutcomeID = a.AssessmentOutcome
LEFT OUTER JOIN dbo.ClaimOutcomes og     ON og.ClaimOutcomeID = o.ClaimOutcomeMaster
WHERE sc.SourceClaimID > 0;
GO

-- Scorecard per person. Two gates keep AI output from counting until a person has looked at it:
-- the assertion must be Confirmed (502) and its current verdict must be Confirmed (602).
-- Predictions = original (501) or repeated (502) assertions. Outcome groups: 1 Open, 2 Correct,
-- 3 Partly correct, 4 Incorrect, 5 Not scoreable. A prediction without a confirmed verdict is Open.
-- Revisions (503), retractions (504) and claimed vindications (505) are counted separately:
-- they feed the accountability and consistency verdicts.
CREATE OR ALTER VIEW dbo.PersonScoreSummary
AS
SELECT
    p.PersonID, p.PersonLabel,
    SUM(f.IsPrediction)                                                                 AS PersonClaimCount,
    COUNT(DISTINCT CASE WHEN f.IsPrediction = 1 THEN NULLIF(l.ClaimID, 0) END)          AS PersonClaimCountDistinct,
    SUM(CASE WHEN f.IsPrediction = 1 AND f.IsCounted = 1 THEN 1 ELSE 0 END)             AS PersonClaimCountScored,
    SUM(CASE WHEN f.IsPrediction = 1 AND f.GroupID = 2 THEN 1 ELSE 0 END)               AS PersonClaimCountCorrect,
    SUM(CASE WHEN f.IsPrediction = 1 AND f.GroupID = 3 THEN 1 ELSE 0 END)               AS PersonClaimCountPartial,
    SUM(CASE WHEN f.IsPrediction = 1 AND f.GroupID = 4 THEN 1 ELSE 0 END)               AS PersonClaimCountIncorrect,
    SUM(CASE WHEN f.IsPrediction = 1 AND f.GroupID = 5 THEN 1 ELSE 0 END)               AS PersonClaimCountUnscoreable,
    SUM(CASE WHEN f.IsPrediction = 1 AND ISNULL(f.GroupID, 0) IN (0, 1) THEN 1 ELSE 0 END) AS PersonClaimCountOpen,
    AVG(CASE WHEN f.IsPrediction = 1 AND f.IsCounted = 1 THEN CAST(l.AssessmentScore AS DECIMAL(9,4)) END) AS PersonScoreAverage,
    SUM(CASE WHEN l.SourceClaimType = 502 THEN 1 ELSE 0 END)                            AS PersonClaimCountRepeated,
    SUM(CASE WHEN l.SourceClaimType = 503 THEN 1 ELSE 0 END)                            AS PersonClaimCountRevised,
    SUM(CASE WHEN l.SourceClaimType = 504 THEN 1 ELSE 0 END)                            AS PersonClaimCountRetracted,
    SUM(CASE WHEN l.SourceClaimType = 505 THEN 1 ELSE 0 END)                            AS PersonClaimCountVindication
FROM dbo.Persons p
LEFT OUTER JOIN dbo.SourceClaimList l
    ON  l.PersonID = p.PersonID
    AND l.SourceClaimStatus = 502           -- Confirmed assertion
OUTER APPLY (
    SELECT CASE WHEN l.SourceClaimType IN (501, 502) THEN 1 ELSE 0 END                                  AS IsPrediction,
           CASE WHEN l.AssessmentStatus = 602 THEN l.ClaimOutcomeGroupID END                            AS GroupID,
           CASE WHEN l.AssessmentStatus = 602 AND l.ClaimOutcomeIsCounted = 1 THEN 1 ELSE 0 END         AS IsCounted
) f
WHERE p.PersonID > 0
GROUP BY p.PersonID, p.PersonLabel;
GO

-- Score per source: average over its assertions that have a confirmed, scored verdict.
CREATE OR ALTER VIEW dbo.SourceScoreSummary
AS
SELECT
    l.SourceID, l.SourceLabel, l.SourceDatePublished, l.PersonID, l.PersonLabel,
    COUNT(l.SourceClaimID)                                                                              AS SourceClaimCount,
    SUM(CASE WHEN l.AssessmentStatus = 602 AND l.ClaimOutcomeIsCounted = 1 THEN 1 ELSE 0 END)           AS SourceClaimCountScored,
    AVG(CASE WHEN l.AssessmentStatus = 602 AND l.ClaimOutcomeIsCounted = 1 THEN CAST(l.AssessmentScore AS DECIMAL(9,4)) END) AS SourceScoreAverage
FROM dbo.SourceClaimList l
WHERE l.SourceClaimStatus <> 503            -- not Rejected
GROUP BY l.SourceID, l.SourceLabel, l.SourceDatePublished, l.PersonID, l.PersonLabel;
GO
