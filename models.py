from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime # Importante para la marca de tiempo

db = SQLAlchemy()

# Modelo para los agentes/administradores (sin cambios)
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- NUEVO MODELO PARA LOS COMENTARIOS ---
class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    author_name = db.Column(db.String(100), nullable=False)
    author_type = db.Column(db.String(20), nullable=False, default='Agent')

    # Clave foránea para vincular el comentario a un ticket
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)


# Modelo de Ticket actualizado
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

    # --- RELACIÓN AÑADIDA ---
    # Vincula los tickets con los comentarios, asegurando que se ordenen por fecha.
    comments = db.relationship('Comment', backref='ticket', lazy=True, order_by='Comment.timestamp')