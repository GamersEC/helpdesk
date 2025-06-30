import os
import random
import shutil
import string
import json
from io import BytesIO
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, send_file, g, jsonify)
from sqlalchemy import case, func, cast
from sqlalchemy.types import String
from jinja2.exceptions import TemplateNotFound
from models import db, Ticket, User, Comment, Attachment, Area, TicketCategory, Setting, get_utc_now, ActivityLog
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from datetime import timedelta
import pytz
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)

@app.context_processor
def inject_utility_functions():
    from models import get_utc_now
    return dict(get_utc_now=get_utc_now)


#Configuracion basica
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una-clave-secreta-muy-dificil-de-adivinar')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://helpdesk:helpdesk123@db:5432/helpdesk_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


#Inicializar extensiones
db.init_app(app)
mail = Mail()
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "info"


#Logica de instalación y configuración
def is_installed():
    return db.session.query(User.query.filter_by(role='admin').exists()).scalar()

def load_app_config(app_instance):
    if not hasattr(g, 'settings_loaded'):
        settings = Setting.query.all()
        config = {s.key: s.value for s in settings}
        app_instance.config.update(
            MAIL_SERVER=config.get('MAIL_SERVER'),
            MAIL_PORT=int(config.get('MAIL_PORT', 587)),
            MAIL_USE_TLS=config.get('MAIL_USE_TLS', 'true').lower() == 'true',
            MAIL_USERNAME=config.get('MAIL_USERNAME'),
            MAIL_PASSWORD=config.get('MAIL_PASSWORD'),
            MAIL_DEFAULT_SENDER=config.get('MAIL_USERNAME'),
            APP_TIMEZONE=config.get('APP_TIMEZONE', 'UTC'),
            APP_NAME=config.get('APP_NAME', 'Soporte Helpdesk')
        )
        mail.init_app(app_instance)
        g.settings_loaded = True

@app.before_request
def before_request_handler():
    if request.endpoint in ['install_wizard', 'static', 'test_smtp']:
        return
    with app.app_context():
        if not is_installed():
            return redirect(url_for('install_wizard'))
    load_app_config(app)
    if (current_user.is_authenticated and current_user.password_reset_required and
            not current_user.is_admin and request.endpoint not in ['change_password', 'logout']):
        return redirect(url_for('change_password'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("No tienes permiso para acceder a esta página.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('local_time')
def format_datetime_local(utc_dt):
    if not utc_dt: return ""
    local_tz_name = app.config.get('APP_TIMEZONE', 'UTC')
    try: local_tz = pytz.timezone(local_tz_name)
    except pytz.UnknownTimeZoneError: local_tz = pytz.utc
    local_dt = utc_dt.astimezone(local_tz)
    return local_dt.strftime('%d-%m-%Y %H:%M')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def auto_close_inactive_tickets():
    time_limit = get_utc_now() - timedelta(days=3)
    tickets_to_close = Ticket.query.filter(Ticket.status == 'Abierto', Ticket.last_updated_by_type == 'Agent', Ticket.last_updated < time_limit).all()
    if not tickets_to_close: return 0
    for ticket in tickets_to_close:
        ticket.status = 'Cerrado'; ticket.closed_at = get_utc_now()
        db.session.add(Comment(content="Este ticket ha sido cerrado automáticamente por inactividad.", ticket_id=ticket.id, author_name="Sistema", author_type="Agent"))
        db.session.add(ActivityLog(ticket_id=ticket.id, description="Ticket cerrado automáticamente por inactividad."))
    db.session.commit()
    return len(tickets_to_close)

def cleanup_old_attachments():
    cleanup_limit = get_utc_now() - timedelta(days=7)
    tickets_to_clean = Ticket.query.filter(Ticket.status == 'Cerrado', Ticket.closed_at.isnot(None), Ticket.closed_at < cleanup_limit, Ticket.attachments.any()).all()
    cleaned_count = 0
    for ticket in tickets_to_clean:
        ticket_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], str(ticket.id))
        if os.path.exists(ticket_upload_path):
            try: shutil.rmtree(ticket_upload_path); cleaned_count += 1
            except OSError as e: print(f"Error al eliminar la carpeta {ticket_upload_path}: {e.strerror}")
        for attachment in ticket.attachments: db.session.delete(attachment)
    if cleaned_count > 0: db.session.commit()
    return cleaned_count

def send_email_notification(recipients, subject_template, html_template, **kwargs):
    sender_email = app.config.get('MAIL_USERNAME')
    if not sender_email:
        print("ERROR: MAIL_USERNAME no está configurado. No se pueden enviar correos.")
        return
    try:
        subject = render_template(subject_template, **kwargs)
        html_body = render_template(html_template, **kwargs)
        sender_name = app.config.get('APP_NAME', 'Soporte Helpdesk')
        msg = Message(subject.strip(), sender=(sender_name, sender_email), recipients=recipients)
        msg.html = html_body
        mail.send(msg)
    except TemplateNotFound as e: print(f"ERROR_SENDING_EMAIL: No se encontró la plantilla de correo: {e}")
    except Exception as e: print(f"ERROR_SENDING_EMAIL: to {recipients} with subject {subject_template}: {e}")

@app.route('/captcha')
def captcha_image():
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    session['captcha_code'] = captcha_text
    image = Image.new('RGB', (150, 50), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    try: font = ImageFont.truetype(os.path.join(app.root_path, 'assets', 'Roboto-Regular.ttf'), 36)
    except IOError: font = ImageFont.load_default()
    for i, char in enumerate(captcha_text):
        draw.text((10 + i * 35 + random.randint(-5, 5), random.randint(-5, 5)), char, font=font, fill=(50, 50, 50))
    for _ in range(5):
        draw.line(((random.randint(0, 150), random.randint(0, 50)), (random.randint(0, 150), random.randint(0, 50))), fill=(150, 150, 150), width=1)
    image = image.filter(ImageFilter.GaussianBlur(1))
    buffer = BytesIO(); image.save(buffer, 'PNG'); buffer.seek(0)
    return send_file(buffer, mimetype='image/png')

@app.route('/install', methods=['GET', 'POST'])
def install_wizard():
    if is_installed(): return redirect(url_for('home'))
    if request.method == 'POST':
        try:
            admin_username = request.form.get('admin_username')
            admin_email = request.form.get('admin_email')
            admin_password = request.form.get('admin_password')
            if not all([admin_username, admin_email, admin_password]):
                flash('Los campos del administrador son obligatorios.', 'danger'); return render_template('install/setup.html')
            admin = User(username=admin_username, email=admin_email, role='admin', password_reset_required=False)
            admin.set_password(admin_password)
            db.session.add(admin)
            settings_to_save = {'APP_NAME': request.form.get('app_name'),'APP_TIMEZONE': request.form.get('app_timezone'),'MAIL_SERVER': request.form.get('mail_server'),'MAIL_PORT': request.form.get('mail_port'),'MAIL_USERNAME': request.form.get('mail_username'),'MAIL_PASSWORD': request.form.get('mail_password'),'MAIL_USE_TLS': 'true' if request.form.get('mail_use_tls') else 'false'}
            for key, value in settings_to_save.items():
                if value is not None: db.session.add(Setting(key=key, value=value))
            created_areas = {}
            area_names = request.form.getlist('area_names[]')
            for name in area_names:
                if name.strip() and name.strip() not in created_areas:
                    new_area = Area(name=name.strip()); db.session.add(new_area); created_areas[name.strip()] = new_area
            db.session.flush()
            category_titles, category_priorities, category_areas = request.form.getlist('category_titles[]'), request.form.getlist('category_priorities[]'), request.form.getlist('category_areas[]')
            for title, priority, area_name in zip(category_titles, category_priorities, category_areas):
                if title.strip() and area_name.strip():
                    area_obj = created_areas.get(area_name.strip())
                    if area_obj: db.session.add(TicketCategory(title=title.strip(), priority=priority, area_id=area_obj.id))
            agent_usernames, agent_emails, agent_passwords, agent_areas = request.form.getlist('agent_usernames[]'), request.form.getlist('agent_emails[]'), request.form.getlist('agent_passwords[]'), request.form.getlist('agent_areas[]')
            for username, email, password, area_name in zip(agent_usernames, agent_emails, agent_passwords, agent_areas):
                if username.strip() and email.strip() and password.strip():
                    area_obj = created_areas.get(area_name.strip())
                    new_agent = User(username=username.strip(), email=email.strip(), area_id=area_obj.id if area_obj else None, password_reset_required=True)
                    new_agent.set_password(password); db.session.add(new_agent)
            db.session.commit()
            flash('¡Instalación completada! Por favor, inicia sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback(); flash(f'Error durante la instalación: {e}', 'danger'); print(f"INSTALLATION ERROR: {e}")
    return render_template('install/setup.html')

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/new', methods=['GET', 'POST'])
def new_ticket():
    if request.method == 'POST':
        captcha_answer = request.form.get('captcha', '').strip().upper()
        if 'captcha_code' not in session or not captcha_answer or captcha_answer != session['captcha_code']:
            flash('El código de verificación es incorrecto.', 'danger'); return redirect(url_for('new_ticket'))
        category_id = request.form.get('category_id')
        if not category_id: flash('Debes seleccionar una categoría.', 'danger'); return redirect(url_for('new_ticket'))
        category = TicketCategory.query.get(category_id)
        if not category: flash('La categoría seleccionada no es válida.', 'danger'); return redirect(url_for('new_ticket'))
        files = request.files.getlist('attachments')
        if len(files) > 2: flash('No puedes subir más de 2 imágenes.', 'danger'); return redirect(url_for('new_ticket'))
        for file in files:
            if file and not allowed_file(file.filename): flash('Solo se permiten imágenes.', 'danger'); return redirect(url_for('new_ticket'))
        target_area = category.area; assigned_agent = None
        agents_in_area = User.query.filter(User.area_id == target_area.id, User.role == 'agent').order_by(User.id).all()
        if agents_in_area:
            last_agent_id = target_area.last_assigned_agent_id; last_index = -1
            if last_agent_id:
                try: last_index = [agent.id for agent in agents_in_area].index(last_agent_id)
                except ValueError: last_index = -1
            next_index = (last_index + 1) % len(agents_in_area); assigned_agent = agents_in_area[next_index]
            target_area.last_assigned_agent_id = assigned_agent.id
        new_ticket_obj = Ticket(customer_name=request.form['name'], customer_email=request.form['email'], description=request.form['description'], title=category.title, priority=category.priority, area_id=category.area_id, assigned_agent_id=assigned_agent.id if assigned_agent else None)
        db.session.add(new_ticket_obj); db.session.flush()
        db.session.add(ActivityLog(ticket_id=new_ticket_obj.id, description=f"Ticket creado por el cliente '{new_ticket_obj.customer_name}'"))
        if assigned_agent: db.session.add(ActivityLog(ticket_id=new_ticket_obj.id, description=f"Ticket asignado automáticamente a {assigned_agent.username}"))
        for file in files:
            if file:
                filename = secure_filename(file.filename)
                ticket_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], str(new_ticket_obj.id))
                os.makedirs(ticket_upload_path, exist_ok=True)
                file.save(os.path.join(ticket_upload_path, filename)); db.session.add(Attachment(filename=filename, ticket_id=new_ticket_obj.id))
        db.session.commit(); session.pop('captcha_code', None)
        try:
            send_email_notification(recipients=[new_ticket_obj.customer_email], subject_template='email/subjects/new_ticket_customer.txt', html_template='email/new_ticket_customer.html', ticket=new_ticket_obj)
            if assigned_agent: send_email_notification(recipients=[assigned_agent.email], subject_template='email/subjects/new_assignment_agent.txt', html_template='email/new_assignment_agent.html', ticket=new_ticket_obj, agent=assigned_agent)
        except Exception as e:
            print(f"ERROR CRÍTICO AL LLAMAR A send_email_notification: {e}")
        return redirect(url_for('ticket_created_success', tracking_id=new_ticket_obj.tracking_id))
    categories = TicketCategory.query.order_by(TicketCategory.title).all()
    return render_template('new_ticket.html', categories=categories)

@app.route('/uploads/<int:ticket_id>/<filename>')
def uploaded_file(ticket_id, filename):
    if current_user.is_authenticated or ('viewed_ticket_id' in session and session['viewed_ticket_id'] == ticket_id):
        return send_from_directory(os.path.join(os.getcwd(), app.config['UPLOAD_FOLDER'], str(ticket_id)), filename)
    flash('No tienes permiso para ver este archivo.', 'danger'); return redirect(url_for('home'))

@app.route('/ticket/<tracking_id>')
def track_ticket(tracking_id):
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first_or_404()
    session['viewed_ticket_id'] = ticket.id
    agents = User.query.filter_by(role='agent').order_by(User.username).all() if current_user.is_authenticated and current_user.is_admin else None
    return render_template('ticket_view.html', ticket=ticket, agents=agents)

@app.route('/ticket/<tracking_id>/reply', methods=['POST'])
def reply_ticket(tracking_id):
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first_or_404()
    reply_text = request.form.get('reply')
    if reply_text:
        new_comment = Comment(content=reply_text, ticket_id=ticket.id, author_name=ticket.customer_name, author_type='Customer')
        db.session.add(new_comment)
        ticket.last_updated_by_type = 'Customer'; ticket.last_updated = get_utc_now()
        db.session.add(ActivityLog(ticket_id=ticket.id, description=f"El cliente '{ticket.customer_name}' ha respondido."))
        db.session.commit()
        if ticket.assigned_agent and ticket.assigned_agent.email:
            send_email_notification(recipients=[ticket.assigned_agent.email], subject_template='email/subjects/customer_reply.txt', html_template='email/customer_reply.html', ticket=ticket, comment=new_comment)
        flash('Tu respuesta ha sido enviada.', 'success')
    else: flash('No puedes enviar una respuesta vacía.', 'warning')
    return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))

@app.route('/ticket/<tracking_id>/customer-close', methods=['POST'])
def customer_close_ticket(tracking_id):
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first_or_404()
    if ticket.status == 'Abierto':
        ticket.status = 'Cerrado'; ticket.closed_at = get_utc_now()
        db.session.add(Comment(content="El ticket ha sido cerrado por el cliente.", ticket_id=ticket.id, author_name=ticket.customer_name, author_type='Customer'))
        db.session.add(ActivityLog(ticket_id=ticket.id, description=f"Ticket cerrado por el cliente '{ticket.customer_name}'."))
        db.session.commit()
        flash('Gracias por confirmar. El ticket ha sido cerrado.', 'success')
    return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))

@app.route('/search', methods=['POST'])
def search_ticket():
    tracking_id = request.form.get('tracking_id', '').strip()
    if not tracking_id: flash('Por favor, ingresa un ID de seguimiento.', 'warning'); return redirect(url_for('home'))
    ticket = Ticket.query.filter_by(tracking_id=tracking_id).first()
    if ticket: return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))
    else: flash(f'No se encontró ningún ticket con el ID "{tracking_id}".', 'danger'); return redirect(url_for('home'))

@app.route('/success/<tracking_id>')
def ticket_created_success(tracking_id):
    ticket_url = url_for('track_ticket', tracking_id=tracking_id, _external=True)
    return render_template('ticket_created_success.html', ticket_url=ticket_url)

@app.route('/dashboard')
@login_required
def dashboard():
    closed_count = auto_close_inactive_tickets()
    cleaned_count = cleanup_old_attachments()
    if closed_count > 0: flash(f'{closed_count} ticket(s) han sido cerrados automáticamente.', 'info')
    if cleaned_count > 0: flash(f'Se han limpiado los adjuntos de {cleaned_count} ticket(s) antiguos.', 'secondary')
    if current_user.is_admin:
        stats_data = {'total_open': Ticket.query.filter_by(status='Abierto').count(),'unassigned': Ticket.query.filter(Ticket.status == 'Abierto', Ticket.assigned_agent_id == None).count(),'high_priority': Ticket.query.filter_by(status='Abierto', priority='Alta').count(),'recent_activity': ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(5).all()}
        return render_template('admin/admin_dashboard.html', stats=stats_data)
    else:
        query = request.args.get('query', '')
        # *** CORRECCIÓN: Se usa get() con valor por defecto para el status ***
        status_filter = request.args.get('status', 'Abierto')
        page = request.args.get('page', 1, type=int)
        priority_order = case((Ticket.priority == 'Alta', 1), (Ticket.priority == 'Media', 2), (Ticket.priority == 'Baja', 3), else_=4)
        base_query = Ticket.query.filter(Ticket.assigned_agent_id == current_user.id)
        if query:
            search_term = f"%{query}%"

            #Busqueda por ID, título, nombre del cliente o ID de seguimiento
            base_query = base_query.filter(db.or_(
                cast(Ticket.id, String).like(search_term),
                Ticket.title.ilike(search_term),
                Ticket.customer_name.ilike(search_term),
                Ticket.tracking_id.ilike(search_term)
            ))
        if status_filter:
            base_query = base_query.filter(Ticket.status == status_filter)
        pagination = base_query.order_by(Ticket.status.asc(), priority_order.asc(), Ticket.last_updated.desc()).paginate(page=page, per_page=15, error_out=False)
        return render_template('index.html', tickets=pagination.items, pagination=pagination, status_filter=status_filter, query=query)

@app.route('/admin/stats')
@admin_required
def stats():
    tickets_by_category = db.session.query(TicketCategory.title, func.count(Ticket.id)).join(Ticket, Ticket.title == TicketCategory.title).group_by(TicketCategory.title).all()
    tickets_by_area = db.session.query(Area.name, func.count(Ticket.id)).join(Ticket).group_by(Area.name).all()
    chart_data = {"category": {"labels": [c[0] for c in tickets_by_category], "data": [c[1] for c in tickets_by_category]}, "area": {"labels": [a[0] for a in tickets_by_area], "data": [a[1] for a in tickets_by_area]}}
    return render_template('admin/stats.html', chart_data_json=json.dumps(chart_data))

@app.route('/admin/tickets')
@admin_required
def view_all_tickets():
    query = request.args.get('query', '')

    #Boton "Mostrar Todos"
    status_filter = request.args.get('status', None) # None para no filtrar por defecto
    page = request.args.get('page', 1, type=int)
    priority_order = case((Ticket.priority == 'Alta', 1), (Ticket.priority == 'Media', 2), (Ticket.priority == 'Baja', 3), else_=4)
    base_query = Ticket.query
    if query:
        search_term = f"%{query}%"
        base_query = base_query.filter(db.or_(cast(Ticket.id, String).like(search_term), Ticket.title.ilike(search_term), Ticket.customer_name.ilike(search_term), Ticket.tracking_id.ilike(search_term)))
    if status_filter:
        base_query = base_query.filter(Ticket.status == status_filter)
    pagination = base_query.order_by(Ticket.status.asc(), priority_order.asc(), Ticket.last_updated.desc()).paginate(page=page, per_page=15, error_out=False)
    return render_template('admin/view_tickets.html', tickets=pagination.items, pagination=pagination, status_filter=status_filter, query=query)

@app.route('/admin/areas', methods=['GET', 'POST'])
@admin_required
def manage_areas():
    if request.method == 'POST':
        name = request.form.get('name')
        if name and not Area.query.filter_by(name=name).first():
            db.session.add(Area(name=name)); db.session.commit(); flash('Área creada con éxito.', 'success')
        else: flash('Nombre de área inválido o ya existe.', 'danger')
        return redirect(url_for('manage_areas'))
    return render_template('admin/manage_areas.html', areas=Area.query.order_by(Area.name).all())

@app.route('/admin/categories', methods=['GET', 'POST'])
@admin_required
def manage_categories():
    if request.method == 'POST':
        title, priority, area_id = request.form.get('title'), request.form.get('priority'), request.form.get('area_id')
        if title and priority and area_id:
            db.session.add(TicketCategory(title=title, priority=priority, area_id=area_id)); db.session.commit(); flash('Categoría creada con éxito.', 'success')
        else: flash('Todos los campos son obligatorios.', 'danger')
        return redirect(url_for('manage_categories'))
    return render_template('admin/manage_categories.html', categories=TicketCategory.query.order_by(TicketCategory.title).all(), areas=Area.query.order_by(Area.name).all())

@app.route('/admin/agents', methods=['GET', 'POST'])
@admin_required
def manage_agents():
    if request.method == 'POST':
        username, password, email, area_id = request.form.get('username'), request.form.get('password'), request.form.get('email'), request.form.get('area_id')
        if not all([username, password, email]): flash('Usuario, contraseña y email son obligatorios.', 'danger')
        elif User.query.filter_by(username=username).first(): flash('Ese nombre de usuario ya existe.', 'warning')
        elif User.query.filter_by(email=email).first(): flash('Ese email ya está en uso.', 'warning')
        else:
            new_agent = User(username=username, first_name=request.form.get('first_name'), last_name=request.form.get('last_name'), email=email, area_id=area_id if area_id else None, password_reset_required=True)
            new_agent.set_password(password); db.session.add(new_agent); db.session.commit()
            flash(f'Agente "{username}" creado.', 'success')
        return redirect(url_for('manage_agents'))
    agents_data = []
    for user in User.query.order_by(User.role.desc(), User.username).all():
        agents_data.append({'user': user, 'ticket_count': Ticket.query.filter(Ticket.assigned_agent_id == user.id, Ticket.status == 'Abierto').count()})
    return render_template('admin/manage_agents.html', agents_data=agents_data, areas=Area.query.order_by(Area.name).all())

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if not current_user.password_reset_required or current_user.is_admin: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        new_password, confirm_password = request.form.get('new_password'), request.form.get('confirm_password')
        if not new_password or new_password != confirm_password: flash('Las contraseñas no coinciden.', 'danger')
        else:
            current_user.set_password(new_password); current_user.password_reset_required = False
            db.session.commit(); flash('Contraseña actualizada. Ya puedes usar el sistema.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def view_profile():
    if request.method == 'POST':
        current_password, new_password, confirm_password = request.form.get('current_password'), request.form.get('new_password'), request.form.get('confirm_password')
        if not current_user.check_password(current_password): flash('La contraseña actual es incorrecta.', 'danger')
        elif not new_password or new_password != confirm_password: flash('Las nuevas contraseñas no coinciden.', 'danger')
        else: current_user.set_password(new_password); db.session.commit(); flash('Tu contraseña ha sido actualizada.', 'success')
        return redirect(url_for('view_profile'))
    return render_template('profile.html', user=current_user, is_editable=False)

@app.route('/admin/edit_agent/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_agent(user_id):
    agent_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        agent_to_edit.first_name, agent_to_edit.last_name = request.form.get('first_name'), request.form.get('last_name')
        agent_to_edit.username, agent_to_edit.email = request.form.get('username'), request.form.get('email')
        agent_to_edit.role, agent_to_edit.area_id = request.form.get('role'), request.form.get('area_id') if request.form.get('area_id') else None
        new_password = request.form.get('password')
        if new_password: agent_to_edit.set_password(new_password); agent_to_edit.password_reset_required = False; flash('Perfil y contraseña actualizados.', 'success')
        else: flash('Perfil de agente actualizado.', 'success')
        db.session.commit()
        return redirect(url_for('manage_agents'))
    return render_template('profile.html', user=agent_to_edit, is_editable=True, areas=Area.query.order_by(Area.name).all())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter(func.lower(User.username) == func.lower(request.form['username'])).first()
        if user and user.check_password(request.form['password']):
            login_user(user); return redirect(url_for('dashboard'))
        else: flash('Usuario o contraseña incorrectos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('login'))

@app.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if not current_user.is_admin and ticket.assigned_agent_id != current_user.id:
        flash('No tienes permiso para comentar en este ticket.', 'danger'); return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))
    comment_text = request.form.get('comment')
    if comment_text:
        new_comment = Comment(content=comment_text, ticket_id=ticket.id, author_name=current_user.username, author_type='Agent')
        db.session.add(new_comment)
        ticket.last_updated_by_type = 'Agent'; ticket.last_updated = get_utc_now()
        db.session.add(ActivityLog(ticket_id=ticket.id, description=f"El agente {current_user.username} comentó en el ticket."))
        db.session.commit()
        if ticket.customer_email:
            send_email_notification(recipients=[ticket.customer_email], subject_template='email/subjects/agent_reply.txt', html_template='email/agent_reply.html', ticket=ticket, comment=new_comment)
        flash('Tu respuesta ha sido añadida.', 'success')
    else: flash('No puedes enviar una respuesta vacía.', 'warning')
    return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))

@app.route('/ticket/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if not current_user.is_admin and ticket.assigned_agent_id != current_user.id:
        flash('No tienes permiso para cerrar este ticket.', 'danger'); return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))
    ticket.status = 'Cerrado'; ticket.closed_at = get_utc_now()
    db.session.add(Comment(content='El ticket ha sido marcado como cerrado por un agente.', ticket_id=ticket.id, author_name=current_user.username, author_type='Agent'))
    db.session.add(ActivityLog(ticket_id=ticket.id, description=f"Ticket cerrado por el agente {current_user.username}."))
    db.session.commit()
    flash(f'Ticket #{ticket.id} ha sido cerrado.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/ticket/<int:ticket_id>/reassign', methods=['POST'])
@admin_required
def reassign_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    new_agent_id = int(request.form.get('agent_id')) if request.form.get('agent_id') else None
    if new_agent_id is None:
        if ticket.assigned_agent_id:
            log_description = f"Ticket desasignado de '{ticket.assigned_agent.username}' por el admin '{current_user.username}'."
            ticket.assigned_agent_id = None; db.session.add(ActivityLog(ticket_id=ticket.id, description=log_description)); db.session.commit()
            flash('El ticket ha sido marcado como no asignado.', 'success')
    else:
        new_agent = User.query.get(new_agent_id)
        if not new_agent: flash('El agente seleccionado no es válido.', 'danger')
        elif ticket.assigned_agent_id != new_agent.id:
            old_agent_name = ticket.assigned_agent.username if ticket.assigned_agent else "nadie"
            ticket.assigned_agent_id = new_agent.id
            log_description = f"Ticket reasignado de '{old_agent_name}' a '{new_agent.username}' por el admin '{current_user.username}'."
            db.session.add(ActivityLog(ticket_id=ticket.id, description=log_description)); db.session.commit()
            send_email_notification(recipients=[new_agent.email], subject_template='email/subjects/new_assignment_agent.txt', html_template='email/new_assignment_agent.html', ticket=ticket, agent=new_agent)
            flash(f'Ticket reasignado exitosamente a {new_agent.username}.', 'success')
    return redirect(url_for('track_ticket', tracking_id=ticket.tracking_id))

def test_smtp_connection(config):
    try:
        test_mail = Mail(); test_app = Flask(__name__)
        test_app.config.update(MAIL_SERVER=config.get('mail_server'), MAIL_PORT=int(config.get('mail_port', 587)), MAIL_USE_TLS=config.get('mail_use_tls', 'true').lower() == 'true', MAIL_USERNAME=config.get('mail_username'), MAIL_PASSWORD=config.get('mail_password'))
        test_mail.init_app(test_app)
        sender_name = config.get('app_name', 'Prueba del Helpdesk'); recipient_email = config.get('test_email')
        msg = Message(f"Prueba de Conexión - {sender_name}", sender=(sender_name, config.get('mail_username')), recipients=[recipient_email])
        msg.body = "Si recibes este correo, la configuración SMTP funciona."
        with test_app.app_context(): test_mail.send(msg)
        return True, f"¡Conexión exitosa! Se envió un correo de prueba a {recipient_email}."
    except Exception as e: return False, f"Error en la conexión: {str(e)}"

@app.route('/test-smtp', methods=['POST'])
def test_smtp():
    if is_installed(): return jsonify({'success': False, 'message': 'La aplicación ya está instalada.'}), 403
    data = request.get_json()
    if not data or not data.get('mail_username') or not data.get('test_email'):
        return jsonify({'success': False, 'message': 'Faltan datos para la prueba.'}), 400
    success, message = test_smtp_connection(data)
    return jsonify({'success': success, 'message': message})

with app.app_context():
    db.create_all()

@app.cli.command("create-admin")
def create_admin(username, password, email):
    if User.query.filter_by(username=username).first(): print(f"Error: El usuario '{username}' ya existe."); return
    admin = User(username=username, email=email, role='admin', password_reset_required=False)
    admin.set_password(password); db.session.add(admin); db.session.commit()
    print(f"Usuario administrador '{username}' creado.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)