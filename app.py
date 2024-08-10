from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from models import db, User, Chat
from forms import RegistrationForm, LoginForm
import os
import shutil
from werkzeug.utils import secure_filename
import json
import requests

app = Flask(__name__)
app.config.from_object('config.Config')
#db = SQLAlchemy(app)
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Root Route
@app.route("/")
@login_required
def root():
    return redirect(url_for('home'))

# User Routes
@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()  # Create an instance of RegistrationForm
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('home'))
    return render_template('register.html', form=form)  # Pass the form to the template

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()  # Create an instance of LoginForm
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', form=form)  # Pass the form to the template

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/home")
@login_required
def home():
    chats = Chat.query.filter_by(user_id=current_user.id).all()
    return render_template('home.html', chats=chats)

@app.route("/new_chat", methods=['POST'])
@login_required
def new_chat():
    title = request.form.get('title')
    chat = Chat(title=title, history="", user_id=current_user.id)
    db.session.add(chat)
    db.session.commit()

    # Clear the uploads folder for new chat
    uploads_dir = 'uploads'
    if os.path.exists(uploads_dir):
        shutil.rmtree(uploads_dir)
    os.makedirs(uploads_dir)

    return redirect(url_for('chat', chat_id=chat.id))

@app.route("/chat/<int:chat_id>")
@login_required
def chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    return render_template('chat.html', chat=chat)

@app.route("/delete_chat/<int:chat_id>", methods=['POST'])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    db.session.delete(chat)
    db.session.commit()
    return redirect(url_for('home'))

# RAG and LLaMA 3.1 Integration
def process_and_store_embeddings(file_path, user):
    # Process the file to generate embeddings and store them
    pass

def generate_rag_response(query, user):
    api_url = "http://localhost:11434/api/generate"
    prompt = f"Context: {query}\nAssistant:"
    payload = {
        "model": "llama3.1",
        "prompt": prompt,
        "max_tokens": 200,
        "temperature": 0.7
    }

    response = requests.post(api_url, json=payload, stream=True)
    full_response = ""
    citations = []

    for line in response.iter_lines():
        if line:
            decoded_line = line.decode('utf-8')
            json_line = json.loads(decoded_line)
            full_response += json_line.get("response", "")

    return full_response, citations

@app.route("/upload", methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.url)
    
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join('uploads', filename)
        file.save(file_path)

        process_and_store_embeddings(file_path, current_user)

        flash('File successfully uploaded', 'success')
        return redirect(url_for('chat', chat_id=request.form.get('chat_id')))
    else:
        flash('File upload failed', 'danger')
        return redirect(request.url)

@app.route("/query", methods=['POST'])
@login_required
def query():
    data = request.json
    query = data.get('query')
    chat_id = data.get('chat_id')
    
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    response, citations = generate_rag_response(query, current_user)
    
    chat = Chat.query.get(chat_id)
    chat.history += f"You: {query}\nBot: {response}\n\n"
    db.session.commit()
    
    return jsonify({"response": response})

# Run the app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)