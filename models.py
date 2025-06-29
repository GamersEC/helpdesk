from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime
import pytz

#Definimos la zona horaria UTC para consistencia
UTC = pytz.UTC

def get_utc_now():
    """Devuelve la fecha y hora actual en UTC, consciente de la zona horaria."""
    return datetime.now(UTC)

db = SQLAlchemy()

#Modelo para los agentes/administradores
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False, default='agent')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

#Modelo para los comentarios
class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    author_name = db.Column(db.String(100), nullable=False)
    author_type = db.Column(db.String(20), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)

#Modelo para Archivos Adjuntos
class Attachment(db.Model):
    __tablename__ = 'attachments'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)

#Modelo de Ticket actualizado
class Ticket(db.Model):
    __tablename__ = 'ticket'
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    tracking_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Abierto', nullable=False)
    priority = db.Column(db.String(20), default='Baja', nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now)
    last_updated_by_type = db.Column(db.String(20), nullable=False, default='Customer')
    assigned_agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_agent = db.relationship('User', backref='assigned_tickets', foreign_keys=[assigned_agent_id])

    comments = db.relationship('Comment', backref='ticket', lazy=True, order_by='Comment.timestamp')
    attachments = db.relationship('Attachment', backref='ticket', lazy=True, cascade="all, delete-orphan")