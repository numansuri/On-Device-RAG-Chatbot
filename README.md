# On-Device RAG Chatbot with Llama 3.1

## Table of Contents
1. [Introduction](#introduction)
2. [Features](#features)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Usage](#usage)
6. [Project Structure](#project-structure)
7. [How It Works](#how-it-works)
8. [Contributing](#contributing)
9. [License](#license)

## Introduction

This project is an on-device Retrieval-Augmented Generation (RAG) chatbot that uses Llama 3.1 via Ollama. It allows users to upload documents, which are then processed and used as context for answering questions. When no documents are provided, the system engages in regular conversation using Llama 3.1.

## Features

- User authentication (register, login, logout)
- Document upload and processing (supports .txt, .pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx)
- RAG-based question answering using uploaded documents
- Regular conversation mode when no documents are present
- Chat history with formatted responses (lists, tables, etc.)
- Document management (view uploaded documents, clear chat and documents)
- Responsive web interface

## Prerequisites

- Python 3.7+
- Ollama (for running Llama 3.1)
- SQLite (included with Python)

## Installation

1. **Clone the repository:**
   ```
   git clone https://github.com/numansuri/On_Device_RAG_Chatbot.git
   cd on-device-rag-chatbot
   ```

2. **Install required Python packages:**
   ```
   pip install -r requirements.txt
   ```

3. **Install Ollama:**
   Follow the instructions on the [Ollama GitHub page](https://github.com/ollama/ollama) to install Ollama for your operating system.

4. **Pull the Llama 3.1 model:**
   After installing Ollama on Windows, a PowerShell window will open. In this window, run:
   ```
   ollama pull llama3.1
   ```

## Usage

1. **Start the Ollama server:**
   Follow the instructions provided by Ollama to start the server with the Llama 3.1 model.

2. **Run the application:**
   You can run the application in two ways:
   
   a. Through the terminal:
      ```
      python run.py
      ```
   
   b. Using an IDE:
      - Open the project in VS Code or PyCharm.
      - Locate the `run.py` file in the project explorer.
      - Click the "Run" or "Play" button next to the `run.py` file.

3. **Access the application:**
   Open a web browser and go to `http://localhost:5000`

4. **Register a new account or log in.**

5. **Create a new chat and start interacting with the bot.**

6. **To use RAG, upload documents using the upload button in the chat interface.**

## Project Structure

- `.cache/`: Cache folder for temporary files
- `__pycache__/`: Python bytecode cache
- `instance/`: Instance-specific data
- `migrations/`: Database migration files
- `templates/`: HTML templates for the web interface
- `uploads/`: Directory for uploaded documents
- `.DS_Store`: macOS system file (can be ignored)
- `.gitattributes`: Git attributes file
- `app.py`: Main Flask application file
- `config.py`: Configuration settings
- `forms.py`: Form classes for user input
- `models.py`: Database models
- `README.md`: Project documentation (this file)
- `requirements.txt`: List of Python package dependencies
- `run.py`: Entry point for running the application

Key components:
- `app.py`: Contains the core logic of the Flask application, including route definitions and request handling.
- `models.py`: Defines the database schema using SQLAlchemy ORM.
- `forms.py`: Contains form classes used for user input validation.
- `config.py`: Stores configuration variables for the application.
- `templates/`: Houses the HTML templates used to render the web pages.
- `uploads/`: Stores user-uploaded documents for processing.
- `migrations/`: Contains database migration scripts for managing schema changes.
- `run.py`: The entry point for starting the Flask development server.

## How It Works

### Backend (Flask)

1. **User Authentication:**
   - Uses Flask-Login for user session management.
   - Passwords are hashed using bcrypt before storage.

2. **Document Processing:**
   - Uploaded documents are saved in chat-specific folders.
   - Documents are processed using libraries like PyPDF2 for PDFs, python-docx for Word documents, and pandas for Excel files.
   - Processed text is summarized using Llama 3.1 via Ollama.

3. **Chat Functionality:**
   - When a user sends a message, it's saved to the database.
   - If documents are present, the system uses RAG:
     - Constructs a prompt with document summaries and the user's question.
     - Sends this to Llama 3.1 for processing.
   - If no documents are present, it engages in regular conversation.
   - The response is formatted (adding HTML tags for lists, tables, etc.) before being sent back to the frontend.

4. **API Endpoints:**
   - `/send_message`: Handles message processing and response generation.
   - `/upload_documents`: Manages document uploads and processing.
   - `/get_documents`: Retrieves the list of uploaded documents for a chat.
   - `/clear_chat`: Deletes all messages and documents for a chat.

### Frontend (HTML/JavaScript)

1. **Chat Interface (`chat.html`):**
   - Uses Tailwind CSS for styling.
   - Implements a two-pane layout: document list and chat area.
   - Dynamically adds messages to the chat area.
   - Handles document uploads and message sending via AJAX requests.

2. **Home Page (`home.html`):**
   - Displays a list of user's chats.
   - Allows creation of new chats.

3. **Authentication Pages:**
   - `login.html` and `register.html` handle user authentication.

### Data Flow

1. User uploads documents → Backend processes and summarizes → Summaries stored in memory.
2. User sends message → Frontend sends to backend → Backend generates response using Llama 3.1 → Formatted response sent back to frontend → Frontend displays response.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
