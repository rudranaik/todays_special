// DOM Elements
const frequencyButtons = document.querySelectorAll('.frequency-btn');
const notificationsToggle = document.getElementById('notificationsToggle');
const exportBtn = document.getElementById('exportBtn');
const clearDataBtn = document.getElementById('clearDataBtn');
const overlay = document.getElementById('overlay');
const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');

// Constants for emotion options
const EMOTIONS = {
  1: { text: "Frustrated to the extent that I'm considering quitting" },
  2: { text: "Sad for needing to do it" },
  3: { text: "Neutral" },
  4: { text: "Enjoying" },
  5: { text: "Super thrilled" }
};

// Load and display settings
async function loadSettings() {
  try {
    const data = await chrome.storage.local.get('settings');
    const settings = data.settings || { frequency: 30, notifications: true };
    
    // Update UI to reflect current settings
    frequencyButtons.forEach(button => {
      const minutes = parseInt(button.dataset.minutes);
      button.classList.toggle('active', minutes === settings.frequency);
    });
    
    notificationsToggle.checked = settings.notifications;
  } catch (error) {
    console.error('Error loading settings:', error);
  }
}

// Update frequency setting
frequencyButtons.forEach(button => {
  button.addEventListener('click', async () => {
    // Remove active class from all buttons
    frequencyButtons.forEach(btn => btn.classList.remove('active'));
    
    // Add active class to clicked button
    button.classList.add('active');
    
    // Get selected frequency
    const frequency = parseInt(button.dataset.minutes);
    
    try {
      // Get current settings
      const data = await chrome.storage.local.get('settings');
      const settings = data.settings || { frequency: 30, notifications: true };
      
      // Update frequency
      settings.frequency = frequency;
      
      // Save updated settings
      await chrome.storage.local.set({ settings });
      
      // Notify background script
      await chrome.runtime.sendMessage({ type: 'settingsUpdated' });
    } catch (error) {
      console.error('Error updating settings:', error);
      alert('Error updating settings. Please try again.');
    }
  });
});

// Toggle notifications
notificationsToggle.addEventListener('change', async () => {
  try {
    // Get current settings
    const data = await chrome.storage.local.get('settings');
    const settings = data.settings || { frequency: 30, notifications: true };
    
    // Update notifications setting
    settings.notifications = notificationsToggle.checked;
    
    // Save updated settings
    await chrome.storage.local.set({ settings });
    
    // Notify background script
    await chrome.runtime.sendMessage({ type: 'settingsUpdated' });
  } catch (error) {
    console.error('Error updating notification settings:', error);
    alert('Error updating notification settings. Please try again.');
  }
});

// Export logs as CSV
exportBtn.addEventListener('click', async () => {
  try {
    const data = await chrome.storage.local.get('logs');
    const logs = data.logs || [];
    
    if (logs.length === 0) {
      alert('No log entries to export');
      return;
    }
    
    // Create CSV content
    const headers = ['Date', 'Activity', 'Emotion'];
    const rows = logs.map(log => [
      log.formattedDate,
      `"${log.activity.replace(/"/g, '""')}"`, // Escape quotes in CSV
      EMOTIONS[log.emotion].text
    ]);
    
    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n');
    
    // Create blob and download link
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `activity-log-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    
    // Clean up
    setTimeout(() => URL.revokeObjectURL(url), 100);
  } catch (error) {
    console.error('Error exporting logs:', error);
    alert('Error exporting logs. Please try again.');
  }
});

// Show clear data confirmation
clearDataBtn.addEventListener('click', () => {
  overlay.classList.remove('hidden');
});

// Cancel clear data
cancelDeleteBtn.addEventListener('click', () => {
  overlay.classList.add('hidden');
});

// Confirm clear data
confirmDeleteBtn.addEventListener('click', async () => {
  try {
    // Clear logs but keep settings
    const data = await chrome.storage.local.get('settings');
    await chrome.storage.local.clear();
    await chrome.storage.local.set({ 
      settings: data.settings || { frequency: 30, notifications: true },
      logs: [] 
    });
    
    overlay.classList.add('hidden');
    alert('All log data has been cleared successfully.');
  } catch (error) {
    console.error('Error clearing data:', error);
    alert('Error clearing data. Please try again.');
    overlay.classList.add('hidden');
  }
});

// Initial load
document.addEventListener('DOMContentLoaded', loadSettings);