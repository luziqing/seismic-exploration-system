/**
 * llm-client.js -- AI assistant chat sidebar, SSE streaming chat, multi-provider settings
 * Load order: after sam-client.js (loaded last)
 */

// ── Global state ──────────────────────────────────────────────
let chatMessages = [];
let chatStreaming = false;
let chatAbortController = null;
let chatSidebarVisible = false;
let llmConfigCache = null;
let chatSidebarEl = null;
let chatMessagesEl = null;
let chatInputEl = null;
let chatLoadingEl = null;

// ── Sidebar DOM ────────────────────────────────────────

function createChatSidebar() {
    const sidebar = document.createElement('div');
    sidebar.id = 'chatSidebar';

    // Header
    const header = document.createElement('div');
    header.className = 'chat-header';
    header.innerHTML =
        '<span>AI assistant</span>' +
        '<span class="chat-spacer"></span>' +
        '<span class="chat-config-icon" id="chatConfigBtn" title="Settings">⚙️</span>' +
        '<span class="chat-close-icon" id="chatCloseBtn" title="Close">✕</span>';
    sidebar.appendChild(header);

    // Messages
    const messagesDiv = document.createElement('div');
    messagesDiv.className = 'chat-messages';
    messagesDiv.id = 'chatMessages';
    sidebar.appendChild(messagesDiv);
    chatMessagesEl = messagesDiv;

    // Loading animation
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'chat-loading';
    loadingDiv.id = 'chatLoading';
    loadingDiv.innerHTML =
        '<span class="chat-dot"></span>' +
        '<span class="chat-dot"></span>' +
        '<span class="chat-dot"></span>';
    sidebar.appendChild(loadingDiv);
    chatLoadingEl = loadingDiv;

    // Input area
    const inputArea = document.createElement('div');
    inputArea.className = 'chat-input-area';
    const textarea = document.createElement('textarea');
    textarea.id = 'chatInput';
    textarea.placeholder = 'Type a message (Enter to send, Shift+Enter for a new line)';
    textarea.rows = 2;
    chatInputEl = textarea;

    const sendBtn = document.createElement('button');
    sendBtn.textContent = 'Send';
    sendBtn.id = 'chatSendBtn';

    inputArea.appendChild(textarea);
    inputArea.appendChild(sendBtn);
    sidebar.appendChild(inputArea);

    document.body.appendChild(sidebar);
    chatSidebarEl = sidebar;

    // ── Event wiring ──────────────────────────────────────────
    document.getElementById('chatConfigBtn').onclick = showLLMConfigModal;
    document.getElementById('chatCloseBtn').onclick = toggleChatSidebar;
    sendBtn.onclick = sendChatMessage;
    textarea.onkeydown = function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    };
}

// ── Message rendering ──────────────────────────────────────────────

function appendMessage(role, content) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-msg ' + role;
    msgDiv.textContent = content;
    chatMessagesEl.appendChild(msgDiv);
    scrollChatToBottom();
    return msgDiv;
}

function scrollChatToBottom() {
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function setChatLoading(show) {
    if (show) {
        chatLoadingEl.classList.add('active');
    } else {
        chatLoadingEl.classList.remove('active');
    }
}

// ── SSE streaming core ──────────────────────────────────────

async function sendChatMessage() {
    const text = chatInputEl.value.trim();
    if (!text || chatStreaming) return;
    chatInputEl.value = '';
    chatInputEl.focus();

    chatMessages.push({ role: 'user', content: text });
    appendMessage('user', text);

    setChatLoading(true);
    chatStreaming = true;

    const msgEl = appendMessage('assistant', '');
    let fullContent = '';

    chatAbortController = new AbortController();
    try {
        const resp = await fetch('/api/llm/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: chatMessages }),
            signal: chatAbortController.signal,
        });

        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error('HTTP ' + resp.status + ': ' + errText);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const payload = line.slice(6).trim();
                    if (payload === '[DONE]') continue;
                    try {
                        const parsed = JSON.parse(payload);
                        if (parsed.token) {
                            fullContent += parsed.token;
                            msgEl.textContent = fullContent;
                            scrollChatToBottom();
                        } else if (parsed.error) {
                            fullContent = parsed.error;
                            msgEl.textContent = '❌ ' + fullContent;
                        }
                    } catch (e) {
                        // skip JSON that does not parse
                    }
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            msgEl.textContent = '❌ Connection failed: ' + err.message;
            fullContent = msgEl.textContent;
        }
    } finally {
        setChatLoading(false);
        chatStreaming = false;
        chatAbortController = null;
        if (fullContent && !fullContent.startsWith('❌')) {
            chatMessages.push({ role: 'assistant', content: fullContent });
        } else if (!fullContent) {
            chatMessages.push({ role: 'assistant', content: '(empty response)' });
            msgEl.textContent = '(empty response)';
        }
    }
}

// ── Sidebar toggle ────────────────────────────────────────────

function toggleChatSidebar() {
    chatSidebarVisible = !chatSidebarVisible;
    if (chatSidebarVisible) {
        chatSidebarEl.style.display = 'flex';
        // Make room in the main container
        const mainContainer = document.querySelector('.main-container');
        if (mainContainer) mainContainer.style.marginRight = '380px';
        // Shift the slice panel too
        const slicePanel = document.getElementById('slicePanel');
        if (slicePanel) slicePanel.style.marginRight = '380px';
        chatInputEl.focus();
    } else {
        chatSidebarEl.style.display = 'none';
        const mainContainer = document.querySelector('.main-container');
        if (mainContainer) mainContainer.style.marginRight = '';
        const slicePanel = document.getElementById('slicePanel');
        if (slicePanel) slicePanel.style.marginRight = '';
    }
    // Trigger a canvas resize
    window.dispatchEvent(new Event('resize'));
}

function clearChat() {
    chatMessages = [];
    if (chatMessagesEl) chatMessagesEl.innerHTML = '';
}

// ── VLM slice interpretation ─────────────────────────────────────

function captureCanvasComposite() {
    const canvas = document.getElementById('seismicCanvas');
    if (!canvas) return null;
    return canvas.toDataURL('image/png').split(',')[1];  // strip the data:image/png;base64, prefix
}

function buildSliceContext() {
    const ctx = {
        direction: typeof curDir !== 'undefined' ? curDir : 'inline',
        line_index: typeof curIndex !== 'undefined' ? curIndex : 0,
        volume_name: (typeof volInfo !== 'undefined' && volInfo.name) ? volInfo.name : 'not loaded',
        coords: {},
        y_unit: (typeof yAxisUnit !== 'undefined' && yAxisUnit === 'depth') ? 'Depth (m)' : 'Time (ms)',
    };

    // Direction short names
    const dirLabels = { inline: 'IL', crossline: 'XL', timeslice: 'TS' };
    const dirLabel = dirLabels[ctx.direction] || '';

    if (ctx.direction === 'timeslice') {
        // TimeSlice: X=Crossline, Y=Inline, fixed time/depth
        ctx.line_label = `TS ${ctx.line_index}`;
        ctx.coords = {
            x_min: typeof volInfo !== 'undefined' ? volInfo.xlMin : 0,
            x_max: typeof volInfo !== 'undefined' ? volInfo.xlMax : 0,
            x_label: 'XL',
            y_min: typeof volInfo !== 'undefined' ? volInfo.ilMin : 0,
            y_max: typeof volInfo !== 'undefined' ? volInfo.ilMax : 0,
            y_label: 'IL',
        };
        // Time of the current slice
        if (typeof volInfo !== 'undefined' && volInfo.dtUs && volInfo.tsCount) {
            const totalTime = volInfo.tsCount * volInfo.dtUs / 1000;
            const frac = ctx.line_index / Math.max(1, volInfo.tsCount - 1);
            ctx.time_at_slice = Math.round(frac * totalTime);
        }
    } else {
        // Inline / Crossline: Y=Time/Depth
        ctx.line_label = dirLabel + ' ' + ctx.line_index;
        ctx.coords = {
            x_min: typeof COORD !== 'undefined' ? Math.round(COORD.crossMin) : 0,
            x_max: typeof COORD !== 'undefined' ? Math.round(COORD.crossMax) : 0,
            x_label: ctx.direction === 'inline' ? 'XL' : 'IL',
            y_min: 0,
            y_max: typeof COORD !== 'undefined' ? Math.round(COORD.yRange) : 0,
            y_label: ctx.y_unit,
        };
    }

    // Pick counts
    const allPicks = typeof picksBySlice !== 'undefined' ? picksBySlice : new Map();
    let nInclude = 0, nExclude = 0;
    for (const pts of allPicks.values()) {
        for (const p of pts) {
            if (p.label === 1) nInclude++;
            else if (p.label === 0) nExclude++;
        }
    }
    ctx.picks = { include: nInclude, exclude: nExclude };

    // SAM3 result
    if (typeof logitsMap !== 'undefined' && logitsMap) {
        const totalPx = (typeof logitsWidth !== 'undefined' ? logitsWidth : 1) *
                        (typeof logitsHeight !== 'undefined' ? logitsHeight : 1);
        let positivePx = 0;
        for (let i = 0; i < logitsMap.length; i++) {
            if (logitsMap[i] > 0.3) positivePx++;
        }
        // Last SAM score from the global, if any
        let samScore = 0;
        if (typeof window._lastSamScore !== 'undefined') samScore = window._lastSamScore;
        ctx.sam_mask = {
            score: samScore,
            area_pct: totalPx > 0 ? Math.round(positivePx / totalPx * 1000) / 10 : 0,
        };
    }

    return ctx;
}

async function analyzeSlice() {
    if (chatStreaming) return;

    const imageBase64 = captureCanvasComposite();
    if (!imageBase64) {
        if (chatMessagesEl) {
            appendMessage('assistant', '❌ Cannot capture the canvas. Load data first.');
        }
        return;
    }

    const context = buildSliceContext();

    // Make sure the sidebar is open
    if (!chatSidebarVisible) toggleChatSidebar();

    // Add a context message
    const dirNames = { inline: 'Inline section', crossline: 'Crossline section', timeslice: 'Time slice' };
    const contextSummary = [
        `**AI slice reading — ${dirNames[context.direction] || context.direction}**`,
        `Volume: ${context.volume_name}`,
        `${context.line_label}  |  X: ${context.coords.x_min}~${context.coords.x_max} (${context.coords.x_label})  |  Y: ${context.coords.y_min}~${context.coords.y_max} (${context.coords.y_label})`,
    ];
    if (context.time_at_slice !== undefined) {
        contextSummary[contextSummary.length - 1] += `  |  Slice time: ~${context.time_at_slice}ms`;
    }
    contextSummary.push(`Picks: Include ${context.picks.include} / Exclude ${context.picks.exclude}`);
    if (context.sam_mask && context.sam_mask.score > 0) {
        contextSummary.push(`SAM3 mask: score ${context.sam_mask.score.toFixed(4)}, area ${context.sam_mask.area_pct}%`);
    }
    appendMessage('assistant', contextSummary.join('\n'));
    chatMessages.push({ role: 'assistant', content: contextSummary.join('\n') });

    setChatLoading(true);
    chatStreaming = true;

    const msgEl = appendMessage('assistant', '');
    let fullContent = '';

    chatAbortController = new AbortController();
    try {
        const resp = await fetch('/api/llm/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_base64: imageBase64, context: context }),
            signal: chatAbortController.signal,
        });

        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error('HTTP ' + resp.status + ': ' + errText);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const payload = line.slice(6).trim();
                    if (payload === '[DONE]') continue;
                    try {
                        const parsed = JSON.parse(payload);
                        if (parsed.token) {
                            fullContent += parsed.token;
                            msgEl.textContent = fullContent;
                            scrollChatToBottom();
                        } else if (parsed.error) {
                            fullContent = parsed.error;
                            msgEl.textContent = '❌ ' + fullContent;
                        }
                    } catch (e) {}
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            msgEl.textContent = '❌ Analysis failed: ' + err.message;
            fullContent = msgEl.textContent;
        }
    } finally {
        setChatLoading(false);
        chatStreaming = false;
        chatAbortController = null;
        if (fullContent && !fullContent.startsWith('❌')) {
            chatMessages.push({ role: 'assistant', content: fullContent });
        } else if (!fullContent) {
            msgEl.textContent = '(No response. The model may not accept images; use a multimodal model such as Claude or GPT-4o.)';
        }
    }
}

// ── Settings modal ──────────────────────────────────────────────

async function showLLMConfigModal() {
    const modal = document.getElementById('llmConfigModal');
    const providerSel = document.getElementById('llmProviderSelect');
    const apiKeyInput = document.getElementById('llmApiKey');
    const modelInput = document.getElementById('llmModel');
    const localUrlInput = document.getElementById('llmLocalUrl');
    const systemPromptTa = document.getElementById('llmSystemPrompt');
    const localUrlRow = document.getElementById('providerLocalUrlRow');
    const statusEl = document.getElementById('llmConnectionStatus');

    // Fetch the current settings
    try {
        const resp = await fetch('/api/llm/config');
        if (resp.ok) llmConfigCache = await resp.json();
    } catch (e) {
        console.warn('Failed to load LLM config:', e);
    }

    // Fill the form
    if (llmConfigCache) {
        providerSel.value = llmConfigCache.provider || 'local';
        modelInput.value = llmConfigCache.model || '';
        localUrlInput.value = llmConfigCache.local_url || 'http://localhost:11434/v1';
        systemPromptTa.value = llmConfigCache.system_prompt || '';
        apiKeyInput.value = '';  // left empty (the masked value cannot be reused)
    }

    // React to provider changes
    function updateProviderUI() {
        const prov = providerSel.value;
        localUrlRow.style.display = (prov === 'local') ? 'flex' : 'none';
        if (llmConfigCache && llmConfigCache.provider !== prov) {
            // Use the default model when the provider changes
            const defaults = {
                'anthropic': 'claude-sonnet-4-20250514',
                'openai': 'gpt-4o',
                'local': 'qwen2.5:7b',
            };
            modelInput.value = defaults[prov] || '';
        }
        statusEl.style.display = 'none';
    }
    providerSel.onchange = updateProviderUI;
    updateProviderUI();

    statusEl.style.display = 'none';
    modal.style.display = 'flex';

    // Close button
    document.getElementById('llmConfigClose').onclick = function() {
        modal.style.display = 'none';
    };

    // Cancel
    document.getElementById('llmConfigCancel').onclick = function() {
        modal.style.display = 'none';
    };

    // Test connection
    document.getElementById('llmConfigTest').onclick = async function() {
        statusEl.style.display = 'block';
        statusEl.className = 'connection-status testing';
        statusEl.textContent = '⏳ Testing connection...';

        try {
            const testResp = await fetch('/api/llm/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: [{ role: 'user', content: 'Hello, please reply with the word "connected".' }],
                }),
            });
            if (!testResp.ok) {
                const errText = await testResp.text();
                throw new Error('HTTP ' + testResp.status + ': ' + errText);
            }
            // Read the whole streamed response
            const reader = testResp.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (line.startsWith('data: ') && !line.includes('[DONE]')) {
                        try {
                            const p = JSON.parse(line.slice(6));
                            if (p.token) fullText += p.token;
                            if (p.error) throw new Error(p.error);
                        } catch (e) {
                            if (e.message && !e.message.startsWith('Unexpected')) throw e;
                        }
                    }
                }
            }
            statusEl.className = 'connection-status success';
            statusEl.textContent = '✅ Connected. Model reply: ' + (fullText.slice(0, 100) || '(empty)');
        } catch (e) {
            statusEl.className = 'connection-status error';
            statusEl.textContent = '❌ Connection failed: ' + e.message;
        }
    };

    // Save
    document.getElementById('llmConfigSave').onclick = async function() {
        const config = {
            provider: providerSel.value,
            api_key: apiKeyInput.value,
            model: modelInput.value,
            local_url: localUrlInput.value,
            system_prompt: systemPromptTa.value,
        };
        try {
            const resp = await fetch('/api/llm/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Save failed');
            }
            llmConfigCache = await resp.json();
            modal.style.display = 'none';
        } catch (e) {
            alert('Saving settings failed: ' + e.message);
        }
    };

    // Click on the overlay closes the modal
    modal.onclick = function(e) {
        if (e.target === modal) modal.style.display = 'none';
    };
}

// ── Init ─────────────────────────────────────────────────

function initLLMChat() {
    createChatSidebar();

    // Add the toggle buttons (into the More menu if present, else the toolbar)
    const toolbar = document.querySelector('.toolbar');
    if (!toolbar) { setTimeout(initLLMChat, 200); return; }

    const separator = document.createElement('span');
    separator.style.color = 'var(--ui-border)';
    separator.textContent = '|';

    const btn = document.createElement('button');
    btn.className = 'action-btn';
    btn.id = 'btnAIChat';
    btn.textContent = 'AI assistant';
    btn.style.fontWeight = 'bold';
    btn.style.color = '#000080';
    btn.onclick = toggleChatSidebar;

    const analyzeBtn = document.createElement('button');
    analyzeBtn.className = 'action-btn';
    analyzeBtn.id = 'btnAIAnalyze';
    analyzeBtn.textContent = 'AI analyse';
    analyzeBtn.style.fontWeight = 'bold';
    analyzeBtn.style.color = '#880088';
    analyzeBtn.title = 'AI reading of the current slice (picks + SAM3 mask + geology)';
    analyzeBtn.onclick = analyzeSlice;

    // Into the More menu when the page has one (scope S8), else before the status indicator
    const aiRow = document.getElementById('moreAIRow');
    const statusSpan = document.getElementById('statusIndicator');
    if (aiRow) {
        aiRow.appendChild(btn);
        aiRow.appendChild(analyzeBtn);
    } else if (statusSpan && statusSpan.parentNode === toolbar) {
        toolbar.insertBefore(separator, statusSpan);
        toolbar.insertBefore(btn, separator);
        const sep2 = document.createElement('span');
        sep2.style.color = 'var(--ui-border)';
        sep2.textContent = '|';
        toolbar.insertBefore(sep2, separator);
        toolbar.insertBefore(analyzeBtn, sep2);
    } else {
        toolbar.appendChild(separator);
        toolbar.appendChild(btn);
        toolbar.appendChild(analyzeBtn);
    }
}

// ── Init on page load ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initLLMChat, 300);  // delay so the toolbar is rendered
});
