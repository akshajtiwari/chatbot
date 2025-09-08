// --- Global State ---
let statusInterval = null; // To hold our polling interval

// --- DOM Elements ---
const configSelect = document.getElementById('config-select');
const loadConfigBtn = document.getElementById('load-config-btn');
const newConfigBtn = document.getElementById('new-config-btn');
const saveConfigBtn = document.getElementById('save-config-btn');
const startSearchingBtn = document.getElementById('start-searching-btn');
const stopSearchingBtn = document.getElementById('stop-searching-btn');
const triggerSearchBtn = document.getElementById('trigger-search-btn');
const loadDocumentsBtn = document.getElementById('load-documents-btn');
const documentsTableBody = document.querySelector('#documents-table tbody');
const responseMessage = document.getElementById('response-message');
const form = document.getElementById('searcher-form');
const statusIndicator = document.getElementById('searcher-status-indicator');

// --- Functions ---

function clearForm() {
    form.reset();
    document.getElementById('config_id').value = '';
    configSelect.value = '';
    updateUIForStatus({}); // Reset UI
}

function showMessage(msg, type) {
    responseMessage.textContent = msg;
    responseMessage.className = `message-${type}`;
}


function updateUIForStatus(runningSearchers) {
    const selectedConfigId = configSelect.value;
    const isRunning = selectedConfigId && runningSearchers[selectedConfigId] && runningSearchers[selectedConfigId].status === 'running';
    const hasError = selectedConfigId && runningSearchers[selectedConfigId] && runningSearchers[selectedConfigId].status === 'error';

    // Enable/disable buttons based on status
    startSearchingBtn.disabled = isRunning;
    stopSearchingBtn.disabled = !isRunning;
    triggerSearchBtn.disabled = !isRunning;
    loadConfigBtn.disabled = isRunning;
    saveConfigBtn.disabled = isRunning;
    configSelect.disabled = Object.keys(runningSearchers).length > 0; // Disable dropdown if any searcher is active

    if (isRunning) {
        statusIndicator.textContent = 'Status: Running...';
        statusIndicator.style.color = 'green';
    } else if (hasError) {
        statusIndicator.textContent = 'Status: Error!';
        statusIndicator.style.color = 'red';
        // Display the specific error from the backend
        showMessage(`Backend Error: ${runningSearchers[selectedConfigId].error_message}`, 'error');
        stopStatusPolling(); // Stop checking once an error is found
    } else {
        statusIndicator.textContent = 'Status: Stopped.';
        statusIndicator.style.color = 'grey';
    }
}


function startStatusPolling() {
    if (statusInterval) clearInterval(statusInterval); // Clear any existing interval
    statusInterval = setInterval(async () => {
        try {
            const response = await fetch('/get_status');
            const runningSearchers = await response.json();
            updateUIForStatus(runningSearchers);
            // If the selected searcher is no longer running, stop polling
            if (configSelect.value && !runningSearchers[configSelect.value]) {
                stopStatusPolling();
            }
        } catch (e) {
            console.error("Status poll failed:", e);
            stopStatusPolling();
        }
    }, 2000); // Check every 2 seconds
}

function stopStatusPolling() {
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
    // Final UI update to ensure it shows 'stopped'
    updateUIForStatus({});
}

// --- Event Listeners ---
document.addEventListener('DOMContentLoaded', startStatusPolling); // Start polling on page load

configSelect.addEventListener('change', () => {
    // When dropdown changes, update the UI immediately based on the last known status
    fetch('/get_status').then(res => res.json()).then(updateUIForStatus);
});

newConfigBtn.addEventListener('click', clearForm);

loadConfigBtn.addEventListener('click', async () => {
    const configId = configSelect.value;
    if (!configId) return;
    try {
        const response = await fetch(`/get_config/${configId}`);
        const config = await response.json();
        document.getElementById('config_id').value = config._id;
        document.getElementById('erp_name').value = config.erp_name;
        document.getElementById('login_url').value = config.login_url;
        document.getElementById('username_payload_key').value = config.username_payload_key;
        document.getElementById('password_payload_key').value = config.password_payload_key;
        document.getElementById('target_urls').value = config.target_urls.join('\n');
        document.getElementById('supported_file_types').value = config.supported_file_types.join('\n');
        showMessage('Configuration loaded.', 'success');
    } catch (e) { showMessage('Failed to load config.', 'error'); }
});

saveConfigBtn.addEventListener('click', async () => {
    const formData = {
        config_id: document.getElementById('config_id').value,
        erp_name: document.getElementById('erp_name').value,
        login_url: document.getElementById('login_url').value,
        username_payload_key: document.getElementById('username_payload_key').value,
        password_payload_key: document.getElementById('password_payload_key').value,
        target_urls: document.getElementById('target_urls').value.split('\n').filter(Boolean),
        supported_file_types: document.getElementById('supported_file_types').value.split('\n').filter(Boolean),
    };
    try {
        const response = await fetch('/save_config', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });
        const result = await response.json();
        showMessage(result.message, 'success');
        window.location.reload();
    } catch (e) { showMessage('Error saving config.', 'error'); }
});

startSearchingBtn.addEventListener('click', async () => {
    const payload = {
        config_id: document.getElementById('config_id').value,
        username: document.getElementById('username').value,
        password: document.getElementById('password').value,
    };
    if (!payload.config_id) { showMessage('Please load a config first.', 'error'); return; }
    try {
        const response = await fetch('/start_searching', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        showMessage(result.message, response.ok ? 'success' : 'error');
        if (response.ok) {
            startStatusPolling(); // Start checking the status
        }
    } catch (e) { showMessage('Error starting searcher.', 'error'); }
});

stopSearchingBtn.addEventListener('click', async () => {
    const payload = { config_id: document.getElementById('config_id').value };
    try {
        const response = await fetch('/stop_searching', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        showMessage(result.message, 'success');
        stopStatusPolling(); // Stop checking status
    } catch (e) { showMessage('Error stopping searcher.', 'error'); }
});

triggerSearchBtn.addEventListener('click', async () => {
    const payload = { config_id: document.getElementById('config_id').value };
    try {
        await fetch('/trigger_search', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        showMessage('Manual search triggered!', 'info');
    } catch (e) { showMessage('Error triggering search.', 'error'); }
});

// --- Data Management (Unchanged) ---
loadDocumentsBtn.addEventListener('click', async () => {
    try {
        const response = await fetch('/get_documents');
        const documents = await response.json();
        documentsTableBody.innerHTML = '';
        documents.forEach(doc => {
            const row = documentsTableBody.insertRow();
            const source = doc.file_name || doc.source_url;
            const timestamp = new Date(doc.download_timestamp * 1000).toLocaleString();
            row.innerHTML = `
                <td>${source}</td>
                <td>${doc.status}</td>
                <td>${doc.file_type}</td>
                <td>${timestamp}</td>
                <td><button class="delete-btn" data-id="${doc._id}">Delete</button></td>
            `;
        });
        showMessage(`Loaded ${documents.length} documents.`, 'success');
    } catch (e) { showMessage('Error loading documents.', 'error'); }
});

documentsTableBody.addEventListener('click', async (event) => {
    if (event.target.classList.contains('delete-btn')) {
        const docId = event.target.dataset.id;
        if (confirm('Are you sure you want to delete this document?')) {
            try {
                await fetch(`/delete_document/${docId}`, { method: 'POST' });
                event.target.closest('tr').remove();
                showMessage('Document deleted.', 'success');
            } catch (e) { showMessage('Error deleting document.', 'error'); }
        }
    }
});

