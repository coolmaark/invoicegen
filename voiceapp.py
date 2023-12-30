from flask import Flask, request, render_template, redirect, url_for, jsonify
import pdfplumber
from pymongo import MongoClient
from gridfs import GridFS

app = Flask(__name__)

# MongoDB Configuration
# client = MongoClient("mongodb://localhost:27017/")
client = MongoClient('mongodb+srv://gaja:gaja123@cluster0.jdoybcv.mongodb.net/gameproject')
db = client["pdf_data"]
fs = GridFS(db)

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'pdf' not in request.files:
        return redirect(request.url)

    pdf_file = request.files['pdf']
    if pdf_file.filename == '':
        return redirect(request.url)

    if pdf_file:
        pdf_text = extract_pdf_text(pdf_file)
        store_pdf_and_text(pdf_file.filename, pdf_text, pdf_file)
        return redirect(url_for('display_text', filename=pdf_file.filename))

@app.route('/display/<filename>')
def display_text(filename):
    pdf_data = fs.find_one({"filename": filename})
    if pdf_data:
        pdf_text = pdf_data.metadata["text"]
        return render_template('display.html', pdf_text=pdf_text)

#For Mongodb locally 
# @app.route('/all_data', methods=['GET'])
# def get_all_data():
#     all_data = list(fs.find({}, no_cursor_timeout=True))
#     processed_data = [{"filename": item.filename, "text": item.metadata["text"]} for item in all_data]
#     return render_template('alldata.html', data=processed_data)


#MongoDb
@app.route('/all_data', methods=['GET'])
def get_all_data():
    all_data_cursor = fs.find({})
    all_data = list(all_data_cursor)
    all_data_cursor.close()  # Close the cursor explicitly
    processed_data = [{"filename": item.filename, "text": item.metadata["text"]} for item in all_data]
    return render_template('alldata.html', data=processed_data)

def extract_pdf_text(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
    return text

def store_pdf_and_text(filename, text, pdf_file):
    pdf_id = fs.put(pdf_file, filename=filename, metadata={"text": text})
    return pdf_id

if __name__ == '__main__':
    app.run(debug=True)
