from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from sentence_transformers import SentenceTransformer
import faiss
import torch
import logging
import traceback
import os

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='../frontend')
CORS(app)

# Determine the device
device = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
logger.info(f"Using device: {device}")

# Load LLaMA model using Transformers pipeline
model_path = "On-Device RAG/meta-llama/Meta-Llama-3.1-8B"
try:
    logger.info(f"Loading model from {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True
    )
    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device=device,
        max_new_tokens=10000,
        do_sample=True,
        temperature=0.7,
        pad_token_id=tokenizer.eos_token_id,
        truncation=True,
    )
    logger.info("Model loaded successfully")
except Exception as e:
    logger.error(f"Error loading the model: {e}")
    logger.error(traceback.format_exc())
    pipe = None

# Load Sentence Transformer for embeddings
embedder = SentenceTransformer('all-MiniLM-L6-v2')
embedder.to(device)

# Initialize FAISS index
d = 384  # Dimension of embeddings
index = faiss.IndexFlatL2(d)

# In-memory storage for documents
documents = []

def add_document(text):
    global index, documents
    embedding = embedder.encode([text], device=device)
    index.add(embedding)
    documents.append(text)

def search_documents(query, top_k=5):
    query_embedding = embedder.encode([query], device=device)
    D, I = index.search(query_embedding, top_k)
    if len(I[0]) == 0 or I[0][0] == -1:
        return []  # No documents found
    return [documents[i] for i in I[0] if i < len(documents)]

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    if file:
        try:
            # Attempt to decode using UTF-8, fall back to Latin-1 or others if needed
            try:
                text = file.read().decode('utf-8')
            except UnicodeDecodeError:
                logger.warning("UTF-8 decoding failed, trying Latin-1")
                text = file.read().decode('latin-1')
            add_document(text)
            return jsonify({"status": "success", "message": "File uploaded successfully"})
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            logger.error(traceback.format_exc())
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/query', methods=['POST'])
def query():
    if pipe is None:
        logger.error("Model not loaded")
        return jsonify({"error": "Model not loaded. Check server logs."}), 500

    data = request.json
    logger.info(f"Received query: {data}")
    query = data.get('query')
    if not query:
        logger.warning("No query provided")
        return jsonify({"error": "No query provided"}), 400

    try:
        # Retrieve relevant documents based on query
        retrieved_docs = search_documents(query)
        context = "\n".join(retrieved_docs)
        logger.info(f"Retrieved {len(retrieved_docs)} documents")

        # Generate prompt
        prompt = f"Human: {query}\n\n"
        if context:
            prompt += f"Context:\n{context}\n\nAssistant:"
        else:
            prompt += "Assistant:"
        
        logger.info(f"Generated prompt: {prompt}")

        # Generate the response using the local LLaMA model
        response = pipe(prompt, return_full_text=False)
        logger.info(f"Raw model response: {response}")
        
        # Extract the generated text and ensure it's valid
        answer = response[0].get('generated_text', '').strip()
        if not answer:
            answer = "I'm sorry, I didn't understand that. Could you please ask again?"
        
        logger.info(f"Processed answer: {answer}")

        return jsonify({"response": answer})
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2000, debug=True)