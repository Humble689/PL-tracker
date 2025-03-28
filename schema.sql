-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create teams table
CREATE TABLE IF NOT EXISTS teams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    short_name VARCHAR(3) NOT NULL,
    team_rank INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create matches table
CREATE TABLE IF NOT EXISTS matches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    season VARCHAR(9) NOT NULL,
    home_team_id INT NOT NULL,
    away_team_id INT NOT NULL,
    home_goals INT DEFAULT 0,
    away_goals INT DEFAULT 0,
    home_team_rank INT DEFAULT 0,
    away_team_rank INT DEFAULT 0,
    result VARCHAR(20) NOT NULL DEFAULT 'Scheduled',
    match_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (home_team_id) REFERENCES teams(id),
    FOREIGN KEY (away_team_id) REFERENCES teams(id)
);

-- Create predictions table
CREATE TABLE IF NOT EXISTS predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    match_id INT NOT NULL,
    predicted_result VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (match_id) REFERENCES matches(id)
);

-- Insert some sample teams
INSERT INTO teams (name, short_name, team_rank) VALUES
('Arsenal', 'ARS', 1),
('Aston Villa', 'AVL', 2),
('Brighton', 'BHA', 3),
('Burnley', 'BUR', 4),
('Chelsea', 'CHE', 5),
('Crystal Palace', 'CRY', 6),
('Everton', 'EVE', 7),
('Leeds', 'LEE', 8),
('Leicester', 'LEI', 9),
('Liverpool', 'LIV', 10),
('Manchester City', 'MCI', 11),
('Manchester United', 'MUN', 12),
('Newcastle', 'NEW', 13),
('Norwich', 'NOR', 14),
('Southampton', 'SOU', 15),
('Tottenham', 'TOT', 16),
('Watford', 'WAT', 17),
('West Ham', 'WHU', 18),
('Wolves', 'WOL', 19),
('Brentford', 'BRE', 20); 