# File Uploader with Progress Bar and Estimated Time

This Python script provides a graphical user interface (GUI) for uploading large files using multipart upload. 

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Running the Script](#running-the-script)
  - [Using the Application](#using-the-application)
- [Converting to an Executable](#converting-to-an-executable)
  - [Using PyInstaller](#using-pyinstaller)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Features

- **Multipart Upload:** Efficiently uploads large files by splitting them into smaller parts.
- **GUI Interface:** User-friendly interface using Tkinter.
- **Progress Bar:** Visual representation of the upload progress.
- **Estimated Time Remaining:** Dynamically calculated based on actual bytes uploaded and upload speed.
- **Error Handling:** Provides informative messages in case of upload failures.

## Requirements

- **Python 3.6 or higher**
- **Required Python Packages:**
  - `requests`
  - `tkinter` (comes pre-installed with Python on most systems)
  - `ttk` (part of `tkinter`)
  - `PyInstaller` (optional, for converting to executable)

## Installation

1. **Install Required Packages:**

   Use `pip` to install the required Python packages.

   ```bash
   pip install requests
   ```

   - Note: `tkinter` and `ttk` are usually included with standard Python installations. If not, refer to your operating system's instructions for installing `tkinter`.

## Usage

### Running the Script

1. **Configure API Settings:**

   - Open the script file (e.g., `file_uploader.py`) in a text editor.
   - Update the `API_BASE_URL` and `BUCKET_NAME` variables with your API endpoint and bucket name.

   ```python
   API_BASE_URL = 'http://your-api-endpoint/api/FileAccess'
   BUCKET_NAME = 'your-bucket-name'
   ```

2. **Run the Script:**

   Execute the script using Python from your terminal or command prompt.

   ```bash
   python File_Upload_Tool.py
   ```

### Using the Application

1. **Launch the Application:**

   - Upon running the script, a GUI window titled "File Uploader" will appear.

2. **Select a File to Upload:**

   - Click the **Select File** button.
   - Browse and choose the file you wish to upload.
   - The selected file path will be displayed in the application.

3. **Start the Upload:**

   - Click the **Upload File** button.
   - The upload process will begin, and the progress bar will start moving.

4. **Monitor Progress:**

   - The progress bar shows the percentage of the file uploaded.
   - An estimated time remaining is displayed below the progress bar.

5. **Completion:**

   - Upon successful upload, a success message will appear.
   - If an error occurs, an error message will be displayed.

## Converting to an Executable

To make it easier for users without Python installed, you can convert the script into a standalone executable using **PyInstaller**.

### Using PyInstaller

1. **Install PyInstaller:**

   ```bash
   pip install pyinstaller
   ```

2. **Prepare the Script:**

   - Ensure the script has the correct API configurations.
   - Save the script with a suitable name, e.g., `file_uploader.py`.

3. **Create the Executable:**

   Navigate to the directory containing your script and run:

   ```bash
   pyinstaller --onefile --windowed file_uploader.py
   ```

   - `--onefile`: Packages everything into a single executable.
   - `--windowed`: Prevents a console window from appearing (useful for GUI applications).

4. **Locate the Executable:**

   - After the process completes, find the executable in the `dist` folder created by PyInstaller.

5. **Run the Executable:**

   - Double-click the executable (`file_uploader.exe` on Windows) to launch the application.

6. **Distribute the Application:**

   - You can now distribute the executable file to users who do not have Python installed.

## Troubleshooting

- **ImportError: No module named 'tkinter':**
  - On some systems, `tkinter` may not be installed by default.
  - **Windows:** Usually comes with Python.
  - **macOS:** Install Python from the official installer at [python.org](https://www.python.org/downloads/mac-osx/).
  - **Linux (Ubuntu/Debian):**

    ```bash
    sudo apt-get install python3-tk
    ```

- **Errors During Executable Creation:**
  - Ensure all dependencies are installed in the same Python environment used by PyInstaller.
  - Run PyInstaller in a virtual environment if necessary.

- **Application Not Connecting to API:**
  - Verify that `API_BASE_URL` is correct and accessible.
  - Ensure that any required authentication or headers are properly configured in the script.
