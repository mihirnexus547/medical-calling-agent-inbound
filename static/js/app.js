/**
 * MediFlow AI - Web Application JavaScript
 * Connects frontend directly with FastAPI endpoints & LangGraph Multi-Agent Orchestrator
 */

// Application State
const state = {
  activeView: 'chat',
  threadId: localStorage.getItem('mediflow_thread_id') || `web_${Date.now()}_${Math.random().toString(36).substring(7)}`,
  token: localStorage.getItem('mediflow_auth_token') || null,
  user: JSON.parse(localStorage.getItem('mediflow_user') || 'null'),
  conversations: [],
  doctors: [],
  selectedDoctorId: null,
  selectedDate: getFormattedDate(0),
  isLoading: false,
};

// Save session thread
localStorage.setItem('mediflow_thread_id', state.threadId);

// DOM Elements
const elements = {
  navTabs: document.querySelectorAll('.nav-item button'),
  views: document.querySelectorAll('.view-section'),
  chatMessages: document.getElementById('chatMessages'),
  chatInput: document.getElementById('chatInput'),
  chatSendBtn: document.getElementById('chatSendBtn'),
  chatResetBtn: document.getElementById('chatResetBtn'),
  threadIdDisplay: document.getElementById('threadIdDisplay'),
  promptChips: document.querySelectorAll('.prompt-chip'),
  profileCards: document.querySelectorAll('.profile-card'),
  doctorsGrid: document.getElementById('doctorsGrid'),
  deptFilters: document.getElementById('deptFilters'),
  doctorSelect: document.getElementById('doctorSelect'),
  dateInput: document.getElementById('dateInput'),
  quickDateBtns: document.querySelectorAll('.quick-date-btn'),
  morningSlots: document.getElementById('morningSlots'),
  afternoonSlots: document.getElementById('afternoonSlots'),
  slotSummaryText: document.getElementById('slotSummaryText'),
  statPatients: document.getElementById('statPatients'),
  statBookings: document.getElementById('statBookings'),
  statSlots: document.getElementById('statSlots'),
  statInvoices: document.getElementById('statInvoices'),
  apptsTableBody: document.getElementById('apptsTableBody'),
  refreshAdminBtn: document.getElementById('refreshAdminBtn'),
  toast: document.getElementById('toast'),

  // Auth & Conversations Sidebar Elements
  openAuthModalBtn: document.getElementById('openAuthModalBtn'),
  closeAuthModalBtn: document.getElementById('closeAuthModalBtn'),
  authModal: document.getElementById('authModal'),
  tabLoginBtn: document.getElementById('tabLoginBtn'),
  tabRegisterBtn: document.getElementById('tabRegisterBtn'),
  loginForm: document.getElementById('loginForm'),
  registerForm: document.getElementById('registerForm'),
  loginError: document.getElementById('loginError'),
  registerError: document.getElementById('registerError'),
  userProfileBadge: document.getElementById('userProfileBadge'),
  navUserName: document.getElementById('navUserName'),
  logoutBtn: document.getElementById('logoutBtn'),
  conversationsList: document.getElementById('conversationsList'),
  newChatSidebarBtn: document.getElementById('newChatSidebarBtn'),
  convAuthStatus: document.getElementById('convAuthStatus'),
  convAuthText: document.getElementById('convAuthText'),
  convLoginPromptBtn: document.getElementById('convLoginPromptBtn'),
};

// ==============================================================================
// INITIALIZATION
// ==============================================================================
document.addEventListener('DOMContentLoaded', async () => {
  initNavigation();
  initAuth();
  initChat();
  initDoctors();
  initSlots();
  loadStats();
  loadAppointments();

  // Validate existing login token
  if (state.token) {
    await verifyCurrentUser();
  } else {
    updateAuthUI();
  }

  // Load user's conversations or load current thread messages
  await loadConversations();
  await loadConversationMessages(state.threadId);

  if (elements.threadIdDisplay) {
    elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
  }
});

// Helper: Format Date as YYYY-MM-DD
function getFormattedDate(daysOffset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + daysOffset);
  return d.toISOString().split('T')[0];
}

// Helper: Show Toast
function showToast(message, duration = 3000) {
  if (!elements.toast) return;
  elements.toast.textContent = message;
  elements.toast.style.display = 'block';
  setTimeout(() => {
    elements.toast.style.display = 'none';
  }, duration);
}

// ==============================================================================
// AUTHENTICATION & USER PROFILE
// ==============================================================================
function initAuth() {
  // Modal Open/Close
  if (elements.openAuthModalBtn) {
    elements.openAuthModalBtn.addEventListener('click', () => openAuthModal('login'));
  }
  if (elements.convLoginPromptBtn) {
    elements.convLoginPromptBtn.addEventListener('click', () => openAuthModal('login'));
  }
  if (elements.closeAuthModalBtn) {
    elements.closeAuthModalBtn.addEventListener('click', closeAuthModal);
  }
  if (elements.authModal) {
    elements.authModal.addEventListener('click', (e) => {
      if (e.target === elements.authModal) closeAuthModal();
    });
  }

  // Tabs
  if (elements.tabLoginBtn && elements.tabRegisterBtn) {
    elements.tabLoginBtn.addEventListener('click', () => switchAuthTab('login'));
    elements.tabRegisterBtn.addEventListener('click', () => switchAuthTab('register'));
  }

  // Login Submit
  if (elements.loginForm) {
    elements.loginForm.addEventListener('submit', handleLogin);
  }

  // Register Submit
  if (elements.registerForm) {
    elements.registerForm.addEventListener('submit', handleRegister);
  }

  // Logout
  if (elements.logoutBtn) {
    elements.logoutBtn.addEventListener('click', handleLogout);
  }
}

function openAuthModal(tab = 'login') {
  if (!elements.authModal) return;
  switchAuthTab(tab);
  elements.loginError.style.display = 'none';
  elements.registerError.style.display = 'none';
  elements.authModal.style.display = 'flex';
}

function closeAuthModal() {
  if (!elements.authModal) return;
  elements.authModal.style.display = 'none';
}

function switchAuthTab(tab) {
  if (tab === 'login') {
    elements.tabLoginBtn.classList.add('active');
    elements.tabRegisterBtn.classList.remove('active');
    elements.loginForm.style.display = 'flex';
    elements.registerForm.style.display = 'none';
  } else {
    elements.tabRegisterBtn.classList.add('active');
    elements.tabLoginBtn.classList.remove('active');
    elements.registerForm.style.display = 'flex';
    elements.loginForm.style.display = 'none';
  }
}

async function handleLogin(e) {
  e.preventDefault();
  elements.loginError.style.display = 'none';
  const email = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value.trim();

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to sign in');
    }

    // Save token & patient info
    state.token = data.token;
    state.user = data.patient;
    localStorage.setItem('mediflow_auth_token', state.token);
    localStorage.setItem('mediflow_user', JSON.stringify(state.user));

    if (data.default_thread_id) {
      state.threadId = data.default_thread_id;
      localStorage.setItem('mediflow_thread_id', state.threadId);
      if (elements.threadIdDisplay) {
        elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
      }
    }

    closeAuthModal();
    updateAuthUI();
    showToast(`Welcome back, ${state.user.name}!`);
    await loadConversations();
    await loadConversationMessages(state.threadId);
  } catch (err) {
    elements.loginError.textContent = err.message;
    elements.loginError.style.display = 'block';
  }
}

async function handleRegister(e) {
  e.preventDefault();
  elements.registerError.style.display = 'none';
  const name = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const phone = document.getElementById('regPhone').value.trim();
  const password = document.getElementById('regPassword').value.trim();

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, phone, password }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Registration failed');
    }

    state.token = data.token;
    state.user = data.patient;
    localStorage.setItem('mediflow_auth_token', state.token);
    localStorage.setItem('mediflow_user', JSON.stringify(state.user));

    if (data.default_thread_id) {
      state.threadId = data.default_thread_id;
      localStorage.setItem('mediflow_thread_id', state.threadId);
      if (elements.threadIdDisplay) {
        elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
      }
    }

    closeAuthModal();
    updateAuthUI();
    showToast(`Account created! Welcome, ${state.user.name}.`);
    await loadConversations();
    await loadConversationMessages(state.threadId);
  } catch (err) {
    elements.registerError.textContent = err.message;
    elements.registerError.style.display = 'block';
  }
}

function handleLogout() {
  state.token = null;
  state.user = null;
  state.conversations = [];
  localStorage.removeItem('mediflow_auth_token');
  localStorage.removeItem('mediflow_user');

  // Switch to guest thread
  state.threadId = `web_${Date.now()}_${Math.random().toString(36).substring(7)}`;
  localStorage.setItem('mediflow_thread_id', state.threadId);
  if (elements.threadIdDisplay) {
    elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
  }

  updateAuthUI();
  renderConversationsList();
  resetChatMessagesView();
  showToast('You have been logged out.');
}

async function verifyCurrentUser() {
  if (!state.token) return;
  try {
    const res = await fetch('/api/auth/me', {
      headers: { 'Authorization': `Bearer ${state.token}` },
    });
    if (res.ok) {
      const data = await res.json();
      state.user = data.patient;
      localStorage.setItem('mediflow_user', JSON.stringify(state.user));
    } else {
      // Token expired or invalid
      state.token = null;
      state.user = null;
      localStorage.removeItem('mediflow_auth_token');
      localStorage.removeItem('mediflow_user');
    }
  } catch (err) {
    console.warn('Auth verification failed, using cached session:', err);
  } finally {
    updateAuthUI();
  }
}

function updateAuthUI() {
  if (state.user && state.token) {
    if (elements.openAuthModalBtn) elements.openAuthModalBtn.style.display = 'none';
    if (elements.userProfileBadge) elements.userProfileBadge.style.display = 'flex';
    if (elements.navUserName) elements.navUserName.textContent = state.user.name;

    if (elements.convAuthStatus) {
      elements.convAuthText.textContent = `👤 ${state.user.name}`;
      elements.convLoginPromptBtn.style.display = 'none';
    }
  } else {
    if (elements.openAuthModalBtn) elements.openAuthModalBtn.style.display = 'inline-flex';
    if (elements.userProfileBadge) elements.userProfileBadge.style.display = 'none';

    if (elements.convAuthStatus) {
      elements.convAuthText.textContent = '🔒 Guest Session (Not Saved)';
      elements.convLoginPromptBtn.style.display = 'inline-block';
    }
  }
}

// ==============================================================================
// CONVERSATIONS SIDEBAR & POSTGRESSAVER CHECKPOINTS
// ==============================================================================
async function loadConversations() {
  if (!state.token) {
    state.conversations = [];
    renderConversationsList();
    return;
  }

  try {
    const res = await fetch('/api/conversations', {
      headers: { 'Authorization': `Bearer ${state.token}` },
    });
    if (res.ok) {
      state.conversations = await res.json();
      renderConversationsList();
    }
  } catch (err) {
    console.error('Error loading conversations:', err);
  }
}

function renderConversationsList() {
  if (!elements.conversationsList) return;
  elements.conversationsList.innerHTML = '';

  if (!state.token) {
    elements.conversationsList.innerHTML = `
      <div class="conv-empty-state">
        <p>Log in or sign up to save consultations and access them from any device.</p>
      </div>
    `;
    return;
  }

  if (state.conversations.length === 0) {
    elements.conversationsList.innerHTML = `
      <div class="conv-empty-state">
        <p>No previous consultations found.<br>Click <strong>+ New Chat</strong> to begin!</p>
      </div>
    `;
    return;
  }

  state.conversations.forEach(conv => {
    const item = document.createElement('div');
    const isActive = conv.thread_id === state.threadId;
    item.className = `conv-item ${isActive ? 'active' : ''}`;

    item.innerHTML = `
      <div class="conv-item-info">
        <span class="conv-item-title" title="${escapeHtml(conv.title)}">${escapeHtml(conv.title)}</span>
        <span class="conv-item-date">${conv.updated_at || 'Recent'}</span>
      </div>
      <button class="conv-item-del" title="Delete conversation">&times;</button>
    `;

    // Click on conversation to switch
    item.querySelector('.conv-item-info').addEventListener('click', () => {
      selectConversation(conv.thread_id);
    });

    // Delete conversation
    item.querySelector('.conv-item-del').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteConversation(conv.thread_id);
    });

    elements.conversationsList.appendChild(item);
  });
}

async function selectConversation(threadId) {
  if (state.threadId === threadId) return;
  state.threadId = threadId;
  localStorage.setItem('mediflow_thread_id', state.threadId);
  if (elements.threadIdDisplay) {
    elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
  }
  renderConversationsList();
  await loadConversationMessages(threadId);
}

async function createNewChat() {
  if (state.token) {
    try {
      const res = await fetch('/api/conversations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${state.token}`,
        },
        body: JSON.stringify({ title: 'New Consultation' }),
      });
      if (res.ok) {
        const newConv = await res.json();
        state.threadId = newConv.thread_id;
        localStorage.setItem('mediflow_thread_id', state.threadId);
        if (elements.threadIdDisplay) {
          elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
        }
        await loadConversations();
        resetChatMessagesView();
        showToast('Started new consultation thread.');
        return;
      }
    } catch (err) {
      console.error('Error creating conversation:', err);
    }
  }

  // Fallback for guest mode
  state.threadId = `web_${Date.now()}_${Math.random().toString(36).substring(7)}`;
  localStorage.setItem('mediflow_thread_id', state.threadId);
  if (elements.threadIdDisplay) {
    elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
  }
  resetChatMessagesView();
  showToast('Started new consultation session.');
}

async function deleteConversation(threadId) {
  if (!confirm('Are you sure you want to delete this consultation?')) return;
  try {
    const res = await fetch(`/api/conversations/${encodeURIComponent(threadId)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${state.token}` },
    });
    if (res.ok) {
      state.conversations = state.conversations.filter(c => c.thread_id !== threadId);
      if (state.threadId === threadId) {
        if (state.conversations.length > 0) {
          selectConversation(state.conversations[0].thread_id);
        } else {
          await createNewChat();
        }
      } else {
        renderConversationsList();
      }
      showToast('Consultation removed.');
    }
  } catch (err) {
    console.error('Error deleting conversation:', err);
  }
}

async function loadConversationMessages(threadId) {
  elements.chatMessages.innerHTML = `
    <div style="text-align: center; padding: 40px; color: var(--text-dim); font-size: 13px;">
      <div class="typing-indicator" style="justify-content: center; margin-bottom: 8px;">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
      Synchronizing clinical checkpoint from PostgreSQL...
    </div>
  `;

  try {
    const res = await fetch(`/api/conversations/${encodeURIComponent(threadId)}/messages`);
    const data = await res.json();
    elements.chatMessages.innerHTML = '';

    if (!data.messages || data.messages.length === 0) {
      resetChatMessagesView();
    } else {
      for (const msg of data.messages) {
        appendMessage(msg.role, msg.content);
      }
    }
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
  } catch (err) {
    console.error('Error loading checkpoint messages:', err);
    resetChatMessagesView();
  }
}

function resetChatMessagesView() {
  const greeting = state.user 
    ? `Hello <strong>${escapeHtml(state.user.name)}</strong>! Welcome back to MediFlow AI clinic.`
    : `Hello! I am your <strong>MediFlow AI Receptionist</strong>. 👋`;

  const instruction = state.user
    ? `How can I assist you with your health consultations, doctor bookings, or invoices today?`
    : `I can help you check doctor availability, schedule appointments, review your insurance copay, or send you a secure online payment link.<br><em>Please share your phone number to get started!</em>`;

  elements.chatMessages.innerHTML = `
    <div class="msg-row bot">
      <div class="msg-avatar">🩺</div>
      <div class="msg-bubble">
        <p>${greeting}</p>
        <p>${instruction}</p>
      </div>
    </div>
  `;
}

// ==============================================================================
// NAVIGATION LOGIC
// ==============================================================================
function initNavigation() {
  elements.navTabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetView = btn.dataset.view;
      switchView(targetView);
    });
  });
}

function switchView(viewName) {
  state.activeView = viewName;
  elements.navTabs.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });
  elements.views.forEach(view => {
    view.classList.toggle('active', view.id === `view-${viewName}`);
  });

  if (viewName === 'calendar' && (!state.selectedDoctorId || state.doctors.length === 0)) {
    loadDoctorSlots();
  } else if (viewName === 'admin') {
    loadStats();
    loadAppointments();
  }
}

// ==============================================================================
// CHAT FUNCTIONALITY & STREAMING
// ==============================================================================
function initChat() {
  elements.chatSendBtn.addEventListener('click', handleSendMessage);
  elements.chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  if (elements.chatResetBtn) {
    elements.chatResetBtn.addEventListener('click', createNewChat);
  }
  if (elements.newChatSidebarBtn) {
    elements.newChatSidebarBtn.addEventListener('click', createNewChat);
  }

  // Quick Prompt Chips
  elements.promptChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      if (prompt) {
        elements.chatInput.value = prompt;
        handleSendMessage();
      }
    });
  });

  // Quick Test Profile Cards
  elements.profileCards.forEach(card => {
    card.addEventListener('click', () => {
      const phone = card.dataset.phone;
      if (phone) {
        elements.chatInput.value = `Hi, my phone is ${phone}`;
        handleSendMessage();
      }
    });
  });
}

async function handleSendMessage() {
  const text = elements.chatInput.value.trim();
  if (!text || state.isLoading) return;

  // Append User Bubble
  appendMessage('user', text);
  elements.chatInput.value = '';
  state.isLoading = true;
  elements.chatSendBtn.disabled = true;

  // Create Bot Message Row with live typing placeholder
  const botRow = document.createElement('div');
  botRow.className = 'msg-row bot';
  const botAvatar = document.createElement('div');
  botAvatar.className = 'msg-avatar';
  botAvatar.textContent = '🩺';
  const botBubble = document.createElement('div');
  botBubble.className = 'msg-bubble';
  botBubble.innerHTML = `
    <div class="typing-indicator" style="padding: 4px 0;">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>
  `;
  botRow.appendChild(botAvatar);
  botRow.appendChild(botBubble);
  elements.chatMessages.appendChild(botRow);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (state.token) {
      headers['Authorization'] = `Bearer ${state.token}`;
    }

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        message: text,
        thread_id: state.threadId,
        token: state.token,
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Server status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedText = '';
    let hasReceivedToken = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop(); // save remainder

      for (const evt of events) {
        const trimmed = evt.trim();
        if (!trimmed.startsWith('data: ')) continue;
        const jsonStr = trimmed.slice(6);
        try {
          const payload = JSON.parse(jsonStr);

          if (payload.token) {
            if (!hasReceivedToken) {
              hasReceivedToken = true;
              botBubble.innerHTML = '';
            }
            accumulatedText += payload.token;
            botBubble.innerHTML = parseMarkdownPartial(accumulatedText);
            elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
          }

          if (payload.done) {
            const finalMsg = payload.full_text || accumulatedText;
            botBubble.innerHTML = parseMarkdownPartial(finalMsg);
            if (state.token) {
              loadConversations();
            }
          }

          if (payload.error) {
            botBubble.innerHTML = `<span style="color: #fb7185;">⚠️ ${escapeHtml(payload.error)}</span>`;
          }
        } catch (e) {
          console.error('Error parsing SSE event:', e);
        }
      }
    }
  } catch (err) {
    botBubble.innerHTML = `<span style="color: #fb7185;">⚠️ Error connecting to clinic agent: ${escapeHtml(err.message)}</span>`;
  } finally {
    state.isLoading = false;
    elements.chatSendBtn.disabled = false;
    elements.chatInput.focus();
    loadStats();
    loadAppointments();
  }
}

function appendMessage(role, content) {
  const row = document.createElement('div');
  row.className = `msg-row ${role === 'user' ? 'user' : 'bot'}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🩺';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  if (role === 'user') {
    bubble.textContent = content;
  } else {
    bubble.innerHTML = parseMarkdownPartial(content);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  elements.chatMessages.appendChild(row);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function parseMarkdownPartial(md) {
  if (!md) return '';

  // 1. First sanitize complete or partial Stripe Checkout URLs
  let html = md.replace(/(https:\/\/checkout\.stripe\.com\/[^\s\)\*]+)/g, (fullMatch) => {
    const cleanUrl = fullMatch.replace(/[\*\_]+$/, '');
    return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="stripe-pay-btn">💳 Pay Online Now via Stripe Checkout &rarr;</a>`;
  });

  // 2. Bold **text**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // 3. Bullet points
  html = html.replace(/^\s*[-•]\s+(.*)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

  // 4. Line breaks
  html = html.replace(/\n{2,}/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');

  return `<p>${html}</p>`;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ==============================================================================
// DOCTOR DIRECTORY LOGIC
// ==============================================================================
async function initDoctors() {
  try {
    const res = await fetch('/api/doctors');
    if (!res.ok) throw new Error('Failed to load doctors');
    state.doctors = await res.json();

    renderDoctorsGrid(state.doctors);
    populateDeptFilters(state.doctors);
    populateDoctorSelect(state.doctors);
  } catch (err) {
    console.error('Error fetching doctors:', err);
    if (elements.doctorsGrid) {
      elements.doctorsGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #fb7185;">Error loading doctors directory.</div>`;
    }
  }
}

function renderDoctorsGrid(doctors) {
  if (!elements.doctorsGrid) return;
  elements.doctorsGrid.innerHTML = '';

  const departmentIcons = {
    'General Medicine': '🩺',
    'Cardiology': '❤️',
    'Orthopedics': '🦴',
    'Dermatology': '✨',
    'Pediatrics': '👶',
    'Neurology': '🧠',
    'Ophthalmology': '👁️',
    'ENT': '👂',
    'Psychiatry': '💭',
    'Oncology': '🎗️',
    'Dental Care': '🦷',
    'Gynecology': '🌸',
    'Endocrinology': '🔬',
    'Gastroenterology': '🥣',
    'Urology': '💧',
  };

  doctors.forEach(doc => {
    const card = document.createElement('div');
    card.className = 'doctor-card';
    const icon = departmentIcons[doc.specialization] || '👨‍⚕️';

    card.innerHTML = `
      <div class="doctor-card-top">
        <div class="doctor-avatar-box">${icon}</div>
        <div class="doctor-spec-pill">${doc.specialization}</div>
      </div>
      <div class="doctor-name">${doc.name}</div>
      <div class="doctor-meta">
        <span>⭐ 4.9 Rated</span>
        <span>⏱️ 30-min Consult</span>
      </div>
      <div class="doctor-actions">
        <button class="btn-primary" style="flex: 1;" onclick="bookDoctorViaChat('${escapeHtml(doc.name)}')">
          Book Appointment
        </button>
        <button class="btn-secondary" onclick="viewDoctorInCalendar(${doc.id})">
          📅 Slots
        </button>
      </div>
    `;
    elements.doctorsGrid.appendChild(card);
  });
}

function populateDeptFilters(doctors) {
  if (!elements.deptFilters) return;
  const depts = Array.from(new Set(doctors.map(d => d.specialization))).sort();

  depts.forEach(dept => {
    const btn = document.createElement('button');
    btn.className = 'filter-chip';
    btn.dataset.dept = dept;
    btn.textContent = dept;
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const filtered = doctors.filter(d => d.specialization === dept);
      renderDoctorsGrid(filtered);
    });
    elements.deptFilters.appendChild(btn);
  });

  const allBtn = elements.deptFilters.querySelector('[data-dept="all"]');
  if (allBtn) {
    allBtn.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      allBtn.classList.add('active');
      renderDoctorsGrid(doctors);
    });
  }
}

function populateDoctorSelect(doctors) {
  if (!elements.doctorSelect) return;
  elements.doctorSelect.innerHTML = '';
  doctors.forEach(doc => {
    const opt = document.createElement('option');
    opt.value = doc.id;
    opt.textContent = `${doc.name} (${doc.specialization})`;
    elements.doctorSelect.appendChild(opt);
  });

  if (doctors.length > 0) {
    state.selectedDoctorId = doctors[0].id;
  }
}

window.bookDoctorViaChat = function(doctorName) {
  switchView('chat');
  elements.chatInput.value = `I want to book an appointment with ${doctorName}`;
  handleSendMessage();
};

window.viewDoctorInCalendar = function(doctorId) {
  state.selectedDoctorId = doctorId;
  if (elements.doctorSelect) elements.doctorSelect.value = doctorId;
  switchView('calendar');
  loadDoctorSlots();
};

// ==============================================================================
// VISUAL CALENDAR & SLOTS EXPLORER
// ==============================================================================
function initSlots() {
  if (elements.dateInput) {
    elements.dateInput.value = state.selectedDate;
    elements.dateInput.addEventListener('change', (e) => {
      state.selectedDate = e.target.value;
      loadDoctorSlots();
    });
  }

  if (elements.doctorSelect) {
    elements.doctorSelect.addEventListener('change', (e) => {
      state.selectedDoctorId = parseInt(e.target.value);
      loadDoctorSlots();
    });
  }

  elements.quickDateBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      elements.quickDateBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const offset = parseInt(btn.dataset.offset || 0);
      state.selectedDate = getFormattedDate(offset);
      if (elements.dateInput) elements.dateInput.value = state.selectedDate;
      loadDoctorSlots();
    });
  });
}

async function loadDoctorSlots() {
  const docId = state.selectedDoctorId;
  const date = state.selectedDate;
  if (!docId || !date) return;

  try {
    elements.morningSlots.innerHTML = `<div style="color: var(--text-dim); font-size: 13px;">Checking availability in database...</div>`;
    elements.afternoonSlots.innerHTML = ``;

    const res = await fetch(`/api/availability?doctor_id=${docId}&date=${date}`);
    if (!res.ok) throw new Error('Failed to load slots');
    const data = await res.json();

    const docName = data.doctor_name || 'Doctor';
    if (elements.slotSummaryText) {
      elements.slotSummaryText.textContent = `Showing available slots for ${docName} on ${date}:`;
    }

    renderSlotButtons(data.slots || []);
  } catch (err) {
    console.error('Error fetching slots:', err);
    elements.morningSlots.innerHTML = `<div style="color: #fb7185;">Error loading slots.</div>`;
    elements.afternoonSlots.innerHTML = ``;
  }
}

function renderSlotButtons(slots) {
  elements.morningSlots.innerHTML = '';
  elements.afternoonSlots.innerHTML = '';

  const morning = slots.filter(s => {
    const hour = parseInt(s.start_time.split(':')[0]);
    return hour < 13;
  });

  const afternoon = slots.filter(s => {
    const hour = parseInt(s.start_time.split(':')[0]);
    return hour >= 13;
  });

  if (morning.length === 0) {
    elements.morningSlots.innerHTML = `<div style="color: var(--text-dim); font-size: 13px;">No morning slots available.</div>`;
  } else {
    morning.forEach(slot => {
      elements.morningSlots.appendChild(createSlotElement(slot));
    });
  }

  if (afternoon.length === 0) {
    elements.afternoonSlots.innerHTML = `<div style="color: var(--text-dim); font-size: 13px;">No afternoon slots available.</div>`;
  } else {
    afternoon.forEach(slot => {
      elements.afternoonSlots.appendChild(createSlotElement(slot));
    });
  }
}

function createSlotElement(slot) {
  const btn = document.createElement('div');
  btn.className = `slot-btn ${slot.is_booked ? 'booked' : ''}`;
  const displayTime = slot.start_time.substring(0, 5);

  btn.innerHTML = `
    <span class="slot-time">${displayTime}</span>
    <span class="slot-status-label">${slot.is_booked ? 'Booked' : 'Available'}</span>
  `;

  if (!slot.is_booked) {
    btn.addEventListener('click', () => {
      const docName = elements.doctorSelect ? elements.doctorSelect.options[elements.doctorSelect.selectedIndex].text.split('(')[0].trim() : 'Doctor';
      switchView('chat');
      elements.chatInput.value = `I want to book an appointment with ${docName} on ${state.selectedDate} at ${displayTime}`;
      handleSendMessage();
    });
  }

  return btn;
}

// ==============================================================================
// ADMIN CENTER & STATS LOGIC
// ==============================================================================
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error('Stats fetch error');
    const data = await res.json();

    if (elements.statPatients) elements.statPatients.textContent = Number(data.total_patients).toLocaleString();
    if (elements.statBookings) elements.statBookings.textContent = Number(data.active_bookings).toLocaleString();
    if (elements.statSlots) elements.statSlots.textContent = Number(data.open_slots).toLocaleString();
    if (elements.statInvoices) elements.statInvoices.textContent = Number(data.paid_invoices).toLocaleString();
  } catch (err) {
    console.error('Stats load error:', err);
  }
}

async function loadAppointments() {
  if (!elements.apptsTableBody) return;
  elements.apptsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim);">Loading recent appointments...</td></tr>`;

  try {
    const res = await fetch('/api/appointments');
    if (!res.ok) throw new Error('Appointments fetch error');
    const appts = await res.json();

    if (appts.length === 0) {
      elements.apptsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim);">No appointments recorded.</td></tr>`;
      return;
    }

    elements.apptsTableBody.innerHTML = appts.map(a => `
      <tr>
        <td><strong>#${a.id}</strong></td>
        <td>${a.patient_name || 'Patient ' + a.patient_id}</td>
        <td>${a.doctor_name} <span style="font-size: 11px; color: var(--text-dim);">(${a.specialization})</span></td>
        <td>${a.appointment_date}</td>
        <td>${a.appointment_time.substring(0, 5)}</td>
        <td><span class="badge-status ${a.status.toLowerCase()}">${a.status}</span></td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Appointments table load error:', err);
    elements.apptsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #fb7185;">Error loading appointment data.</td></tr>`;
  }
}

if (elements.refreshAdminBtn) {
  elements.refreshAdminBtn.addEventListener('click', () => {
    loadStats();
    loadAppointments();
    showToast('Admin data refreshed.');
  });
}
