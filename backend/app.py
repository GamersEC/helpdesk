from flask import Flask, render_template, request, redirect, url_for
from models import db, Ticket

app = Flask(__name__)

# Configuración de la base de datos PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://helpdesk:helpdesk123@db:5432/helpdesk_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Crear tablas si no existen
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    tickets = Ticket.query.all()
    return render_template('index.html', tickets=tickets)

@app.route('/new', methods=['GET', 'POST'])
def new_ticket():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']

        new_ticket = Ticket(title=title, description=description)
        db.session.add(new_ticket)
        db.session.commit()

        return redirect(url_for('index'))

    return render_template('new_ticket.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)