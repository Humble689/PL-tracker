from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

class Match(db.Model):
    __tablename__ = 'matches'
    
    id = db.Column(db.Integer, primary_key=True)
    match_date = db.Column(db.Date, nullable=False)
    home_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    away_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    home_score = db.Column(db.Integer)
    away_score = db.Column(db.Integer)
    result = db.Column(db.String(10))  # 'Home Win', 'Draw', 'Away Win'
    
    # Relationships
    home_team = db.relationship('Team', foreign_keys=[home_team_id], backref='home_matches')
    away_team = db.relationship('Team', foreign_keys=[away_team_id], backref='away_matches')
    
    @property
    def HomeTeamName(self):
        return self.home_team.name
    
    @property
    def AwayTeamName(self):
        return self.away_team.name

class Team(db.Model):
    __tablename__ = 'teams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    short_name = db.Column(db.String(3), nullable=False)

class UserPrediction(db.Model):
    __tablename__ = 'user_predictions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    prediction = db.Column(db.String(10), nullable=False)  # 'Home Win', 'Draw', 'Away Win'
    predicted_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('predictions', lazy=True))
    match = db.relationship('Match', backref=db.backref('user_predictions', lazy=True))
    
    def __repr__(self):
        return f'<UserPrediction {self.user.username} - {self.match.HomeTeamName} vs {self.match.AwayTeamName}>' 