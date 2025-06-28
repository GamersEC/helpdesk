import os
from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Ticket, User
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
app = Flask(__name__)

#Configuración
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una-clave-secreta-muy-dificil-de-adivinar')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://helpdesk:helpdesk123@db:5432/helpdesk_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

#Configuración de Flask-Mail
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'tu_email@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'tu_contraseña_de_aplicacion')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'tu_email@gmail.com')

#inicializar las extensiones
db.init_app(app)
mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

#Rutas publicas (para clientes)

@app.route('/')
def home():
    return redirect(url_for('new_ticket'))

@app.route('/new', methods=['GET', 'POST'])
def new_ticket():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        customer_email = request.form['email']
        priority = request.form['priority']

        new_ticket_obj = Ticket(
            title=title,
            description=description,
            customer_email=customer_email,
            priority=priority
        )
        db.session.add(new_ticket_obj)
        db.session.commit()

        try:
            send_tracking_email(new_ticket_obj)
            flash(f'Ticket creado con éxito. Se ha enviado un correo a {customer_email} con el enlace de seguimiento.', 'success')
        except Exception as e:
            flash('Ticket creado, pero no se pudo enviar el correo de seguimiento. Por favor, contacta a soporte.', 'warning')
            print(f"Error sending email: {e}")

        return redirect(url_for('ticket_created_success', tracking_id=new_ticket_obj.tracking_id))

    return render_template('new_ticket.html')

@app.route('/ticket/<tracking_id>')
def track_ticket(tracking_id):
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first_or_404()
    return render_template('ticket_view.html', ticket=ticket)

@app.route('/success/<tracking_id>')
def ticket_created_success(tracking_id):
    ticket_url = url_for('track_ticket', tracking_id=tracking_id, _external=True)
    return render_template('ticket_created_success.html', ticket_url=ticket_url)


#Rutas de agente (protegidas)

@app.route('/dashboard')
@login_required
def dashboard():
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    return render_template('index.html', tickets=tickets)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/ticket/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    ticket.status = 'Cerrado'
    db.session.commit()
    flash(f'Ticket #{ticket.id} ha sido cerrado.', 'success')
    return redirect(url_for('dashboard'))

#Funciones auxiliares

def send_tracking_email(ticket):
    subject = f"Tu ticket de soporte [#{ticket.id}] ha sido creado"
    tracking_url = url_for('track_ticket', tracking_id=ticket.tracking_id, _external=True)

    msg = Message(subject, recipients=[ticket.customer_email])
    msg.html = render_template('email/tracking_link.html', ticket=ticket, tracking_url=tracking_url)
    mail.send(msg)

#Crear tablas y de administrador inicial si no existen

with app.app_context():
    #1. Crea todas las tablas de la base de datos si no existen
    db.create_all()

    #2. Revisa si se debe crear un usuario admin
    admin_user = os.environ.get('ADMIN_USERNAME')
    admin_pass = os.environ.get('ADMIN_PASSWORD')

    #Condicional para verificar si las variables de entorno están definidas
    if admin_user and admin_pass:
        # Revisa si el usuario ya existe en la base de datos
        if not User.query.filter_by(username=admin_user).first():
            print(f"Admin user '{admin_user}' not found in DB. Creating...")

            #Crea la nueva instancia de usuario
            new_admin = User(username=admin_user)
            new_admin.set_password(admin_pass)

            #Añade y guarda en la base de datos
            db.session.add(new_admin)
            db.session.commit()

            print(f"Admin user '{admin_user}' created successfully from environment variables.")
        else:
            #Si el usuario ya existe, no hace nada y solo informa
            print(f"Admin user '{admin_user}' already exists. Skipping creation.")

#Comando manual opcional para crear usuarios adicionales desde la terminal
@app.cli.command("create-admin")
def create_admin(username, password):
    """Crea un nuevo usuario administrador."""
    if User.query.filter_by(username=username).first():
        print(f"El usuario '{username}' ya existe.")
        return

    admin = User(username=username)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Usuario administrador '{username}' creado con éxito.")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)