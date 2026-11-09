/**
 * llm-client.js -- AI 助手聊天侧边栏, SSE 流式对话, 多模型配置
 * 加载顺序: 在 sam-client.js 之后 (最后加载)
 */

// ── 全局状态 ──────────────────────────────────────────────
let chatMessages = [];
let chatStreaming = false;
let chatAbortController = null;
let chatSidebarVisible = false;
let llmConfigCache = null;
let chatSidebarEl = null;
let chatMessagesEl = null;
let chatInputEl = null;
let chatLoadingEl = null;

// ── 侧边栏 DOM 创建 ────────────────────────────────────────

function createChatSidebar() {
    const sidebar = document.createElement('div');
    sidebar.id = 'chatSidebar';

    // 头部
    const header = document.createElement('div');
    header.className = 'chat-header';
    header.innerHTML =
        '<span>💬 AI 助手</span>' +
        '<span class="chat-spacer"></span>' +
        '<span class="chat-config-icon" id="chatConfigBtn" title="设置">⚙️</span>' +
        '<span class="chat-close-icon" id="chatCloseBtn" title="关闭">✕</span>';
    sidebar.appendChild(header);

    // 消息区域
    const messagesDiv = document.createElement('div');
    messagesDiv.className = 'chat-messages';
    messagesDiv.id = 'chatMessages';
    sidebar.appendChild(messagesDiv);
    chatMessagesEl = messagesDiv;

    // 加载动画
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'chat-loading';
    loadingDiv.id = 'chatLoading';
    loadingDiv.innerHTML =
        '<span class="chat-dot"></span>' +
        '<span class="chat-dot"></span>' +
        '<span class="chat-dot"></span>';
    sidebar.appendChild(loadingDiv);
    chatLoadingEl = loadingDiv;

    // 输入区域
    const inputArea = document.createElement('div');
    inputArea.className = 'chat-input-area';
    const textarea = document.createElement('textarea');
    textarea.id = 'chatInput';
    textarea.placeholder = '输入消息 (Enter 发送, Shift+Enter 换行)';
    textarea.rows = 2;
    chatInputEl = textarea;

    const sendBtn = document.createElement('button');
    sendBtn.textContent = '发送';
    sendBtn.id = 'chatSendBtn';

    inputArea.appendChild(textarea);
    inputArea.appendChild(sendBtn);
    sidebar.appendChild(inputArea);

    document.body.appendChild(sidebar);
    chatSidebarEl = sidebar;

    // ── 事件绑定 ──────────────────────────────────────────
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

// ── 消息渲染 ──────────────────────────────────────────────

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

// ── 核心 SSE 流式逻辑 ──────────────────────────────────────

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
                        // 跳过无法解析的 JSON
                    }
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            msgEl.textContent = '❌ 连接失败: ' + err.message;
            fullContent = msgEl.textContent;
        }
    } finally {
        setChatLoading(false);
        chatStreaming = false;
        chatAbortController = null;
        if (fullContent && !fullContent.startsWith('❌')) {
            chatMessages.push({ role: 'assistant', content: fullContent });
        } else if (!fullContent) {
            chatMessages.push({ role: 'assistant', content: '(空响应)' });
            msgEl.textContent = '(空响应)';
        }
    }
}

// ── 侧边栏控制 ────────────────────────────────────────────

function toggleChatSidebar() {
    chatSidebarVisible = !chatSidebarVisible;
    if (chatSidebarVisible) {
        chatSidebarEl.style.display = 'flex';
        // 调整主容器让出空间
        const mainContainer = document.querySelector('.main-container');
        if (mainContainer) mainContainer.style.marginRight = '380px';
        // 调整切片面板
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
    // 触发画布 resize
    window.dispatchEvent(new Event('resize'));
}

function clearChat() {
    chatMessages = [];
    if (chatMessagesEl) chatMessagesEl.innerHTML = '';
}

// ── VLM 切片智能解读 ─────────────────────────────────────

function captureCanvasComposite() {
    const canvas = document.getElementById('seismicCanvas');
    if (!canvas) return null;
    return canvas.toDataURL('image/png').split(',')[1];  // 去掉 data:image/png;base64, 前缀
}

function buildSliceContext() {
    const ctx = {
        direction: typeof curDir !== 'undefined' ? curDir : 'inline',
        line_index: typeof curIndex !== 'undefined' ? curIndex : 0,
        volume_name: (typeof volInfo !== 'undefined' && volInfo.name) ? volInfo.name : '未加载',
        coords: {},
        y_unit: (typeof yAxisUnit !== 'undefined' && yAxisUnit === 'depth') ? 'Depth (m)' : 'Time (ms)',
    };

    // 方向中文名
    const dirLabels = { inline: 'IL', crossline: 'XL', timeslice: 'TS' };
    const dirLabel = dirLabels[ctx.direction] || '';

    if (ctx.direction === 'timeslice') {
        // TimeSlice: X=Crossline, Y=Inline, 固定时间/深度
        ctx.line_label = `TS ${ctx.line_index}`;
        ctx.coords = {
            x_min: typeof volInfo !== 'undefined' ? volInfo.xlMin : 0,
            x_max: typeof volInfo !== 'undefined' ? volInfo.xlMax : 0,
            x_label: 'XL',
            y_min: typeof volInfo !== 'undefined' ? volInfo.ilMin : 0,
            y_max: typeof volInfo !== 'undefined' ? volInfo.ilMax : 0,
            y_label: 'IL',
        };
        // 计算当前时间层位
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

    // 拾取点统计
    const allPicks = typeof picksBySlice !== 'undefined' ? picksBySlice : new Map();
    let nInclude = 0, nExclude = 0;
    for (const pts of allPicks.values()) {
        for (const p of pts) {
            if (p.label === 1) nInclude++;
            else if (p.label === 0) nExclude++;
        }
    }
    ctx.picks = { include: nInclude, exclude: nExclude };

    // SAM3 结果
    if (typeof logitsMap !== 'undefined' && logitsMap) {
        const totalPx = (typeof logitsWidth !== 'undefined' ? logitsWidth : 1) *
                        (typeof logitsHeight !== 'undefined' ? logitsHeight : 1);
        let positivePx = 0;
        for (let i = 0; i < logitsMap.length; i++) {
            if (logitsMap[i] > 0.3) positivePx++;
        }
        // 尝试从全局获取最后一次 SAM score
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
            appendMessage('assistant', '❌ 无法截取画布，请先加载数据。');
        }
        return;
    }

    const context = buildSliceContext();

    // 确保侧边栏打开
    if (!chatSidebarVisible) toggleChatSidebar();

    // 添加系统提示消息
    const dirNames = { inline: 'Inline 剖面', crossline: 'Crossline 剖面', timeslice: 'TimeSlice 水平切片' };
    const contextSummary = [
        `📷 **AI 切片解读 — ${dirNames[context.direction] || context.direction}**`,
        `数据体: ${context.volume_name}`,
        `${context.line_label}  |  X: ${context.coords.x_min}~${context.coords.x_max} (${context.coords.x_label})  |  Y: ${context.coords.y_min}~${context.coords.y_max} (${context.coords.y_label})`,
    ];
    if (context.time_at_slice !== undefined) {
        contextSummary[contextSummary.length - 1] += `  |  时间层位: ~${context.time_at_slice}ms`;
    }
    contextSummary.push(`拾取点: Include ${context.picks.include} 个 / Exclude ${context.picks.exclude} 个`);
    if (context.sam_mask && context.sam_mask.score > 0) {
        contextSummary.push(`SAM3 分割: 置信度 ${context.sam_mask.score.toFixed(4)}, 面积 ${context.sam_mask.area_pct}%`);
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
            msgEl.textContent = '❌ 分析失败: ' + err.message;
            fullContent = msgEl.textContent;
        }
    } finally {
        setChatLoading(false);
        chatStreaming = false;
        chatAbortController = null;
        if (fullContent && !fullContent.startsWith('❌')) {
            chatMessages.push({ role: 'assistant', content: fullContent });
        } else if (!fullContent) {
            msgEl.textContent = '(无响应 — 可能模型不支持视觉输入，请使用 Claude/GPT-4o 等多模态模型)';
        }
    }
}

// ── 配置弹窗 ──────────────────────────────────────────────

async function showLLMConfigModal() {
    const modal = document.getElementById('llmConfigModal');
    const providerSel = document.getElementById('llmProviderSelect');
    const apiKeyInput = document.getElementById('llmApiKey');
    const modelInput = document.getElementById('llmModel');
    const localUrlInput = document.getElementById('llmLocalUrl');
    const systemPromptTa = document.getElementById('llmSystemPrompt');
    const localUrlRow = document.getElementById('providerLocalUrlRow');
    const statusEl = document.getElementById('llmConnectionStatus');

    // 获取当前配置
    try {
        const resp = await fetch('/api/llm/config');
        if (resp.ok) llmConfigCache = await resp.json();
    } catch (e) {
        console.warn('Failed to load LLM config:', e);
    }

    // 填充表单
    if (llmConfigCache) {
        providerSel.value = llmConfigCache.provider || 'local';
        modelInput.value = llmConfigCache.model || '';
        localUrlInput.value = llmConfigCache.local_url || 'http://localhost:11434/v1';
        systemPromptTa.value = llmConfigCache.system_prompt || '';
        apiKeyInput.value = '';  // 不填充（脱敏值不可用）
    }

    // provider 切换联动
    function updateProviderUI() {
        const prov = providerSel.value;
        localUrlRow.style.display = (prov === 'local') ? 'flex' : 'none';
        if (llmConfigCache && llmConfigCache.provider !== prov) {
            // 切换 provider 时使用默认模型
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

    // 关闭按钮
    document.getElementById('llmConfigClose').onclick = function() {
        modal.style.display = 'none';
    };

    // 取消
    document.getElementById('llmConfigCancel').onclick = function() {
        modal.style.display = 'none';
    };

    // 测试连接
    document.getElementById('llmConfigTest').onclick = async function() {
        statusEl.style.display = 'block';
        statusEl.className = 'connection-status testing';
        statusEl.textContent = '⏳ 正在测试连接...';

        try {
            const testResp = await fetch('/api/llm/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: [{ role: 'user', content: '你好，请回复"连接成功"两个字。' }],
                }),
            });
            if (!testResp.ok) {
                const errText = await testResp.text();
                throw new Error('HTTP ' + testResp.status + ': ' + errText);
            }
            // 读取完整流式响应
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
            statusEl.textContent = '✅ 连接成功！模型回复: ' + (fullText.slice(0, 100) || '(空)');
        } catch (e) {
            statusEl.className = 'connection-status error';
            statusEl.textContent = '❌ 连接失败: ' + e.message;
        }
    };

    // 保存
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
                throw new Error(err.detail || '保存失败');
            }
            llmConfigCache = await resp.json();
            modal.style.display = 'none';
        } catch (e) {
            alert('配置保存失败: ' + e.message);
        }
    };

    // 点击遮罩关闭
    modal.onclick = function(e) {
        if (e.target === modal) modal.style.display = 'none';
    };
}

// ── 初始化 ─────────────────────────────────────────────────

function initLLMChat() {
    createChatSidebar();

    // 在工具栏添加切换按钮
    const toolbar = document.querySelector('.toolbar');
    if (!toolbar) { setTimeout(initLLMChat, 200); return; }

    const separator = document.createElement('span');
    separator.style.color = 'var(--ui-border)';
    separator.textContent = '|';

    const btn = document.createElement('button');
    btn.className = 'action-btn';
    btn.id = 'btnAIChat';
    btn.textContent = '💬 AI 助手';
    btn.style.fontWeight = 'bold';
    btn.style.color = '#000080';
    btn.onclick = toggleChatSidebar;

    const analyzeBtn = document.createElement('button');
    analyzeBtn.className = 'action-btn';
    analyzeBtn.id = 'btnAIAnalyze';
    analyzeBtn.textContent = '🔍 AI 分析';
    analyzeBtn.style.fontWeight = 'bold';
    analyzeBtn.style.color = '#880088';
    analyzeBtn.title = 'AI 智能解读当前切片（拾取点+SAM3分割+地质特征）';
    analyzeBtn.onclick = analyzeSlice;

    // 插入到状态指示器之前
    const statusSpan = document.getElementById('statusIndicator');
    if (statusSpan && statusSpan.parentNode) {
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

// ── 页面加载时初始化 ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initLLMChat, 300);  // 延迟确保 toolbar 已渲染
});
