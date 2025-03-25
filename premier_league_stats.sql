CREATE DATABASE premier_league_stats;
USE premier_league_stats;

-- Table to store teams
CREATE TABLE Teams (
    TeamID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    ShortName VARCHAR(3) NOT NULL
);

-- Alter table to add Rank column
ALTER TABLE Teams ADD `Rank` INT;

-- Insert actual Premier League teams
INSERT INTO Teams (Name, ShortName, `Rank`) VALUES
('Arsenal', 'ARS', 1),
('Aston Villa', 'AVL', 2),
('Bournemouth', 'BOU', 3),
('Brentford', 'BRE', 4),
('Brighton & Hove Albion', 'BHA', 5),
('Chelsea', 'CHE', 6),
('Crystal Palace', 'CRY', 7),
('Everton', 'EVE', 8),
('Fulham', 'FUL', 9),
('Leeds United', 'LEE', 10),
('Leicester City', 'LEI', 11),
('Liverpool', 'LIV', 12),
('Manchester City', 'MCI', 13),
('Manchester United', 'MUN', 14),
('Newcastle United', 'NEW', 15),
('Nottingham Forest', 'NFO', 16),
('Tottenham Hotspur', 'TOT', 17),
('West Ham United', 'WHU', 18),
('Wolverhampton Wanderers', 'WOL', 19);

-- Table to store players
CREATE TABLE Players (
    PlayerID INT AUTO_INCREMENT PRIMARY KEY,
    TeamID INT,
    Name VARCHAR(100) NOT NULL,
    Position VARCHAR(20),
    Number INT,
    FOREIGN KEY (TeamID) REFERENCES Teams(TeamID)
);

-- Table to store historical matches
CREATE TABLE HistoricalMatches (
    MatchID INT AUTO_INCREMENT PRIMARY KEY,
    Season VARCHAR(9),
    HomeTeamID INT,
    AwayTeamID INT,
    HomeGoals INT,
    AwayGoals INT,
    HomeTeamRank INT,
    AwayTeamRank INT,
    Result VARCHAR(20),
    MatchDate DATE,
    Attendance INT,
    FOREIGN KEY (HomeTeamID) REFERENCES Teams(TeamID),
    FOREIGN KEY (AwayTeamID) REFERENCES Teams(TeamID)
);

-- Table to store team form (last 5 matches)
CREATE TABLE TeamForm (
    FormID INT AUTO_INCREMENT PRIMARY KEY,
    TeamID INT,
    MatchDate DATE,
    Points INT,
    GoalsScored INT,
    GoalsConceded INT,
    FOREIGN KEY (TeamID) REFERENCES Teams(TeamID)
);

-- Table to store user predictions
CREATE TABLE UserPredictions (
    PredictionID INT AUTO_INCREMENT PRIMARY KEY,
    UserID INT,
    MatchID INT,
    PredictedResult VARCHAR(20),
    Confidence INT,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (MatchID) REFERENCES Matches(MatchID)
);

-- Table to store users
CREATE TABLE Users (
    UserID INT AUTO_INCREMENT PRIMARY KEY,
    Username VARCHAR(50) UNIQUE NOT NULL,
    Email VARCHAR(100) UNIQUE NOT NULL,
    PasswordHash VARCHAR(255) NOT NULL,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to store player statistics
CREATE TABLE PlayerStats (
    StatID INT AUTO_INCREMENT PRIMARY KEY,
    PlayerID INT,
    MatchID INT,
    Goals INT DEFAULT 0,
    Assists INT DEFAULT 0,
    YellowCards INT DEFAULT 0,
    RedCards INT DEFAULT 0,
    MinutesPlayed INT,
    FOREIGN KEY (PlayerID) REFERENCES Players(PlayerID),
    FOREIGN KEY (MatchID) REFERENCES Matches(MatchID)
);

-- Table to store head-to-head records
CREATE TABLE HeadToHead (
    H2HID INT AUTO_INCREMENT PRIMARY KEY,
    Team1ID INT,
    Team2ID INT,
    Team1Wins INT DEFAULT 0,
    Team2Wins INT DEFAULT 0,
    Draws INT DEFAULT 0,
    Team1Goals INT DEFAULT 0,
    Team2Goals INT DEFAULT 0,
    LastUpdated DATE,
    FOREIGN KEY (Team1ID) REFERENCES Teams(TeamID),
    FOREIGN KEY (Team2ID) REFERENCES Teams(TeamID)
);
