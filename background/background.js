// Constants for emotion options
const EMOTIONS = {
  FRUSTRATED: { id: 1, text: "Frustrated to the extent that I'm considering quitting", color: "#e74c3c" },
  SAD: { id: 2, text: "Sad for needing to do it", color: "#9b59b6" },
  NEUTRAL: { id: 3, text: "Neutral", color: "#3498db" },
  ENJOYING: { id: 4, text: "Enjoying", color: "#2ecc71" },
  THRILLED: { id: 5, text: "Super thrilled", color: "#27ae60" }
};

// Default settings
const DEFAULT_SETTINGS = {
  frequency: 30, // minutes
  notifications: true
};

// Initialize extension
chrome.runtime.onInstalled.addListener(async () => {
  console.log('Activity & Emotion Logger installed');
  
  // Initialize settings
  const storage = await chrome.storage.local.get('settings');
  if (!storage.settings) {
    await chrome.storage.local.set({ 
      settings: DEFAULT_SETTINGS,
      logs: [] 
    });
  }
  
  // Schedule first alarm
  setupAlarm();
});

// Setup notification alarm based on current settings
async function setupAlarm() {
  const storage = await chrome.storage.local.get('settings');
  const settings = storage.settings || DEFAULT_SETTINGS;
  
  // Clear any existing alarms
  await chrome.alarms.clearAll();
  
  // Create new alarm with current frequency
  chrome.alarms.create('logReminder', { 
    periodInMinutes: settings.frequency 
  });
  
  console.log(`Alarm set to trigger every ${settings.frequency} minutes`);
}

// Listen for alarm
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'logReminder') {
    showNotification();
  }
});

// Display notification
function showNotification() {
  chrome.notifications.create({
    type: 'basic',
    iconUrl: '/icons/icon128.png',
    title: 'Activity & Emotion Check-in',
    message: 'What are you working on right now? How are you feeling?',
    buttons: [
      { title: 'Log Now' }
    ],
    priority: 2
  });
}

// Handle notification button click
chrome.notifications.onButtonClicked.addListener((notificationId, buttonIndex) => {
  if (buttonIndex === 0) {
    // Open popup for logging
    chrome.action.openPopup();
  }
});

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'settingsUpdated') {
    setupAlarm();
    sendResponse({ success: true });
  }
  
  if (message.type === 'logEntry') {
    logActivity(message.data)
      .then(() => sendResponse({ success: true }))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true; // Required for async sendResponse
  }
  
  if (message.type === 'getSettings') {
    chrome.storage.local.get('settings', (data) => {
      sendResponse({ settings: data.settings || DEFAULT_SETTINGS });
    });
    return true; // Required for async sendResponse
  }
  
  if (message.type === 'getLogs') {
    chrome.storage.local.get('logs', (data) => {
      sendResponse({ logs: data.logs || [] });
    });
    return true; // Required for async sendResponse
  }
});

// Save activity log to storage
async function logActivity(logData) {
  const timestamp = new Date().toISOString();
  const newEntry = {
    id: Date.now(), // Unique ID based on timestamp
    timestamp,
    activity: logData.activity,
    emotion: logData.emotion,
    formattedDate: new Date().toLocaleString()
  };
  
  const data = await chrome.storage.local.get('logs');
  const logs = data.logs || [];
  logs.unshift(newEntry); // Add to beginning of array
  
  await chrome.storage.local.set({ logs });
  console.log('Activity logged:', newEntry);
  return newEntry;
}