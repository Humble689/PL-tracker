CREATE DATABASE premier_league_stats;
USE premier_league_stats;
-- Table to store teams
CREATE TABLE Teams (
    TeamID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    ShortName VARCHAR(3) NOT NULL,
    Rank INT
);


-- Table to store players
CREATE TABLE Players (
    PlayerID INT AUTO_INCREMENT PRIMARY KEY,
    TeamID INT,
    Name VARCHAR(100) NOT NULL,
    Position VARCHAR(3),
    FOREIGN KEY (TeamID) REFERENCES Teams(TeamID)
);

-- Table to store matches
CREATE TABLE Matches (
    MatchID INT AUTO_INCREMENT PRIMARY KEY,
    Season VARCHAR(9),
    HomeTeamID INT,
    AwayTeamID INT,
    HomeGoals INT,
    AwayGoals INT,
    HomeTeamRank INT,
    AwayTeamRank INT,
    Result VARCHAR(10),
    MatchDate DATE,


    FOREIGN KEY (HomeTeamID) REFERENCES Teams(TeamID),
    FOREIGN KEY (AwayTeamID) REFERENCES Teams(TeamID)
);

-- Table to store player statistics per match
CREATE TABLE PlayerStats (
    StatID INT AUTO_INCREMENT PRIMARY KEY,
    MatchID INT,
    PlayerID INT,
    MinutesPlayed INT,
    Goals INT,
    Assists INT,
    FOREIGN KEY (MatchID) REFERENCES Matches(MatchID),
    FOREIGN KEY (PlayerID) REFERENCES Players(PlayerID)
);
