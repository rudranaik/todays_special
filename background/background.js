// Constants for emotion options
const DEFAULT_EMOTIONS = {
  1: { id: 1, text: "Frustrated to the extent that I'm considering quitting", color: "#e74c3c", name: "Frustrated" },
  2: { id: 2, text: "Sad for needing to do it", color: "#9b59b6", name: "Sad" },
  3: { id: 3, text: "Neutral", color: "#3498db", name: "Neutral" },
  4: { id: 4, text: "Enjoying", color: "#2ecc71", name: "Enjoying" },
  5: { id: 5, text: "Super thrilled", color: "#27ae60", name: "Thrilled" }
};

// Default settings
const DEFAULT_SETTINGS = {
  frequency: 30, // minutes
  notifications: true,
  emotions: DEFAULT_EMOTIONS,
  nextPromptTime: null
};

// Initialize extension
chrome.runtime.onInstalled.addListener(async () => {
  console.log('Activity & Emotion Logger installed');
  
  // Initialize settings
  const storage = await chrome.storage.local.get('settings');
  if (!storage.settings) {
    const settings = { ...DEFAULT_SETTINGS };
    settings.nextPromptTime = new Date(Date.now() + settings.frequency * 60000).toISOString();
    await chrome.storage.local.set({ 
      settings,
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

  // Update next prompt time
  settings.nextPromptTime = new Date(Date.now() + settings.frequency * 60000).toISOString();
  await chrome.storage.local.set({ settings });
  
  console.log(`Alarm set to trigger every ${settings.frequency} minutes`);
}

// Listen for alarm
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'logReminder') {
    showNotification();
    updateNextPromptTime();
  }
});

// Update next prompt time
async function updateNextPromptTime() {
  const storage = await chrome.storage.local.get('settings');
  const settings = storage.settings || DEFAULT_SETTINGS;
  settings.nextPromptTime = new Date(Date.now() + settings.frequency * 60000).toISOString();
  await chrome.storage.local.set({ settings });
}

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
    return true;
  }
  
  if (message.type === 'getSettings') {
    chrome.storage.local.get('settings', (data) => {
      sendResponse({ settings: data.settings || DEFAULT_SETTINGS });
    });
    return true;
  }
  
  if (message.type === 'getLogs') {
    chrome.storage.local.get('logs', (data) => {
      sendResponse({ logs: data.logs || [] });
    });
    return true;
  }

  if (message.type === 'updateEmotions') {
    updateEmotions(message.data)
      .then(() => sendResponse({ success: true }))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
});

// Save activity log to storage
async function logActivity(logData) {
  const timestamp = new Date().toISOString();
  const date = new Date().toLocaleDateString();
  const newEntry = {
    id: Date.now(),
    timestamp,
    date,
    activity: logData.activity,
    emotion: logData.emotion,
    formattedDate: new Date().toLocaleString()
  };
  
  const data = await chrome.storage.local.get('logs');
  const logs = data.logs || [];
  logs.unshift(newEntry);
  
  await chrome.storage.local.set({ logs });
  console.log('Activity logged:', newEntry);
  return newEntry;
}

// Update emotion names
async function updateEmotions(emotions) {
  const storage = await chrome.storage.local.get('settings');
  const settings = storage.settings || DEFAULT_SETTINGS;
  settings.emotions = emotions;
  await chrome.storage.local.set({ settings });
  return settings;
}