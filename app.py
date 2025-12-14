






import pytesseract
from PIL import Image


import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from sqlalchemy import or_

# --- Gemini API Imports ---
from google import genai
from google.genai import types
from google.genai.errors import APIError
# --- End Gemini API Imports ---

from config import Config

# --- Application Initialization ---
app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)

# --- Gemini Client Initialization ---
ai_client = None
try:
    # Client automatically picks up GEMINI_API_KEY from environment variables
    ai_client = genai.Client() 
    print("Gemini client initialized successfully.")
except Exception as e:
    print(f"Warning: Gemini client initialization failed. AI description will not work. Error: {e}")
# --- END Gemini Client Initialization ---


# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Database Models ---
class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(50), unique=True, nullable=False)
    standard_name = db.Column(db.String(100), nullable=False) 
    display_name = db.Column(db.String(100), nullable=False)
    documents = db.relationship('Document', backref='owner', lazy=True, order_by="Document.date_uploaded")

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_name = db.Column(db.String(100), nullable=False)
    filename_on_disk = db.Column(db.String(150), unique=True, nullable=False) 
    category = db.Column(db.String(100), nullable=True)
    date_uploaded = db.Column(db.DateTime, default=db.func.current_timestamp())
    description = db.Column(db.Text, nullable=True) 
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)

# --- Utility Functions ---

def standardize_name(name):
    if not name:
        return ""
    return ''.join(filter(str.isalnum, name.lower()))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def create_db():
    with app.app_context():
        db.create_all()
# --- AI INTEGRATION FUNCTION (THE TRUE FINAL FIX) ---
# >>> NEW IMPORT <<<
from PyPDF2 import PdfReader 
# >>> END NEW IMPORT <<<

# ... (rest of the file) ...

# --- AI INTEGRATION FUNCTION (COMPREHENSIVE OCR WORKAROUND) ---
def generate_description_with_ai(file_path, original_filename):
    """
    Handles PDF (via PyPDF2) and Images (via Pytesseract OCR) to extract text 
    and send a stable, text-only call to the Gemini API.
    """
    
    # >>> NEW IMPORTS (Ensure these are at the top of your app.py file) <<<
    # from PyPDF2 import PdfReader 
    # import pytesseract
    # from PIL import Image
    # >>> END NEW IMPORTS <<<

    if ai_client is None:
        return f"[AI FAILED]: API client not initialized. Check GEMINI_API_KEY setup."

    extension = os.path.splitext(original_filename)[1].lower()
    extracted_text = ""
    
    # 1. LOCAL CONTENT EXTRACTION
    
    if extension == '.pdf':
        try:
            from PyPDF2 import PdfReader 
            reader = PdfReader(file_path)
            for page in reader.pages:
                extracted_text += page.extract_text() or ""
            
            if not extracted_text.strip():
                 # PDF contained no readable text (try OCR as a fallback)
                 # This section is commented out to keep things stable, but could be added later.
                 pass 

        except Exception as e:
            return f"[AI Error]: Could not read PDF content locally: {e}"
            
    elif extension in ['.jpg', '.jpeg', '.png']:
        try:
            import pytesseract
            from PIL import Image
            
            # --- OCR LOGIC ---
            # NOTE: Tesseract must be installed on your operating system for this to work.
            img = Image.open(file_path)
            extracted_text = pytesseract.image_to_string(img)
            # --- END OCR LOGIC ---
            
        except Exception as e:
            # If Pytesseract or PIL is not configured correctly, this catches the error
            return f"[AI Error]: OCR failed for image. Detail: {e}. Check Tesseract/Pillow installation."
        
    else:
        return f"[AI Skipped]: File type '{extension}' is not supported."
    
    # Check if text was found after extraction/OCR
    if not extracted_text.strip():
        return f"[AI Skipped]: Document/Image contained no readable text."

    # 2. DEFINE PROMPT
    system_instruction = (
        "You are an expert document summarization assistant. Analyze the text provided "
        "and generate a single, concise description (max 2 sentences) that highlights the "
        "most important details, such as the document's type, purpose, dates, or key entities. "
        "The description will be used as metadata in a document management system. Be brief and professional."
    )
    
    contents = [
        "Please summarize the following document text:",
        extracted_text[:30000] # Limit text size to prevent large payload errors
    ]

    try:
        # 3. GENERATE CONTENT (STABLE TEXT-ONLY CALL)
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
        
        return response.text.strip()[:65535]

    except APIError as e:
        return f"[AI Error]: Gemini API failed on text call. Detail: {e}"
    except Exception as e:
        return f"[AI Error]: An unexpected error occurred during summary generation: {e}"
# --- END AI INTEGRATION FUNCTION (COMPREHENSIVE OCR WORKAROUND) ---

# --- Routes ---
# In app.py:

# In app.py:

# In app.py:

# In app.py, add the os import if it's not already there:

# ... (rest of imports)
# In app.py:

@app.route('/delete/<int:doc_id>', methods=['POST'])
def delete_document(doc_id):
    document = Document.query.get_or_404(doc_id)
    
    try:
        # 1. DELETE FILE FROM STORAGE - CORRECTED LINE
        # Access UPLOADS_FOLDER from the app's configuration dictionary
        file_path = os.path.join(app.config['UPLOADS_FOLDER'], document.hashed_filename)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # 2. DELETE RECORD FROM DATABASE
        db.session.delete(document)
        db.session.commit()
        
        flash(f"Successfully deleted document: {document.document_name}", 'success')
        
    except Exception as e:
        # Check if the error is the expected missing file error, or another type
        if "No such file or directory" in str(e):
            flash(f"Warning: Document {document.document_name} deleted from DB, but file was already missing from disk.", 'danger')
            db.session.delete(document)
            db.session.commit()
        else:
            db.session.rollback()
            flash(f"Error deleting document: {e}", 'danger')
        
    return redirect(url_for('index'))



@app.route('/', methods=['GET', 'POST'])
def index():
    create_db()

    # --- POST Logic (File Upload) ---
    if request.method == 'POST':
        # ... (Your existing POST logic for file upload remains here) ...
        # NOTE: If you have a session.add/commit here, that's fine.
        return redirect(url_for('index'))


    # --- GET Logic (Handles Display and Search) ---
    search_term = request.args.get('search', '').strip()
    
    # *** FINAL FIX: Temporarily disable autoflush to prevent IntegrityError ***
    with db.session.no_autoflush:
        
        # 1. Start with a query for all people
        all_people = Person.query.order_by(Person.display_name).all()
        
        final_people_list = []
        
        if search_term:
            search_lower = search_term.lower()

            for person in all_people:
                
                # Filter documents in Python for the current person
                # This line (person.documents) triggered the original error via autoflush
                filtered_docs = []
                
                for doc in person.documents:
                    doc_desc = (doc.description or '').lower()
                    doc_name = (doc.document_name or '').lower()
                    doc_category = (doc.category or '').lower()
                    
                    # Check if the search term matches any document field
                    if search_lower in doc_name or \
                       search_lower in doc_category or \
                       search_lower in doc_desc:
                        
                        filtered_docs.append(doc)

                # Check if the person's fields match OR if they have matching documents
                person_matches = search_lower in person.display_name.lower() or \
                                 search_lower in person.unique_id.lower() or \
                                 len(filtered_docs) > 0
                                 
                if person_matches:
                    # Temporarily replace the person's full document list 
                    # with the filtered list for template rendering simplicity.
                    person.documents = filtered_docs
                    final_people_list.append(person)
                    
        else:
            # If no search term, use the full list of people
            final_people_list = all_people
    # *** END no_autoflush block ***


    # Pass the final list (either filtered or full) to the template
    return render_template('index.html', all_people=final_people_list, search_term=search_term)


@app.route('/view/<int:doc_id>') 
def view_file(doc_id):
    # ... (view_file route remains the same) ...
    doc = Document.query.get_or_404(doc_id)
    person_unique_id = doc.owner.unique_id 
    person_dir = person_unique_id 
    filename_on_disk = secure_filename(doc.document_name)
    extension = os.path.splitext(filename_on_disk)[1].lower()
    
    mimetype = 'application/octet-stream' 
    if extension == '.pdf':
        mimetype = 'application/pdf'
    elif extension in ['.jpg', '.jpeg']:
        mimetype = 'image/jpeg'
    elif extension == '.png':
        mimetype = 'image/png'

    response = send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], person_dir), 
        filename_on_disk, 
        mimetype=mimetype, 
        download_name=doc.document_name
    )
    
    response.headers["Content-Disposition"] = "inline"
    return response

if __name__ == '__main__':
    create_db()
    app.run(debug=True)
