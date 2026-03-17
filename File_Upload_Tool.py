import requests
import json
import os
import io
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import time

API_BASE_URL = 'http://192.168.178.11:32652/api/FileAccess'  # Base URL of the API endpoint

# Configuration
BUCKET_NAME = 'my-bucket'  # Name of the storage bucket
PART_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_WORKERS = 5  # Number of parallel threads for uploading parts

def initiate_multipart_upload(object_name, content_type):
    url = f"{API_BASE_URL}/multipart/initiate"
    payload = {
        'BucketName': BUCKET_NAME,
        'ObjectName': object_name,
        'ContentType': content_type
    }
    headers = {'Content-Type': 'application/json'}

    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print(f"Initiate response status code: {response.status_code}")

    if response.status_code != 200:
        print(f"Initiate response content: {response.text}")
        response.raise_for_status()

    try:
        result = response.json()
        upload_id = result.get('uploadId')
        if not upload_id:
            print(f"Failed to obtain UploadId. Response JSON: {result}")
            raise ValueError("Failed to obtain UploadId from initiation response.")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
        raise

    print(f"Upload initiated. UploadId: {upload_id}")
    return upload_id

def upload_part(upload_id, part_number, part_data, object_name, progress_callback=None):
    start_time = time.time()
    url = f"{API_BASE_URL}/multipart/upload-part"

    files = {
        'BucketName': (None, BUCKET_NAME),
        'ObjectName': (None, object_name),
        'UploadId': (None, upload_id),
        'PartNumber': (None, str(part_number)),
        'FilePart': ('part.bin', io.BytesIO(part_data), 'application/octet-stream')
    } 
    response = requests.post(url, files=files)
    print(f"Upload part {part_number} response status code: {response.status_code}")
    print(f"Upload part {part_number} response content: {response.text}")  # Log the full response 
    if response.status_code != 200:
        print(f"Upload part {part_number} response content: {response.text}")
        response.raise_for_status() 
    result = response.json()
    etag = result.get('eTag')
    
    # Fix: Strip extra surrounding quotes, if present
    if etag:
        etag = etag.strip('"') 
    if not etag:
        raise ValueError(f"No ETag returned for part {part_number}.") 
    print(f"Uploaded part {part_number}. ETag: {etag}")

    # Calculate time taken for this part
    time_taken = time.time() - start_time

    # If a progress callback is provided, call it with bytes uploaded
    if progress_callback:
        progress_callback(part_number, time_taken, len(part_data))

    return part_number, etag

def complete_multipart_upload(upload_id, parts, object_name):
    url = f"{API_BASE_URL}/multipart/complete"
    payload = {
        'BucketName': BUCKET_NAME,
        'ObjectName': object_name,
        'UploadId': upload_id,
        'PartETags': [{'PartNumber': part[0], 'ETag': part[1]} for part in parts]
    }
    headers = {'Content-Type': 'application/json'}

    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print(f"Complete response status code: {response.status_code}")
    if response.status_code != 200:
        print(f"Complete response content: {response.text}")
        response.raise_for_status()

    result = response.json()
    print(f"Multipart upload completed. Message: {result.get('Message')}, ETag: {result.get('ETag')}")

def abort_multipart_upload(upload_id, object_name):
    url = f"{API_BASE_URL}/multipart/abort"
    payload = {
        'BucketName': BUCKET_NAME,
        'ObjectName': object_name,
        'UploadId': upload_id
    }
    headers = {'Content-Type': 'application/json'}

    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print(f"Abort response status code: {response.status_code}")
    if response.status_code != 200:
        print(f"Abort response content: {response.text}")
        response.raise_for_status()

    result = response.json()
    print(f"Multipart upload aborted. Message: {result.get('Message')}")

def upload_file(file_path):
    upload_id = None
    object_name = os.path.basename(file_path)
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = 'application/octet-stream'

    print(f"Object name: {object_name}")
    print(f"Content type: {content_type}")

    try:
        # Step 1: Initiate multipart upload
        upload_id = initiate_multipart_upload(object_name, content_type)

        parts = []
        part_number = 1

        file_size = os.path.getsize(file_path)
        print(f"File size: {file_size} bytes")

        # Read all parts into a list
        part_data_list = []
        with open(file_path, 'rb') as f:
            while True:
                part_data = f.read(PART_SIZE)
                if not part_data:
                    break
                part_data_list.append((part_number, part_data))
                part_number += 1

        progress_data = {
            'total_size': file_size,
            'bytes_uploaded': 0,
            'total_time': 0
        }

        # Function to update progress
        def part_progress(part_number, time_taken, bytes_uploaded_in_part):
            progress_data['bytes_uploaded'] += bytes_uploaded_in_part
            progress_data['total_time'] += time_taken

            # Calculate average speed in bytes per second
            average_speed = progress_data['bytes_uploaded'] / progress_data['total_time'] if progress_data['total_time'] > 0 else 0

            # Estimate time remaining in seconds
            bytes_remaining = progress_data['total_size'] - progress_data['bytes_uploaded']
            estimated_time_remaining = bytes_remaining / average_speed if average_speed > 0 else 0

            # Calculate progress percentage
            progress_percent = (progress_data['bytes_uploaded'] / progress_data['total_size']) * 100

            # Update progress bar and label on the main thread
            root.after(0, update_progress, progress_percent, estimated_time_remaining)

        # Upload parts in parallel
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for part_number, part_data in part_data_list:
                futures.append(executor.submit(upload_part, upload_id, part_number, part_data, object_name, part_progress))

            for future in as_completed(futures):
                try:
                    part_num, etag = future.result()
                    parts.append((part_num, etag))
                except Exception as e:
                    print(f"An error occurred while uploading part: {e}")
                    raise e

        # Sort parts by PartNumber before completing
        parts.sort(key=lambda x: x[0])

        # Step 3: Complete multipart upload
        complete_multipart_upload(upload_id, parts, object_name)

    except Exception as e:
        print(f"An error occurred: {e}")
        if upload_id:
            # Step 4: Abort multipart upload
            abort_multipart_upload(upload_id, object_name)
        raise e

def start_upload(file_path):
    try:
        # Disable the upload button during upload
        upload_button.config(state=tk.DISABLED)
        # Reset progress bar
        progress_bar['value'] = 0
        progress_label.config(text="Starting upload...")
        upload_file(file_path)
        messagebox.showinfo("Success", f"File '{os.path.basename(file_path)}' uploaded successfully.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")
    finally:
        # Re-enable the upload button after upload
        upload_button.config(state=tk.NORMAL)
        progress_label.config(text="")

def select_file():
    file_path = filedialog.askopenfilename()
    if file_path:
        file_label.config(text=file_path)
        upload_button.config(state=tk.NORMAL)
        upload_button.file_path = file_path

def upload_button_clicked():
    file_path = upload_button.file_path
    threading.Thread(target=start_upload, args=(file_path,)).start()

def update_progress(progress_percent, estimated_time_remaining):
    # Convert estimated_time_remaining to minutes and seconds
    mins, secs = divmod(int(estimated_time_remaining), 60)
    if mins > 0:
        time_format = f"{mins} minutes {secs} seconds"
    else:
        time_format = f"{secs} seconds"

    progress_bar['value'] = progress_percent
    progress_label.config(text=f"Uploading... {progress_percent:.2f}% complete. Estimated time remaining: {time_format}.")

# Create the main window
root = tk.Tk()
root.title("File Uploader")

# Create a frame for the file selection
frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

# Add a label and button to select the file
file_label = tk.Label(frame, text="No file selected.")
file_label.pack()

select_button = tk.Button(frame, text="Select File", command=select_file)
select_button.pack(pady=5)

# Add an upload button
upload_button = tk.Button(frame, text="Upload File", state=tk.DISABLED, command=upload_button_clicked)
upload_button.pack(pady=5)
upload_button.file_path = None  # Store the file path as an attribute

# Add a progress bar
progress_bar = ttk.Progressbar(frame, orient='horizontal', length=300, mode='determinate')
progress_bar.pack(pady=10)

# Add a label to show progress percentage and estimated time
progress_label = tk.Label(frame, text="")
progress_label.pack()

# Start the GUI event loop
root.mainloop()
