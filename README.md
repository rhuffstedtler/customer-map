# Customer Drive-Time & Zip Code Map Generator

This tool takes a spreadsheet (`.csv`) of customer addresses, calculates the estimated **minimum and maximum Monday 9:00 AM drive time** from your office using Google Maps traffic data, and generates an interactive HTML map showing every customer color-coded by zip code—complete with zip code borders, zip labels, and drive-time hover cards.

---

## Table of Contents
1. [What This Tool Does](#1-what-this-tool-does)
2. [Step 1: Set Up Your Google Cloud API Key](#2-step-1-set-up-your-google-cloud-api-key)
3. [Step 2: Set Up Python on Windows](#3-step-2-set-up-python-on-windows)
4. [Step 3: Configure & Run the Script](#4-step-3-configure--run-the-script)
5. [Understanding the Output Files](#5-understanding-the-output-files)
6. [How Caching Works (Saving Time & API Costs)](#6-how-caching-works-saving-time--api-costs)
7. [Troubleshooting Common Issues](#7-troubleshooting-common-issues)

---

## 1. What This Tool Does

* **Calculates Monday 9:00 AM Drive Times:** Queries Google Maps for both free-flow (`staticDuration`) and rush-hour traffic (`duration`) estimates arriving at **9:00 AM next Monday** from your office (`1242 Clairmont Rd, Decatur, GA 30030`).
* **Enriches Your Spreadsheet:** Adds four columns to your CSV:
  * `min_drive_time_mins`
  * `max_drive_time_mins`
  * `latitude`
  * `longitude`
* **Builds an Interactive Map (`customer_map.html`):**
  * Displays a red home pin for your office.
  * Plots every customer with a pin color-coded by their 5-digit zip code.
  * Draws U.S. Census zip code borders and labels in the exact same color as the pins inside them.
  * Shows the customer's name, zip code, and Monday 9:00 AM drive-time window when you hover over or click any pin.

---

## 2. Step 1: Set Up Your Google Cloud API Key

To look up addresses and calculate Monday morning traffic, the script needs a free/low-cost API key from Google Cloud. *(Google provides a $200/month free credit for Maps Platform, which easily covers hundreds of customer lookups.)*

### A. Create a Google Cloud Project & Enable Billing
1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and sign in with your Google account.
2. Click the **Project dropdown** in the top-left bar (next to the Google Cloud logo) and click **New Project**.
3. Give it a name (e.g., `Customer-Drive-Map`) and click **Create**, then make sure that project is selected in the top-left dropdown.
4. Open the left navigation menu (**☰**) and click **Billing**. Follow the prompts to link a billing account to your project. *(Google Maps APIs will return a "Permission Denied" error if billing is not linked, even if your usage stays inside the free monthly credit.)*

### B. Enable the Required APIs
1. Open the left navigation menu (**☰**) and go to **APIs & Services > Library**.
2. Search for **Routes API**, click on it, and click the blue **Enable** button. *(Make sure you select **Routes API**, not the older "Directions API".)*
3. Go back to **APIs & Services > Library**, search for **Geocoding API**, click on it, and click **Enable**.

### C. Create and Restrict Your API Key
1. Open the left navigation menu (**☰**) and go to **APIs & Services > Credentials**.
2. At the top of the page, click **+ Create credentials** and choose **API key**.
3. Copy the generated key string (it starts with `AIza...`) and save it somewhere safe for Step 3.
4. Click **Edit API key** (or click the name of your new key in the list) to secure it:
   * Under **Application restrictions**, leave it set to **None** (if set to *Websites*, a local Python script will be blocked).
   * Under **API restrictions**, select **Restrict key**, click the dropdown, and check **Routes API** and **Geocoding API**.
   * Click **Save** at the bottom. *(Note: If Google shows a warning popup about active usage, type `UPDATE` and click **Update**.)*
5. **Wait 2–3 minutes** after saving before running the script so Google's servers finish updating your key permissions.

---

## 3. Step 2: Set Up Python on Windows

If you have never run Python on your Windows computer before, follow these steps once:

### A. Install Python
1. Download the latest Windows installer from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer. **CRITICAL:** On the very first screen of the installer, check the box at the bottom that says **"Add python.exe to PATH"** before clicking **Install Now**.
3. When setup finishes, close the installer.

### B. Set Up Your Project Folder
1. Create a folder on your computer, for example:
   `C:\Users\YourName\Documents\customer-map`
2. Place both of these files inside that folder:
   * `generate_map.py` (the Python script)
   * `20261121 Active Recurring Customers.csv` (your input CSV file)

### C. Install Required Python Libraries
1. Open the folder in Windows File Explorer.
2. Click the **address bar** at the top of the File Explorer window, type `cmd`, and press **Enter**. This opens a black Command Prompt window already pointed at your folder.
3. Paste the following command into the Command Prompt and press **Enter**:
   ```bat
   pip install pandas requests folium
   ```
4. Wait ~15 seconds until you see `Successfully installed...` and the command prompt returns.

---

## 4. Step 3: Configure & Run the Script

### A. Add Your API Key to the Script
1. Right-click `generate_map.py` and select **Open with > Notepad** (or VS Code / any text editor).
2. Near the top of the file, find this line:
   ```python
   API_KEY = "YOUR_NEW_API_KEY"
   ```
3. Replace `YOUR_NEW_API_KEY` with the key you copied in Step 1 (keep the quotation marks around it).
4. *(Optional)* If your input CSV has a different filename or your office address changes, update these lines right below `API_KEY`:
   ```python
   INPUT_CSV = "20261121 Active Recurring Customers.csv"
   ORIGIN = "1242 Clairmont Rd, Decatur, GA 30030"
   ```
5. Press **Ctrl + S** to save `generate_map.py` and close the editor.

### B. Verify Input CSV Column Names
Make sure your input `.csv` file contains these column headers:
* `user__first_name`
* `user__last_name`
* `address_line_one`
* `city`
* `state`
* `zip_code`

### C. Run the Script
In the Command Prompt window inside your folder, type:
```bat
python generate_map.py
```
Press **Enter**. You will see progress printed line-by-line for every customer:
```text
[1/59] 2550 Blackmon Dr, Decatur, GA, 30033 -> 4.6–5.8 min (33.8065, -84.2891)
[2/59] 2415 Picadilly Place, Decatur, GA, 30034 -> 23.1–24.2 min (33.7198, -84.2481)
...
Saved enriched CSV to '20261121_Customers_With_Drive_Times.csv'.
Fetching polygon boundaries for 23 zip codes from U.S. Census TIGERweb...
Saved zip boundaries to 'ga_zcta_boundaries.geojson'.
Saved map to 'customer_map.html'.
```

---

## 5. Understanding the Output Files

After the script finishes, you will see three generated files in your folder:

1. **`20261121_Customers_With_Drive_Times.csv`**
   * Open this in Excel or Google Sheets. It contains all your original customer columns plus `min_drive_time_mins`, `max_drive_time_mins`, `latitude`, and `longitude`.
2. **`customer_map.html`**
   * Double-click this file to open it in Chrome, Edge, or any web browser.
   * **Zoom & Pan:** Scroll to zoom in/out; click and drag to move around the metro area.
   * **Hover:** Move your mouse over any pin to see the customer's name, zip code, and Monday 9:00 AM drive time.
   * **Click:** Click any pin to open a card with their full street address.
   * **Share:** You can email `customer_map.html` directly to teammates—it is completely self-contained and requires no special software to view.
3. **`ga_zcta_boundaries.geojson`**
   * A local cache of the U.S. Census zip code boundary shapes so the map builds instantaneously next time.

---

## 6. How Caching Works (Saving Time & API Costs)

The script automatically avoids making duplicate Google Maps API calls:

* **Normal Run (`python generate_map.py`):**
  If `20261121_Customers_With_Drive_Times.csv` already exists in the folder, the script reads the saved drive times and coordinates directly from it and regenerates `customer_map.html` in less than 1 second with **zero Google API calls**.
* **Refresh Run (`python generate_map.py --refresh`):**
  Whenever you update `20261121 Active Recurring Customers.csv` with new customers or changed addresses, pass the `--refresh` flag to force fresh Google Maps drive-time and coordinate lookups:
  ```bat
  python generate_map.py --refresh
  ```

---

## 7. Troubleshooting Common Issues

| Error / Symptom | Cause | How to Fix |
| :--- | :--- | :--- |
| **`'python' is not recognized as an internal or external command`** | Python was installed without checking *"Add python.exe to PATH"*. | Re-run the Python installer, click **Modify**, check **Add Python to environment variables**, and restart Command Prompt. |
| **`[FATAL - ROUTES API ERROR] (PERMISSION_DENIED)`** | Either **Routes API** isn't enabled, billing isn't linked, or Google is still propagating your key update. | Wait 3 minutes and re-run. If it persists, verify **Routes API** is enabled and **Billing** is active in Google Cloud Console. |
| **`PermissionError: [Errno 13] Permission denied: '...With_Drive_Times.csv'`** | You have the output CSV file open in Excel while the script is trying to overwrite it. | Close the CSV file in Excel. *(The script will also save a timestamped backup CSV automatically so your API results aren't lost.)* |
| **Map pins appear, but zip code borders are missing** | The U.S. Census TIGERweb server was temporarily slow or unreachable. | Re-run `python generate_map.py` once your internet connection is steady to download `ga_zcta_boundaries.geojson`. |
| **Security Reminder** | Never share your `generate_map.py` file with your `API_KEY` still pasted inside it. | Before emailing the script to a coworker, replace your key with `"YOUR_NEW_API_KEY"` so each person uses their own key. |
```

You can save this directly as `README.md` in your `C:\Users\rhuff\Development\customer-map\` folder alongside `generate_map.py`.