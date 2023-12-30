from flask import Flask, render_template, request, redirect, url_for, jsonify
from pymongo import MongoClient
from mindee import Client, product
import os
from datetime import datetime
from bson import ObjectId
import base64
import time
from google_apis import create_service

app = Flask(__name__)

# MongoDB configuration
client = MongoClient('mongodb+srv://gaja:gaja123@cluster0.jdoybcv.mongodb.net/gameproject')
# client = MongoClient('mongodb://localhost:27017')
db = client['pdf_data_new']

# Mindee API configuration
mindee_client = Client(api_key="83548d8bf4bd3a33b7d407f62c76d57b")

# Set up the uploads folder
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Gmail API configuration
CLIENT_FILE = 'client-secret.json'
API_NAME = 'gmail'
API_VERSION = 'v1'
SCOPES = ['https://mail.google.com/']
service = create_service(CLIENT_FILE, API_NAME, API_VERSION, SCOPES)

# Custom Jinja filter to extract information from the output_text
@app.template_filter('extract')
def extract(text, key):
    start = text.find(f'{key}:') + len(key) + 1
    end = text.find('\n', start)
    return text[start:end].strip()

# Gmail API functions
def search_emails(query_string: str, label_ids=None):
    try:
        message_list_response = service.users().messages().list(
            userId='me',
            labelIds=label_ids,
            q=query_string
        ).execute()

        message_items = message_list_response.get('messages')
        next_page_token = message_list_response.get('nextPageToken')

        while next_page_token:
            message_list_response = service.users().messages().list(
                userId='me',
                labelIds=label_ids,
                q=query_string,
                pageToken=next_page_token
            ).execute()

            message_items.extend(message_list_response.get('messages'))
            next_page_token = message_list_response.get('nextPageToken')
        return message_items
    except Exception as e:
        raise NoEmailFound('No emails returned')

def get_file_data(message_id, attachment_id, file_name, save_location):
    response = service.users().messages().attachments().get(
        userId='me',
        messageId=message_id,
        id=attachment_id
    ).execute()

    file_data = base64.urlsafe_b64decode(response.get('data').encode('UTF-8'))
    return file_data

def get_message_detail(message_id, msg_format='metadata', metadata_headers=None):
    message_detail = service.users().messages().get(
        userId='me',
        id=message_id,
        format=msg_format,
        metadataHeaders=metadata_headers
    ).execute()
    return message_detail

@app.route('/')
def home():
    # Fetch data from MongoDB
    collection = db['pdf_data']
    documents = collection.find()
    return render_template('home.html', documents=documents)

@app.route('/upload', methods=['POST', 'GET'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file:
            # Save the uploaded file locally
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            # Load the file and parse it using Mindee API
            input_doc = mindee_client.source_from_path(file_path)
            result = mindee_client.parse(product.InvoiceV4, input_doc)
            # Convert the Document object to a string for storage
            output_text = str(result.document)
            # Store the result in MongoDB
            collection = db['pdf_data']
            uploaded_from = "Web"
            upload_datetime = datetime.now()
            document = {
                'input_file': file_path,
                'output_text': output_text,
                "uploaded_from": uploaded_from,
                'upload_datetime': upload_datetime
            }
            collection.insert_one(document)
            return redirect(url_for('home'))
    return render_template("upload.html")

@app.route('/view_data/<file_id>')
def view_data(file_id):
    # Retrieve data from MongoDB
    collection = db['pdf_data']
    document = collection.find_one({'_id': ObjectId(file_id)})
    if document:
        return render_template('newviewdata.html', document=document)
    else:
        return jsonify({'error': 'File not found'})

@app.route('/view_invoice/<file_id>')
def view_pdf(file_id):
    # Retrieve file path from MongoDB
    collection = db['pdf_data']
    document = collection.find_one({'_id': ObjectId(file_id)})

    if document:
        file_path = document['input_file']

        # Read the PDF file content
        with open(file_path, 'rb') as pdf_file:
            pdf_content = pdf_file.read()

        # Encode the PDF content in base64
        encoded_pdf = base64.b64encode(pdf_content).decode('utf-8')

        return render_template('viewinvoice.html', encoded_pdf=encoded_pdf)
    else:
        return jsonify({'error': 'File not found'})

@app.route('/delete_content/<file_id>')
def delete_content(file_id):
    # Retrieve file path from MongoDB
    collection = db['pdf_data']
    document = collection.find_one({'_id': ObjectId(file_id)})
    documents = collection.find()
    if document:
        # Delete file locally
        file_path = document['input_file']
        # Use os.path.join for a platform-independent path
        os.remove(file_path)
        # Delete document from MongoDB
        collection.delete_one({'_id': ObjectId(file_id)})
        return render_template('home.html', documents=documents)
    else:
        return jsonify({'error': 'File not found'})

@app.route('/fetch_and_process_emails', methods=['GET'])
def fetch_and_process_emails():
    try:
        # Fetch emails from Gmail with the specified query
        # query_string = 'from:gajanantodetti1998@gmail.com has:attachment'
        query_string = 'has:attachment'
        save_location = os.path.join(os.getcwd(), 'uploads')
        email_messages = search_emails(query_string)    

        for email_message in email_messages:
            message_detail = get_message_detail(email_message['id'], msg_format='full', metadata_headers=['parts'])
            message_detail_payload = message_detail.get('payload')

            if 'parts' in message_detail_payload:
                for msg_payload in message_detail_payload['parts']:
                    file_name = msg_payload['filename']
                    body = msg_payload['body']
                    if 'attachmentId' in body:
                        attachment_id = body['attachmentId']
                        attachment_content = get_file_data(email_message['id'], attachment_id, file_name, save_location)

                        if file_name.lower().endswith('.pdf'):
                            # Check if the file has already been processed
                            collection = db['pdf_data']

                            # Use os.path.join for a platform-independent path
                            existing_document = collection.find_one({'input_file': os.path.join('uploads', file_name)})

                            if existing_document:
                                print(f'Email Attachment {file_name} already processed. Skipping...')
                            else:
                                # Save the PDF file in the invoicepdfs folder
                                pdf_path = os.path.join(save_location, file_name)
                                with open(pdf_path, 'wb') as pdf_file:
                                    pdf_file.write(attachment_content)

                                # Process the PDF using Mindee API
                                input_doc = mindee_client.source_from_path(pdf_path)
                                result = mindee_client.parse(product.InvoiceV4, input_doc)
                                output_text = str(result.document)

                                # Store the result in MongoDB
                                uploaded_from = "Gmail"
                                upload_datetime = datetime.now()
                                document = {
                                    'input_file': os.path.join('uploads', file_name),
                                    'output_text': output_text,
                                    'uploaded_from': uploaded_from,
                                    'upload_datetime': upload_datetime
                                }
                                collection.insert_one(document)
                                print(f'Email Attachment {file_name} processed and stored in MongoDB.')

        return redirect(url_for('home'))
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True)
