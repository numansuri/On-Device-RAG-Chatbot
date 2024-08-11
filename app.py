from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from models import db, User, Chat, Message
from forms import RegistrationForm, LoginForm
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os
import shutil
from werkzeug.utils import secure_filename
import json
from datetime import datetime
import requests
import PyPDF2
import docx
import pandas as pd
import re

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

documents = []

def init_db():
    with app.app_context():
        db.create_all()

init_db()

# Initialize the sentence transformer model
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Create a FAISS index for vector search
index = None
doc_embeddings = []
doc_metadata = []  # To store metadata like filenames or doc IDs


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def chunk_text(text, chunk_size=1000, overlap=200):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

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
    
    # Chunk the text
    text_chunks = chunk_text(text)
    
    # Generate embeddings for each chunk
    embeddings = [model.encode([chunk])[0] for chunk in text_chunks]
    
    return text_chunks, embeddings

def summarize_document(text, filename):
    prompt = f"Look at the entire document, no matter how large it is, and summarize it in 3-5 sentences:\n\n{text[:1000]}..."  # Limit text to prevent token overflow
    response = requests.post('http://localhost:11434/api/generate',
                             json={
                                 "model": "llama3.1",
                                 "prompt": prompt,
                                 "stream": False
                             })
    summary = response.json()['response']
    return filename, summary

def process_response(response):
    # Convert numbered lists
    response = re.sub(r'(\d+\.\s*.*?)(?=\n\d+\.|\Z)', r'<li>\1</li>', response, flags=re.DOTALL)
    response = re.sub(r'((?:<li>.*?</li>\n*)+)', r'<ol>\1</ol>', response, flags=re.DOTALL)
    
    # Convert bullet point lists
    response = re.sub(r'(•\s*.*?)(?=\n•|\Z)', r'<li>\1</li>', response, flags=re.DOTALL)
    response = re.sub(r'((?:<li>.*?</li>\n*)+)', r'<ul>\1</ul>', response, flags=re.DOTALL)
    
    # Convert tables
    def table_replace(match):
        rows = match.group(1).split('\n')
        table_html = '<table class="border-collapse border border-gray-400 w-full">'
        for i, row in enumerate(rows):
            cells = row.split('|')
            table_html += '<tr>'
            for cell in cells:
                tag = 'th' if i == 0 else 'td'
                table_html += f'<{tag} class="border border-gray-400 px-4 py-2">{cell.strip()}</{tag}>'
            table_html += '</tr>'
        table_html += '</table>'
        return table_html
    
    response = re.sub(r'\n((?:[^|\n]+\|)+[^|\n]+(?:\n(?:[^|\n]+\|)+[^|\n]+)*)', table_replace, response)
    
    # Convert markdown-style bold to HTML bold
    response = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', response)
    
    # Convert markdown-style italic to HTML italic
    response = re.sub(r'\*(.*?)\*', r'<em>\1</em>', response)
    
    # Convert newlines to <br> tags, except within HTML tags
    response = re.sub(r'(?<!>)\n(?!<)', '<br>', response)
    
    return response

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
@login_required
def root():
    return redirect(url_for('home'))

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

    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(chat.id))
    os.makedirs(uploads_dir, exist_ok=True)

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
    
    user_message = Message(content=content, is_user=True, chat_id=chat_id)
    db.session.add(user_message)
    
    if documents and index is not None:
        query_embedding = model.encode([content])
        _, I = index.search(query_embedding, k=10)  # Get top 10 relevant chunks

        relevant_chunks = [doc_metadata[i] for i in I[0]]
        context = "\n".join([f"Chunk from {doc['filename']}:\n{doc['chunk_text']}" for doc in relevant_chunks])
        prompt = f"Context:\n{context}\n\nUser: {content}\n\nAssistant: Based on the provided context, I'll answer the user's question. If the answer is not in the context, I'll say so and provide a general response. Use proper formatting for lists, tables, and other structured content.\
            I will also do a deep search of the document, no matter how big the document is."
    else:
        prompt = f"User: {content}\n\nAssistant: Provide a detailed response using proper formatting for lists, tables, and other structured content where appropriate."

    response = requests.post('http://localhost:11434/api/generate',
                             json={
                                 "model": "llama3.1",
                                 "prompt": prompt,
                                 "stream": False
                             })
    bot_response = response.json()['response']
    
    formatted_response = process_response(bot_response)
    
    citations = [doc['filename'] for doc in relevant_chunks] if documents else []
    
    bot_message = Message(content=formatted_response, is_user=False, chat_id=chat_id, citations=json.dumps(citations))
    db.session.add(bot_message)
    
    db.session.commit()
    
    return jsonify({'bot_response': formatted_response, 'citations': citations})

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
    
    global documents, index, doc_embeddings, doc_metadata
    documents.clear()
    doc_embeddings = []
    doc_metadata = []

    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(chat_id))
    os.makedirs(uploads_dir, exist_ok=True)
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(uploads_dir, filename)
            file.save(file_path)
            
            text_chunks, embeddings = process_document(file_path)
            summary = summarize_document(text_chunks[0], filename)  # Use the first chunk to create a summary
            documents.append(summary)

            # Store embeddings and metadata for each chunk
            for i, embedding in enumerate(embeddings):
                doc_embeddings.append(embedding)
                doc_metadata.append({'filename': filename, 'chunk_index': i, 'chunk_text': text_chunks[i]})
    
    # Update the FAISS index with new embeddings
    if doc_embeddings:
        doc_embeddings_np = np.array(doc_embeddings)
        if index is None:
            index = faiss.IndexFlatL2(doc_embeddings_np.shape[1])  # L2 distance
        index.add(doc_embeddings_np)
    
    flash('Documents uploaded and processed successfully', 'success')
    return redirect(url_for('chat', chat_id=chat_id))

@app.route("/get_documents/<int:chat_id>")
@login_required
def get_documents(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(chat_id))
    if not os.path.exists(uploads_dir):
        return jsonify([])

    document_list = [f for f in os.listdir(uploads_dir) if os.path.isfile(os.path.join(uploads_dir, f))]
    return jsonify(document_list)

@app.route("/clear_chat/<int:chat_id>", methods=['POST'])
@login_required
def clear_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    
    Message.query.filter_by(chat_id=chat_id).delete()
    
    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(chat_id))
    if os.path.exists(uploads_dir):
        shutil.rmtree(uploads_dir)
    
    global documents
    documents.clear()
    
    db.session.commit()
    flash('Chat cleared and all associated documents deleted', 'info')
    return redirect(url_for('chat', chat_id=chat_id))

def reset_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Database tables created.")

if __name__ == '__main__':
    #reset_db()  # Comment this line out after running once
    app.run(debug=True)