// WebSocket connection
let socket;
let currentMode = 'code';
let isAnalyzing = false;

// DOM elements
const chatContainer = document.getElementById('chatContainer');
const submitBtn = document.getElementById('submitBtn');
const statusBar = document.getElementById('statusBar');
const statusText = statusBar.querySelector('.status-text');

const codeInput = document.getElementById('codeInput');
const repoInput = document.getElementById('repoInput');
const branchInput = document.getElementById('branchInput');
const pathInput = document.getElementById('pathInput');

// Initialize Socket.IO connection
function initSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log('Connected to server');
        updateStatus('Connected', true);
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        updateStatus('Disconnected', false);
    });

    socket.on('connected', (data) => {
        console.log('Server message:', data.message);
        addSystemMessage('Connected to Green Code Analyzer');
    });

    socket.on('progress', (data) => {
        console.log('Progress:', data.message);
        addProgressMessage(data.message);
    });

    socket.on('analysis_complete', (data) => {
        console.log('Analysis complete:', data);
        isAnalyzing = false;
        updateSubmitButton(false);

        if (data.total_findings === 0) {
            addSystemMessage('Analysis complete! No energy inefficiencies found. Your code looks great!');
        } else {
            addSystemMessage(`Analysis complete! Found ${data.total_findings} potential issue${data.total_findings > 1 ? 's' : ''}.`);
            displayFindings(data.findings);
        }

        // Scroll to bottom
        scrollToBottom();
    });

    socket.on('error', (data) => {
        console.error('Error:', data.message);
        isAnalyzing = false;
        updateSubmitButton(false);
        addErrorMessage(data.message);
        scrollToBottom();
    });
}

// Update connection status
function updateStatus(text, connected) {
    statusText.textContent = text;
    if (connected) {
        statusBar.classList.add('connected');
    } else {
        statusBar.classList.remove('connected');
    }
}

// Update submit button state
function updateSubmitButton(loading) {
    if (loading) {
        submitBtn.disabled = true;
        submitBtn.classList.add('loading');
        submitBtn.querySelector('.btn-text').textContent = 'Analyzing';
        submitBtn.querySelector('.btn-icon').textContent = '⏳';
    } else {
        submitBtn.disabled = false;
        submitBtn.classList.remove('loading');
        submitBtn.querySelector('.btn-text').textContent = 'Analyze Code';
        submitBtn.querySelector('.btn-icon').textContent = '🚀';
    }
}

// Add message to chat
function addMessage(content, className) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${className}`;

    if (typeof content === 'string') {
        messageDiv.textContent = content;
    } else {
        messageDiv.appendChild(content);
    }

    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function addUserMessage(text) {
    addMessage(text, 'user');
}

function addSystemMessage(text) {
    addMessage(text, 'system');
}

function addProgressMessage(text) {
    addMessage(text, 'progress');
}

function addErrorMessage(text) {
    addMessage(` ${text}`, 'error');
}

// Display findings
function displayFindings(findings) {
    findings.forEach((finding, index) => {
        const findingDiv = document.createElement('div');
        findingDiv.className = 'finding';

        let html = `
            <div class="finding-header">
                <span class="finding-number">Finding #${index + 1}</span>
                <div class="finding-meta">
        `;

        if (finding.file) {
            html += `<span class="meta-tag">📄 ${escapeHtml(finding.file)}</span>`;
        }
        if (finding.function_name) {
            html += `<span class="meta-tag">⚙️ ${escapeHtml(finding.function_name)}</span>`;
        }
        if (finding.start_line && finding.end_line) {
            html += `<span class="meta-tag">📍 Lines ${finding.start_line}-${finding.end_line}</span>`;
        }
        if (finding.complexity !== null && finding.complexity !== undefined) {
            html += `<span class="meta-tag">🔄 Complexity: ${finding.complexity}</span>`;
        }

        // Show taxonomy category if present
        if (finding.taxonomy_category) {
            html += `<span class="meta-tag taxonomy-tag">🏷️ ${escapeHtml(finding.taxonomy_category)}</span>`;
        }

        // Show similar example reference if present
        if (finding.similar_to_example) {
            html += `<span class="meta-tag example-tag">📚 Similar: ${escapeHtml(finding.similar_to_example)}</span>`;
        }

        html += `
                </div>
            </div>
            <div class="finding-content">
                <div class="finding-issue">${escapeHtml(finding.issue)}</div>
        `;

        if (finding.explanation) {
            // Use marked to render markdown, but sanitize? 
            // We trust the LLM output for now as per plan
            html += `
                <h4>Explanation</h4>
                <div class="finding-explanation markdown-body">${marked.parse(finding.explanation)}</div>
            `;
        }

        if (finding.problematic_code) {
            html += `
                <h4>Problematic Code</h4>
                <div class="finding-code">
                    <pre><code>${escapeHtml(finding.problematic_code)}</code></pre>
                </div>
            `;
        }

        if (finding.patch) {
            html += `
                <h4>Suggested Patch</h4>
                <div class="finding-patch">
                    <pre><code>${escapeHtml(finding.patch)}</code></pre>
                </div>
            `;
        }

        html += `
            </div>
        `;

        findingDiv.innerHTML = html;

        // Highlight code blocks
        findingDiv.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });

        chatContainer.appendChild(findingDiv);
    });
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Scroll chat to bottom
function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Handle mode switching
function switchMode(mode) {
    currentMode = mode;

    // Update mode buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-mode="${mode}"]`).classList.add('active');

    // Update input forms
    document.querySelectorAll('.input-form').forEach(form => {
        form.classList.remove('active');
    });
    document.getElementById(`${mode}Form`).classList.add('active');
}

// Handle form submission
function handleSubmit() {
    if (isAnalyzing) return;

    let data = {
        input_type: currentMode
    };

    let userMessage = '';

    // Validate and prepare data based on mode
    if (currentMode === 'code') {
        const code = codeInput.value.trim();
        if (!code) {
            addErrorMessage('Please enter some code to analyze');
            return;
        }
        data.code = code;
        userMessage = `Analyzing code snippet (${code.split('\n').length} lines)`;

    } else if (currentMode === 'repo') {
        const repoUrl = repoInput.value.trim();
        if (!repoUrl) {
            addErrorMessage('Please enter a repository URL');
            return;
        }
        data.repo_url = repoUrl;
        data.branch = branchInput.value.trim() || null;
        userMessage = `Analyzing repository: ${repoUrl}`;
        if (data.branch) {
            userMessage += ` (branch: ${data.branch})`;
        }

    } else if (currentMode === 'path') {
        const path = pathInput.value.trim();
        if (!path) {
            addErrorMessage('Please enter a local path');
            return;
        }
        data.path = path;
        userMessage = `Analyzing local path: ${path}`;
    }

    // Clear welcome message on first submission
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // Add user message
    addUserMessage(userMessage);

    // Update UI state
    isAnalyzing = true;
    updateSubmitButton(true);

    // Send analysis request
    console.log('Sending analysis request:', data);
    socket.emit('analyze', data);
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initialize WebSocket
    initSocket();

    // Mode selector buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchMode(btn.dataset.mode);
        });
    });

    // Submit button
    submitBtn.addEventListener('click', handleSubmit);

    // Enter key in text inputs
    [codeInput, repoInput, branchInput, pathInput].forEach(input => {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                handleSubmit();
            }
        });
    });
});
