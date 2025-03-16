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
