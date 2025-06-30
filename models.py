from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime
import pytz

UTC = pytz.UTC

def get_utc_now():
    """Retorna la fecha y hora actual en UTC con zona horaria."""
    return datetime.now(UTC)

db = SQLAlchemy()


#Modelos de la aplicacion
class Setting(db.Model):
    #Almacena la configuración general de la aplicación en la base de datos
    __tablename__ = 'settings'
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(255), nullable=True)


class Area(db.Model):
    __tablename__ = 'areas'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    #Guarda el ID del último agente al que se le asignó un ticket para el round-robin
    last_assigned_agent_id = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_area_last_assigned_agent'), nullable=True)


#Define las categorias predefinidas que un cliente puede seleccionar
class TicketCategory(db.Model):
    __tablename__ = 'ticket_categories'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), unique=True, nullable=False)
    priority = db.Column(db.String(20), nullable=False, default='Baja')
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    area = db.relationship('Area', backref='ticket_categories')


#Modelo para agentes y administradores
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False, default='agent')
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=True)
    area = db.relationship('Area', backref='agents', foreign_keys=[area_id])
    password_reset_required = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'


#Almacena los comentarios de clientes y agentes en un ticket
class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    author_name = db.Column(db.String(100), nullable=False)
    author_type = db.Column(db.String(20), nullable=False) # 'Customer' o 'Agent'
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)

    @property
    def meta(self):
        #Propiedad para identificar el tipo de objeto en plantillas Jinja2.
        return {'model': 'Comment'}


class Attachment(db.Model):
    #Almacena los archivos adjuntos a un ticket
    __tablename__ = 'attachments'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)


#Modelo principal que representa un ticket de soporte
class Ticket(db.Model):
    __tablename__ = 'ticket'
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    tracking_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: f"HD-{str(uuid.uuid4()).upper()[:8]}")
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Abierto', nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=get_utc_now)
    last_updated = db.Column(db.DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_updated_by_type = db.Column(db.String(20), nullable=False, default='Customer')
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id'), nullable=False)
    area = db.relationship('Area', backref='tickets', foreign_keys=[area_id])
    assigned_agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_agent = db.relationship('User', backref='assigned_tickets', foreign_keys=[assigned_agent_id])

    #Relaciones para acceder a los comentarios, adjuntos y logs de actividad
    comments = db.relationship('Comment', backref='ticket', lazy=True, order_by='Comment.timestamp', cascade="all, delete-orphan")
    attachments = db.relationship('Attachment', backref='ticket', lazy=True, cascade="all, delete-orphan")
    activity_logs = db.relationship('ActivityLog', backref='ticket', lazy=True, order_by='ActivityLog.timestamp', cascade="all, delete-orphan")


#Registra las acciones importantes que ocurren en un ticket
class ActivityLog(db.Model):
    __tablename__ = "activity_log"
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)

    #Timestamp de la actividad
    timestamp = db.Column(db.DateTime(timezone=True), default=get_utc_now)

    @property
    def meta(self):
        #Propiedad para identificar el tipo de objeto en plantillas Jinja2.
        return {'model': 'ActivityLog'}