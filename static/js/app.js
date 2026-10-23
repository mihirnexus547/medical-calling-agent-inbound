/**
 * MediFlow AI - Web Application JavaScript
 * Connects frontend directly with FastAPI endpoints & LangGraph Multi-Agent Orchestrator
 */

// Application State
const state = {
  activeView: 'chat',
  threadId: localStorage.getItem('mediflow_thread_id') || `web_${Date.now()}_${Math.random().toString(36).substring(7)}`,
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
};

// ==============================================================================
// INITIALIZATION
// ==============================================================================
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initChat();
  initDoctors();
  initSlots();
  loadStats();
  loadAppointments();

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
// CHAT FUNCTIONALITY
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
    elements.chatResetBtn.addEventListener('click', () => {
      state.threadId = `web_${Date.now()}_${Math.random().toString(36).substring(7)}`;
      localStorage.setItem('mediflow_thread_id', state.threadId);
      if (elements.threadIdDisplay) {
        elements.threadIdDisplay.textContent = state.threadId.substring(0, 16) + '...';
      }
      elements.chatMessages.innerHTML = `
        <div class="msg-row bot">
          <div class="msg-avatar">🩺</div>
          <div class="msg-bubble">
            <p><strong>Session reset.</strong> Hello! I am your AI Medical Receptionist. How can I assist you today? Please share your phone number to get started.</p>
          </div>
        </div>
      `;
      showToast('AI Chat Session reset successfully.');
    });
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
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        thread_id: state.threadId
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
            botBubble.innerHTML = parseMarkdownAndLinks(finalMsg);
            if (payload.latency) {
              const meta = document.createElement('div');
              meta.className = 'msg-meta';
              meta.style.cssText = 'font-size: 11px; opacity: 0.55; margin-top: 6px; text-align: right;';
              meta.textContent = `⚡ Latency: ${payload.latency}s`;
              botBubble.appendChild(meta);
            }
            elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
          }

          if (payload.error) {
            botBubble.innerHTML = `<p style="color: #f87171;">⚠️ ${payload.error}</p>`;
          }
        } catch (e) {
          console.error("SSE parse error", e, jsonStr);
        }
      }
    }
  } catch (err) {
    botBubble.innerHTML = `<p style="color: #f87171;">⚠️ Connection error: ${err.message}. Please check if server is running.</p>`;
  } finally {
    state.isLoading = false;
    elements.chatSendBtn.disabled = false;
    elements.chatInput.focus();
  }
}

function parseMarkdownPartial(text) {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/\n/g, '<br>');
  return `<p>${html}<span class="typing-cursor">▌</span></p>`;
}


function appendMessage(sender, text) {
  const row = document.createElement('div');
  row.className = `msg-row ${sender}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = sender === 'user' ? '👤' : '🩺';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  // Parse Markdown Formatting & Stripe Payment Links
  const formattedHtml = parseMarkdownAndLinks(text);
  bubble.innerHTML = formattedHtml;

  row.appendChild(avatar);
  row.appendChild(bubble);
  elements.chatMessages.appendChild(row);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

// Convert markdown text to HTML and inject dedicated Stripe Payment CTA if present
function parseMarkdownAndLinks(text) {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Detect Stripe Checkout URL
  const stripeRegex = /(https:\/\/checkout\.stripe\.com\/[^\s\)\"'>]+)/g;
  let paymentUrl = null;
  const match = text.match(stripeRegex);
  if (match) {
    paymentUrl = match[0];
  }

  // Bold & Italic
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Bullet points
  html = html.replace(/^[-\*]\s+(.*)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');

  // Line breaks to paragraphs
  const paragraphs = html.split('\n\n');
  let result = paragraphs.map(p => {
    if (p.startsWith('<ul>') || p.startsWith('<ol>')) return p;
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join('');

  // Append Stripe Visual Payment Card if URL found
  if (paymentUrl) {
    result += `
      <div class="payment-cta-card">
        <div class="payment-cta-header">
          <span>💳 Secure Online Checkout</span>
          <span>Powered by Stripe</span>
        </div>
        <p style="font-size: 13px; color: #e2e8f0; margin: 0;">Click below to complete your consultation payment right now:</p>
        <a href="${paymentUrl}" target="_blank" rel="noopener noreferrer" class="payment-btn">
          🔒 Pay Online Now via Stripe Checkout &rarr;
        </a>
      </div>
    `;
  }

  return result;
}

// ==============================================================================
// DOCTORS DIRECTORY
// ==============================================================================
async function initDoctors() {
  try {
    const res = await fetch('/api/doctors');
    if (!res.ok) throw new Error('Failed to load doctors');
    state.doctors = await res.json();
    renderDepartmentFilters();
    renderDoctorsGrid(state.doctors);
    populateDoctorSelect(state.doctors);
  } catch (err) {
    console.error('Error fetching doctors:', err);
  }
}

function renderDepartmentFilters() {
  if (!elements.deptFilters) return;
  const specializations = ['All', ...new Set(state.doctors.map(d => d.specialization))];
  elements.deptFilters.innerHTML = '';

  specializations.forEach(spec => {
    const btn = document.createElement('button');
    btn.className = `filter-btn ${spec === 'All' ? 'active' : ''}`;
    btn.textContent = spec;
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (spec === 'All') {
        renderDoctorsGrid(state.doctors);
      } else {
        renderDoctorsGrid(state.doctors.filter(d => d.specialization === spec));
      }
    });
    elements.deptFilters.appendChild(btn);
  });
}

function renderDoctorsGrid(doctorsList) {
  if (!elements.doctorsGrid) return;
  elements.doctorsGrid.innerHTML = '';

  if (doctorsList.length === 0) {
    elements.doctorsGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim); padding: 40px;">No doctors found matching criteria.</div>`;
    return;
  }

  doctorsList.forEach(doc => {
    const card = document.createElement('div');
    card.className = 'doctor-card';
    card.innerHTML = `
      <div class="doc-badge">${doc.specialization}</div>
      <div>
        <div class="doc-avatar-large">🩺</div>
        <div class="doc-name">${doc.name}</div>
        <div class="doc-spec">Specialist in ${doc.specialization}</div>
      </div>
      <div>
        <div class="doc-meta">
          <span>Fee: $150.00</span>
          <span>Status: Available</span>
        </div>
        <button class="btn-book-doc" data-id="${doc.id}" data-name="${doc.name}">
          📅 View Slots & Book
        </button>
      </div>
    `;

    card.querySelector('.btn-book-doc').addEventListener('click', () => {
      state.selectedDoctorId = doc.id;
      if (elements.doctorSelect) elements.doctorSelect.value = doc.id;
      switchView('calendar');
      loadDoctorSlots();
    });

    elements.doctorsGrid.appendChild(card);
  });
}

function populateDoctorSelect(doctorsList) {
  if (!elements.doctorSelect) return;
  elements.doctorSelect.innerHTML = doctorsList.map(doc => `
    <option value="${doc.id}">${doc.name} (${doc.specialization})</option>
  `).join('');

  if (doctorsList.length > 0 && !state.selectedDoctorId) {
    state.selectedDoctorId = doctorsList[0].id;
  }
}

// ==============================================================================
// SLOTS & CALENDAR LOGIC
// ==============================================================================
function initSlots() {
  if (elements.dateInput) {
    elements.dateInput.value = state.selectedDate;
    elements.dateInput.min = getFormattedDate(0);
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
      const days = parseInt(btn.dataset.days || 0);
      state.selectedDate = getFormattedDate(days);
      if (elements.dateInput) elements.dateInput.value = state.selectedDate;
      loadDoctorSlots();
    });
  });
}

async function loadDoctorSlots() {
  if (!elements.morningSlots || !elements.afternoonSlots) return;

  const doctorId = state.selectedDoctorId || (elements.doctorSelect ? elements.doctorSelect.value : null);
  const date = state.selectedDate;
  if (!doctorId || !date) return;

  elements.morningSlots.innerHTML = `<div style="color: var(--text-dim);">Loading slots...</div>`;
  elements.afternoonSlots.innerHTML = `<div style="color: var(--text-dim);">Loading slots...</div>`;

  try {
    const res = await fetch(`/api/availability?doctor_id=${doctorId}&date=${date}`);
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
      // Pre-fill chat message and switch to chat view
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
