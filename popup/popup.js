// Constants for emotion options
const EMOTIONS = {
  1: { text: "Frustrated to the extent that I'm considering quitting", color: "#e74c3c", shortText: "Frustrated" },
  2: { text: "Sad for needing to do it", color: "#9b59b6", shortText: "Sad" },
  3: { text: "Neutral", color: "#3498db", shortText: "Neutral" },
  4: { text: "Enjoying", color: "#2ecc71", shortText: "Enjoying" },
  5: { text: "Super thrilled", color: "#27ae60", shortText: "Thrilled" }
};

// DOM Elements
const tabButtons = document.querySelectorAll('.tab-btn');
const sections = document.querySelectorAll('.section');
const emotionOptions = document.querySelectorAll('.emotion-option');
const saveLogBtn = document.getElementById('saveLogBtn');
const activityInput = document.getElementById('activityInput');
const logSuccess = document.getElementById('logSuccess');
const logEntries = document.getElementById('logEntries');
const exportBtn = document.getElementById('exportBtn');
const frequencyButtons = document.querySelectorAll('.frequency-btn');

// Tab Navigation
tabButtons.forEach(button => {
  button.addEventListener('click', () => {
    // Remove active class from all tabs
    tabButtons.forEach(btn => btn.classList.remove('active'));
    sections.forEach(section => section.classList.remove('active'));
    
    // Add active class to clicked tab
    button.classList.add('active');
    
    // Show corresponding section
    const targetId = button.id.replace('Tab', 'Section');
    document.getElementById(targetId).classList.add('active');
    
    // Load data if navigating to history tab
    if (button.id === 'historyTab') {
      loadLogEntries();
    } else if (button.id === 'settingsTab') {
      loadSettings();
    }
  });
});

// Selected Emotion Tracking
let selectedEmotion = null;

emotionOptions.forEach(option => {
  option.addEventListener('click', () => {
    // Remove selected class from all options
    emotionOptions.forEach(opt => opt.classList.remove('selected'));
    
    // Add selected class to clicked option
    option.classList.add('selected');
    
    // Track selected emotion
    selectedEmotion = option.dataset.emotion;
  });
});

// Save Log Entry
saveLogBtn.addEventListener('click', async () => {
  const activity = activityInput.value.trim();
  
  if (!activity) {
    alert('Please enter what you are doing');
    return;
  }
  
  if (!selectedEmotion) {
    alert('Please select how you are feeling');
    return;
  }
  
  try {
    const response = await chrome.runtime.sendMessage({
      type: 'logEntry',
      data: {
        activity,
        emotion: selectedEmotion
      }
    });
    
    if (response.success) {
      // Show success message
      logSuccess.classList.remove('hidden');
      
      // Reset form
      activityInput.value = '';
      emotionOptions.forEach(opt => opt.classList.remove('selected'));
      selectedEmotion = null;
      
      // Hide success message after 3 seconds
      setTimeout(() => {
        logSuccess.classList.add('hidden');
      }, 3000);
    }
  } catch (error) {
    console.error('Error saving log entry:', error);
    alert('Error saving log entry. Please try again.');
  }
});

// Load Log Entries
async function loadLogEntries() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'getLogs' });
    const logs = response.logs || [];
    
    // Clear existing entries
    logEntries.innerHTML = '';
    
    if (logs.length === 0) {
      const emptyState = document.createElement('div');
      emptyState.className = 'empty-state';
      emptyState.innerHTML = '<p>No entries yet. Start logging your activities!</p>';
      logEntries.appendChild(emptyState);
      return;
    }
    
    // Create entry for each log
    logs.forEach(log => {
      const entry = document.createElement('div');
      entry.className = 'log-entry';
      
      entry.innerHTML = `
        <div class="log-entry-header">
          <span class="log-entry-timestamp">${log.formattedDate}</span>
          <span class="log-entry-emotion" data-emotion="${log.emotion}">${EMOTIONS[log.emotion].shortText}</span>
        </div>
        <div class="log-entry-activity">${log.activity}</div>
      `;
      
      logEntries.appendChild(entry);
    });
  } catch (error) {
    console.error('Error loading log entries:', error);
  }
}

// Export logs as CSV
exportBtn.addEventListener('click', async () => {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'getLogs' });
    const logs = response.logs || [];
    
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

// Load and display settings
async function loadSettings() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'getSettings' });
    const settings = response.settings;
    
    // Update UI to reflect current settings
    frequencyButtons.forEach(button => {
      const minutes = parseInt(button.dataset.minutes);
      button.classList.toggle('active', minutes === settings.frequency);
    });
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
      const response = await chrome.runtime.sendMessage({ type: 'getSettings' });
      const settings = response.settings;
      
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

// Initial load
document.addEventListener('DOMContentLoaded', () => {
  // Default to log tab
  document.getElementById('logTab').click();
});