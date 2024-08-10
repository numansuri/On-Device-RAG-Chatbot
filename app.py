from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from models import db, User, Chat, Message
from forms import RegistrationForm, LoginForm
import os
import shutil
from werkzeug.utils import secure_filename
import json
from datetime import datetime
from sentence_transformers import SentenceTransformer
import faiss
import PyPDF2
import docx
import pandas as pd

app = Flask(__name__)
app.config.from_object('config.Config')
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1 GB

# Initialize sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize FAISS index
index = faiss.IndexFlatL2(384)  # 384 is the dimension of the 'all-MiniLM-L6-v2' model

documents = []

def init_db():
    with app.app_context():
        db.create_all()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_document(file_path):
    _, file_extension = os.path.splitext(file_path)
    
    if file_extension == '.pdf':
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
    elif file_extension in ['.doc', '.docx']:
        doc = docx.Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
    elif file_extension in ['.xls', '.xlsx']:
        df = pd.read_excel(file_path)
        text = df.to_string()
    elif file_extension == '.txt':
        with open(file_path, 'r') as file:
            text = file.read()
    else:
        text = ""
    
    return text

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
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('home'))
    return render_template('register.html', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', form=form)

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
    chat = Chat(title=title, user_id=current_user.id)
    db.session.add(chat)
    db.session.commit()

    # Clear the uploads folder for new chat
    uploads_dir = app.config['UPLOAD_FOLDER']
    if os.path.exists(uploads_dir):
        shutil.rmtree(uploads_dir)
    os.makedirs(uploads_dir)

    return redirect(url_for('chat', chat_id=chat.id))

@app.route("/chat/<int:chat_id>")
@login_required
def chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp).all()
    return render_template('chat.html', chat=chat, messages=messages)

@app.route("/send_message", methods=['POST'])
@login_required
def send_message():
    data = request.json
    chat_id = data['chat_id']
    content = data['message']
    
    # Save user message
    user_message = Message(content=content, is_user=True, chat_id=chat_id)
    db.session.add(user_message)
    
    # Retrieve relevant documents
    query_embedding = model.encode([content])[0]
    _, I = index.search(query_embedding.reshape(1, -1), k=3)
    
    relevant_docs = [documents[i] for i in I[0]]
    
    # Generate response (simplified without LLM)
    bot_response = "Based on the documents I've processed, here's what I found:\n\n"
    citations = []
    
    for i, (doc_name, doc_content) in enumerate(relevant_docs, 1):
        excerpt = doc_content[:200] + "..." if len(doc_content) > 200 else doc_content
        bot_response += f"{i}. From document '{doc_name}':\n{excerpt}\n\n"
        citations.append(doc_name)
    
    # Save bot message
    bot_message = Message(content=bot_response, is_user=False, chat_id=chat_id, citations=json.dumps(citations))
    db.session.add(bot_message)
    
    db.session.commit()
    
    return jsonify({'bot_response': bot_response, 'citations': citations})

@app.route("/delete_chat/<int:chat_id>", methods=['POST'])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    db.session.delete(chat)
    db.session.commit()
    return redirect(url_for('home'))

@app.route("/upload_documents/<int:chat_id>", methods=['POST'])
@login_required
def upload_documents(chat_id):
    if 'documents' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('chat', chat_id=chat_id))
    
    files = request.files.getlist('documents')
    
    if not files:
        flash('No selected file', 'danger')
        return redirect(url_for('chat', chat_id=chat_id))
    
    successful_uploads = 0
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Process and add to documents list and FAISS index
            text = process_document(file_path)
            documents.append((filename, text))
            embedding = model.encode([text])[0]
            index.add(embedding.reshape(1, -1))
            successful_uploads += 1
    
    if successful_uploads > 0:
        flash(f'{successful_uploads} document(s) uploaded and processed successfully', 'success')
    else:
        flash('No documents were uploaded. Please check file types and try again.', 'warning')
    
    return redirect(url_for('chat', chat_id=chat_id))

@app.route("/clear_chat/<int:chat_id>", methods=['POST'])
@login_required
def clear_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    
    # Delete all messages associated with this chat
    Message.query.filter_by(chat_id=chat_id).delete()
    
    # Clear the uploads folder
    uploads_dir = app.config['UPLOAD_FOLDER']
    for filename in os.listdir(uploads_dir):
        file_path = os.path.join(uploads_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')
    
    # Clear the documents list and FAISS index
    global documents
    documents.clear()
    global index
    index = faiss.IndexFlatL2(384)
    
    db.session.commit()
    flash('Chat cleared and all associated documents deleted', 'info')
    return redirect(url_for('chat', chat_id=chat_id))

def reset_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Database tables created.")

if __name__ == '__main__':
    reset_db()  # Comment this line out after running once
    app.run(debug=True)