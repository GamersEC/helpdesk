import os
import random
import shutil
import string
from io import BytesIO
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, send_from_directory, send_file
)
from sqlalchemy import case # <-- ¡NUEVA IMPORTACIÓN!
from models import db, Ticket, User, Comment, Attachment, get_utc_now
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from datetime import timedelta
import pytz
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)

#Configuracion
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una-clave-secreta-muy-dificil-de-adivinar')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://helpdesk:helpdesk123@db:5432/helpdesk_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'tu_email@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'tu_contraseña_de_aplicacion')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'tu_email@gmail.com')

#Inicializar extensiones
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

#Decorador de permisos de administrador
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("No tienes permiso para acceder a esta página.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

#Filtros y funciones auxiliares
@app.template_filter('local_time')
def format_datetime_local(utc_dt):
    if not utc_dt: return ""
    local_tz_name = os.environ.get('APP_TIMEZONE', 'UTC')
    try: local_tz = pytz.timezone(local_tz_name)
    except pytz.UnknownTimeZoneError: local_tz = pytz.utc
    local_dt = utc_dt.astimezone(local_tz)
    return local_dt.strftime('%d-%m-%Y %H:%M %Z')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def auto_close_inactive_tickets():
    print("Checking for inactive tickets to auto-close...")
    time_limit = get_utc_now() - timedelta(days=3)
    tickets_to_close = Ticket.query.filter(Ticket.status == 'Abierto', Ticket.last_updated_by_type == 'Agent', Ticket.last_updated < time_limit).all()
    if not tickets_to_close: return 0
    for ticket in tickets_to_close:
        ticket.status = 'Cerrado'
        system_comment = Comment(content="Este ticket ha sido cerrado automáticamente después de 72 horas de inactividad.", ticket_id=ticket.id, author_name="Sistema", author_type="Agent")
        db.session.add(system_comment)
    db.session.commit()
    print(f"Auto-closed {len(tickets_to_close)} ticket(s).")
    return len(tickets_to_close)

def cleanup_old_attachments():
    print("Checking for old attachments to clean up...")
    cleanup_limit = get_utc_now() - timedelta(days=7)
    tickets_to_clean = Ticket.query.filter(Ticket.status == 'Cerrado', Ticket.last_updated < cleanup_limit, Ticket.attachments.any()).all()
    cleaned_count = 0
    for ticket in tickets_to_clean:
        ticket_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], str(ticket.id))
        if os.path.exists(ticket_upload_path):
            try:
                shutil.rmtree(ticket_upload_path)
                print(f"Deleted attachment folder: {ticket_upload_path}")
                cleaned_count += 1
            except OSError as e:
                print(f"Error deleting folder {ticket_upload_path}: {e.strerror}")
        for attachment in ticket.attachments:
            db.session.delete(attachment)
    db.session.commit()
    return cleaned_count

#Ruta del captcha
@app.route('/captcha')
def captcha_image():
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    session['captcha_code'] = captcha_text
    image = Image.new('RGB', (150, 50), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    try:
        font_path = os.path.join(app.root_path, 'assets', 'Roboto-Regular.ttf')
        font = ImageFont.truetype(font_path, 36)
    except IOError:
        font = ImageFont.load_default()
    for i, char in enumerate(captcha_text):
        draw.text((10 + i * 35 + random.randint(-5, 5), random.randint(-5, 5)), char, font=font, fill=(50, 50, 50))
    for _ in range(5):
        draw.line(((random.randint(0, 150), random.randint(0, 50)), (random.randint(0, 150), random.randint(0, 50))), fill=(150, 150, 150), width=1)
    image = image.filter(ImageFilter.GaussianBlur(1))
    buffer = BytesIO()
    image.save(buffer, 'PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png')

#Rutas publicas
@app.route('/')
def home():
    return redirect(url_for('new_ticket'))

@app.route('/new', methods=['GET', 'POST'])
def new_ticket():
    if request.method == 'POST':
        captcha_answer = request.form.get('captcha', '').strip().upper()
        if 'captcha_code' not in session or not captcha_answer or captcha_answer != session['captcha_code']:
            flash('El código de verificación es incorrecto.', 'danger')
            return redirect(url_for('new_ticket'))
        files = request.files.getlist('attachments')
        if len(files) > 2:
            flash('No puedes subir más de 2 imágenes.', 'danger')
            return redirect(url_for('new_ticket'))
        for file in files:
            if file and not allowed_file(file.filename):
                flash('Solo se permiten imágenes (png, jpg, jpeg, gif).', 'danger')
                return redirect(url_for('new_ticket'))
        customer_name = request.form['name']
        title = request.form['title']
        description = request.form['description']
        customer_email = request.form['email']
        priority = request.form['priority']
        new_ticket_obj = Ticket(
            customer_name=customer_name, title=title, description=description,
            customer_email=customer_email, priority=priority,
            last_updated_by_type='Customer', last_updated=get_utc_now()
        )
        db.session.add(new_ticket_obj)
        db.session.flush()
        for file in files:
            if file:
                filename = secure_filename(file.filename)
                ticket_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], str(new_ticket_obj.id))
                os.makedirs(ticket_upload_path, exist_ok=True)
                file.save(os.path.join(ticket_upload_path, filename))
                attachment = Attachment(filename=filename, ticket_id=new_ticket_obj.id)
                db.session.add(attachment)
        db.session.commit()
        session.pop('captcha_code', None)
        try:
            send_tracking_email(new_ticket_obj)
            flash(f'¡Gracias {customer_name}, tu ticket fue creado con éxito!', 'success')
        except Exception as e:
            flash('Ticket creado, pero no se pudo enviar el correo de seguimiento.', 'warning')
            print(f"Error sending email: {e}")
        return redirect(url_for('ticket_created_success', tracking_id=new_ticket_obj.tracking_id))
    return render_template('new_ticket.html')

@app.route('/uploads/<int:ticket_id>/<filename>')
def uploaded_file(ticket_id, filename):
    if current_user.is_authenticated:
        ticket_upload_path = os.path.join(os.getcwd(), app.config['UPLOAD_FOLDER'], str(ticket_id))
        return send_from_directory(ticket_upload_path, filename)
    if 'viewed_ticket_id' in session and session['viewed_ticket_id'] == ticket_id:
        ticket_upload_path = os.path.join(os.getcwd(), app.config['UPLOAD_FOLDER'], str(ticket_id))
        return send_from_directory(ticket_upload_path, filename)
    flash('No tienes permiso para ver este archivo.', 'danger')
    return redirect(url_for('home'))

@app.route('/ticket/<tracking_id>')
def track_ticket(tracking_id):
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first_or_404()
    session['viewed_ticket_id'] = ticket.id
    agents_data = []
    if current_user.is_authenticated:
        all_agents = User.query.all()
        for agent in all_agents:
            ticket_count = Ticket.query.filter_by(assigned_agent_id=agent.id, status='Abierto').count()
            agents_data.append({'agent': agent, 'ticket_count': ticket_count})
    return render_template('ticket_view.html', ticket=ticket, agents_data=agents_data)

@app.route('/ticket/<tracking_id>/reply', methods=['POST'])
def reply_ticket(tracking_id):
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first_or_404()
    reply_text = request.form.get('reply')
    if reply_text:
        new_comment = Comment(content=reply_text, ticket_id=ticket.id, author_name=ticket.customer_name, author_type='Customer')
        db.session.add(new_comment)
        ticket.last_updated_by_type = 'Customer'
        ticket.last_updated = get_utc_now()
        db.session.commit()
        flash('Tu respuesta ha sido enviada.', 'success')
    else:
        flash('No puedes enviar una respuesta vacía.', 'warning')
    return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))

@app.route('/search', methods=['POST'])
def search_ticket():
    tracking_id = request.form.get('tracking_id', '').strip()
    if not tracking_id:
        flash('Por favor, ingresa un ID de seguimiento.', 'warning')
        return redirect(url_for('home'))
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first()
    if ticket:
        return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))
    else:
        flash(f'No se encontró ningún ticket con el ID "{tracking_id}".', 'danger')
        return redirect(url_for('home'))

@app.route('/success/<tracking_id>')
def ticket_created_success(tracking_id):
    ticket_url = url_for('track_ticket', tracking_id=tracking_id, _external=True)
    return render_template('ticket_created_success.html', ticket_url=ticket_url)

#Rutas de agente y administrador
@app.route('/admin/agents', methods=['GET', 'POST'])
@admin_required
def manage_agents():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('El nombre de usuario y la contraseña son obligatorios.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Ese nombre de usuario ya existe.', 'warning')
        else:
            new_agent = User(username=username, first_name=request.form.get('first_name'), last_name=request.form.get('last_name'))
            new_agent.set_password(password)
            db.session.add(new_agent)
            db.session.commit()
            flash(f'Agente "{username}" creado con éxito.', 'success')
        return redirect(url_for('manage_agents'))
    agents_with_counts = []
    all_agents = User.query.all()
    for agent in all_agents:
        ticket_count = Ticket.query.filter_by(assigned_agent_id=agent.id, status='Abierto').count()
        agents_with_counts.append({'agent': agent, 'ticket_count': ticket_count})
    return render_template('manage_agents.html', agents_data=agents_with_counts)

@app.route('/dashboard')
@login_required
def dashboard():
    closed_count = auto_close_inactive_tickets()
    cleaned_count = cleanup_old_attachments()
    if closed_count > 0:
        flash(f'{closed_count} ticket(s) han sido cerrados automáticamente.', 'info')
    if cleaned_count > 0:
        flash(f'Se han limpiado los adjuntos de {cleaned_count} ticket(s) antiguos.', 'secondary')

    priority_order = case(
        (Ticket.priority == 'Alta', 1),
        (Ticket.priority == 'Media', 2),
        (Ticket.priority == 'Baja', 3),
        else_=4
    )

    if current_user.is_admin:
        tickets = Ticket.query.order_by(
            Ticket.status.asc(), priority_order.asc(), Ticket.last_updated.desc()
        ).all()
    else:
        tickets = Ticket.query.filter(
            (Ticket.assigned_agent_id == current_user.id) | (Ticket.assigned_agent_id == None)
        ).order_by(
            Ticket.status.asc(), priority_order.asc(), Ticket.last_updated.desc()
        ).all()

    return render_template('index.html', tickets=tickets)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
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

@app.route('/profile')
@login_required
def view_profile():
    return render_template('profile.html', user=current_user, is_editable=False)

@app.route('/admin/edit_agent/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_agent(user_id):
    agent_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        agent_to_edit.first_name = request.form.get('first_name')
        agent_to_edit.last_name = request.form.get('last_name')
        agent_to_edit.username = request.form.get('username')
        agent_to_edit.role = request.form.get('role')
        new_password = request.form.get('password')
        if new_password:
            agent_to_edit.set_password(new_password)
        db.session.commit()
        flash(f'Perfil del agente {agent_to_edit.username} actualizado.', 'success')
        return redirect(url_for('manage_agents'))
    return render_template('profile.html', user=agent_to_edit, is_editable=True)

@app.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    comment_text = request.form.get('comment')
    if comment_text:
        if not ticket.assigned_agent_id:
            ticket.assigned_agent_id = current_user.id
            flash(f'Te has asignado automáticamente el ticket #{ticket.id}.', 'info')
        new_comment = Comment(content=comment_text, ticket_id=ticket.id, author_name=current_user.username, author_type='Agent')
        db.session.add(new_comment)
        ticket.last_updated_by_type = 'Agent'
        ticket.last_updated = get_utc_now()
        db.session.commit()
        flash('Tu respuesta ha sido añadida con éxito.', 'success')
    else:
        flash('No puedes enviar una respuesta vacía.', 'warning')
    return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))

@app.route('/ticket/<int:ticket_id>/assign', methods=['POST'])
@admin_required
def assign_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    agent_id = request.form.get('agent_id')
    if agent_id:
        agent = User.query.get(agent_id)
        if agent:
            ticket.assigned_agent_id = agent.id
            db.session.commit()
            flash(f'Ticket #{ticket.id} asignado a {agent.username}.', 'success')
        else:
            flash('El agente seleccionado no es válido.', 'danger')
    else:
        ticket.assigned_agent_id = None
        db.session.commit()
        flash(f'Ticket #{ticket.id} ha quedado sin asignar.', 'info')
    return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))

@app.route('/ticket/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    ticket.status = 'Cerrado'
    db.session.add(Comment(content='El ticket ha sido marcado como cerrado.', ticket_id=ticket.id, author_name=current_user.username, author_type='Agent'))
    db.session.commit()
    flash(f'Ticket #{ticket.id} ha sido cerrado.', 'success')
    return redirect(url_for('dashboard'))

def send_tracking_email(ticket):
    subject = f"Tu ticket de soporte [#{ticket.id}] ha sido creado"
    tracking_url = url_for('track_ticket', tracking_id=ticket.tracking_id, _external=True)
    msg = Message(subject, recipients=[ticket.customer_email])
    msg.html = render_template('email/tracking_link.html', ticket=ticket, tracking_url=tracking_url)
    mail.send(msg)

#Inicializacion de la app
with app.app_context():
    db.create_all()
    admin_user = os.environ.get('ADMIN_USERNAME')
    admin_pass = os.environ.get('ADMIN_PASSWORD')
    if admin_user and admin_pass and not User.query.filter_by(username=admin_user).first():
        new_admin = User(username=admin_user, role='admin')
        new_admin.set_password(admin_pass)
        db.session.add(new_admin)
        db.session.commit()
        print(f"Admin user '{admin_user}' creado con éxito.")

@app.cli.command("create-admin")
def create_admin(username, password):
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