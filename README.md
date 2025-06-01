# Activity & Emotion Logger - Chrome Extension

A Chrome extension that helps you track what you're doing and how you're feeling throughout your day. Get regular check-ins, maintain a log of your activities and emotions, and export data for further analysis.

## Features

- Periodic notifications to remind you to log what you're doing and how you're feeling
- Customizable notification frequency (15, 30, 45, or 60 minutes)
- Log viewer to review all past entries 
- Data export functionality (CSV format)
- Clean, intuitive user interface

## Installation Instructions

### For Development:

1. Clone or download this repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode" using the toggle in the top right
4. Click "Load unpacked" and select the extension folder
5. The extension should now appear in your Chrome toolbar

### Creating Icon Files

For a complete extension, you'll need to create PNG icons in the following sizes:
- 16x16 pixels (icons/icon16.png)
- 48x48 pixels (icons/icon48.png)
- 128x128 pixels (icons/icon128.png)

You can use any image editing software to create these icons.

## Usage

1. Click the extension icon in your toolbar to open the popup
2. Use the "Log" tab to record what you're doing and how you're feeling
3. View your past entries in the "History" tab
4. Configure notification frequency in the "Settings" tab
5. Export your data as CSV from the "History" tab or Options page

## Data Privacy

All your activity and emotion data is stored locally in your browser using Chrome's storage API. No data is sent to any external servers.

## License

This project is licensed under the MIT License.