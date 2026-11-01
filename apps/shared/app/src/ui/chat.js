// The chat surface: thread + composer. Renders exactly what the server returned — the answer state, the
// limitation, the citations — and nothing it did not. No HTML is ever parsed from an answer.
import { h, clear } from './dom.js';
import { icon } from './icons.js';

const TONE = {
  ANSWERED_FROM_KNOWLEDGE: 'success', PARTIAL_ANSWER: 'warning', CONFLICTED: 'warning',
  NEEDS_WEB_RESEARCH: 'processing', NEEDS_USER_SOURCE: 'warning', UNKNOWN: 'unknown',
  PROVIDER_UNAVAILABLE: 'danger', PROCESSING: 'processing',
};
const STATE_ICON = {
  ANSWERED_FROM_KNOWLEDGE: 'status-completed', PARTIAL_ANSWER: 'status-warning', CONFLICTED: 'conflict',
  NEEDS_WEB_RESEARCH: 'research', NEEDS_USER_SOURCE: 'gap', UNKNOWN: 'status-unknown',
  PROVIDER_UNAVAILABLE: 'status-failed', PROCESSING: 'status-processing',
};

export function createChatView(ctx) {
  const { t, store, toast, copy } = ctx;
  let conversationId = null;
  let inflight = null;            // AbortController of the question being answered
  let research = new Map();       // message_id -> research request
  let stickToBottom = true;

  const inner = h('div', { class: 'thread__inner' });
  const thread = h('div', { class: 'thread', id: 'thread', tabindex: '-1', role: 'log', 'aria-live': 'polite',
                            'aria-relevant': 'additions' }, inner);
  thread.addEventListener('scroll', () => {
    stickToBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
  }, { passive: true });

  const input = h('textarea', { id: 'composer-input', rows: 1, placeholder: t('chat.placeholder'),
                                'aria-label': t('chat.placeholder'), enterkeyhint: 'send', dir: 'auto' });
  const send = h('button', { class: 'btn btn--primary', type: 'submit', id: 'composer-send' },
                 icon('action-upload'), h('span', { class: 'label', text: t('chat.send') }));
  const stop = h('button', { class: 'btn', type: 'button', id: 'composer-stop', hidden: true,
                             onclick: () => inflight?.abort() },
                 icon('action-close'), h('span', { text: t('chat.stop') }));
  const hint = h('p', { class: 'composer__hint subtle', id: 'composer-hint' });
  const form = h('form', { class: 'composer' }, h('div', { class: 'composer__inner' }, input, send, stop), hint);

  const autosize = () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, window.innerHeight * 0.4)}px`; };
  input.addEventListener('input', () => { store.setDraft(conversationId, input.value); autosize(); });
  input.addEventListener('keydown', (ev) => {
    // Enter sends on desktop; Shift+Enter is a new line. On touch keyboards Enter is a new line (the Send button sends).
    if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing && !matchMedia('(hover: none)').matches) {
      ev.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text || inflight || !ctx.online()) return;
    store.setDraft(conversationId, '');   // the draft is now a sent question, whichever thread it lands in
    input.value = '';
    autosize();
    await ask(text);
  });

  async function ensureConversation() {
    if (conversationId) return conversationId;
    const c = await store.create();
    conversationId = c.id;
    ctx.onConversationCreated(c);
    return c.id;
  }

  async function ask(text, retryOf) {
    const ac = new AbortController();
    inflight = ac;
    setBusy(true);
    try {
      const id = await ensureConversation();
      stickToBottom = true;
      if (retryOf) await store.retry(id, retryOf, { signal: ac.signal });
      else await store.ask(id, text, { signal: ac.signal });
      await refreshResearch();
      ctx.onAnswered?.();
    } catch (err) {
      if (err.kind === 'session_expired') return;
      if (!['aborted', 'timeout', 'in_progress'].includes(err.kind)) toast(err.message);
      if (!conversationId) input.value = text; // nothing was created: give the text back
    } finally {
      inflight = null;
      setBusy(false);
      render();
    }
  }

  function setBusy(busy) {
    send.hidden = busy;
    stop.hidden = !busy;
    input.setAttribute('aria-busy', String(busy));
  }

  async function refreshResearch() {
    try {
      const page = await ctx.http.get('/chat/research-requests?limit=50&state=pending_approval');
      research = new Map(page.items.filter((r) => r.conversation_id === conversationId).map((r) => [r.message_id, r]));
    } catch { research = new Map(); }
  }

  function statePill(state) {
    return h('span', { class: 'pill', dataset: { tone: TONE[state] ?? 'unknown' } },
             icon(STATE_ICON[state] ?? 'status-unknown'), t(`state.${state}`));
  }

  function citations(m) {
    if (!m.citations?.length) return null;
    return h('details', {},
      h('summary', {}, `${t('chat.sources')} (${m.citations.length})`),
      h('ol', { class: 'cites' }, m.citations.map((c) => h('li', {},
        h('span', { class: 'cite__n', text: `[${c.ordinal}]` }),
        h('span', { class: 'cite__text' }, c.claim_text || '',
          c.page_number != null ? h('span', { class: 'subtle' }, ' · ', t('chat.page', { n: c.page_number })) : null,
          c.contested ? h('span', { class: 'pill', dataset: { tone: 'warning' } }, ' ', t('chat.contested')) : null)))));
  }

  function researchCard(m) {
    const req = research.get(m.id);
    if (!req) return null;
    const box = h('div', { class: 'notice' }, h('p', { style: 'margin:0', text: t('research.pending') }),
      req.proposed_scope ? h('p', { class: 'subtle', text: typeof req.proposed_scope === 'string'
        ? req.proposed_scope : JSON.stringify(req.proposed_scope) }) : null);
    const decide = async (verb) => {
      try {
        const r = await ctx.http.post(`/chat/research-requests/${req.id}/${verb}`, {}, { retries: 0 });
        research.delete(m.id);
        toast(t('research.done', { state: r.state }));
        render();
      } catch (err) { toast(err.message); }
    };
    box.append(h('div', { class: 'msg__actions' },
      h('button', { class: 'btn btn--primary', type: 'button', onclick: () => decide('approve') }, t('research.approve')),
      h('button', { class: 'btn', type: 'button', onclick: () => decide('reject') }, t('research.reject'))));
    return box;
  }

  function messageView(m) {
    if (m.role === 'user') {
      const delivery = m.delivery && m.delivery !== 'confirmed'
        ? h('div', { class: 'delivery', dataset: { state: m.delivery }, role: m.delivery === 'failed' ? 'alert' : null },
            m.delivery === 'pending' ? [h('span', { class: 'spinner', 'aria-hidden': 'true' }), t('chat.thinking')]
              : [t(`delivery.${m.delivery}`), m.error && m.delivery === 'failed' ? ` ${m.error.message}` : '',
                 h('button', { class: 'btn btn--ghost', type: 'button', onclick: () => ask(m.text, m) },
                   icon('action-reprocess'), t('chat.retry'))])
        : null;
      return h('article', { class: 'msg msg--user', dataset: { id: m.id ?? m.localId } },
               h('div', { class: 'msg__body', dir: 'auto', text: m.text }), delivery);
    }
    const copyBtn = h('button', { class: 'btn btn--ghost icon-btn', type: 'button', 'aria-label': t('chat.copy'),
                                  onclick: async () => { await copy(m.text); toast(t('chat.copied')); } },
                      icon('action-copy'));
    return h('article', { class: 'msg msg--assistant', dataset: { id: m.id, state: m.answer_state } },
      h('div', { class: 'msg__meta' }, statePill(m.answer_state)),
      m.text ? h('div', { class: 'msg__body', dir: 'auto', text: m.text }) : null,
      m.limitation ? h('p', { class: 'limitation', dir: 'auto', text: m.limitation }) : null,
      citations(m), researchCard(m),
      h('div', { class: 'msg__actions' }, m.text ? copyBtn : null,
        m.answers_message_id ? h('button', { class: 'btn btn--ghost', type: 'button', onclick: async () => {
          try { await store.regenerate(conversationId, m.answers_message_id); render(); }
          catch (err) { toast(err.message); }
        } }, icon('action-reprocess'), t('chat.regenerate')) : null));
  }

  function render() {
    clear(inner);
    if (!conversationId || !store.thread(conversationId).messages.length) {
      inner.append(h('div', { class: 'empty' }, h('h2', { text: t('chat.empty_title') }),
                     h('p', { class: 'muted', text: t('chat.empty_body') })));
    } else {
      const th = store.thread(conversationId);
      if (!th.loadedAll) {
        inner.append(h('button', { class: 'btn btn--ghost', type: 'button', onclick: async () => {
          const before = thread.scrollHeight;
          await store.loadThread(conversationId, { older: true }).catch((e) => toast(e.message));
          render();
          thread.scrollTop = thread.scrollHeight - before;
        } }, t('chat.load_older')));
      }
      for (const m of th.messages) inner.append(messageView(m));
    }
    if (stickToBottom) thread.scrollTop = thread.scrollHeight;
  }

  async function open(id) {
    inflight?.abort();
    if (conversationId !== null || id !== null) store.setDraft(conversationId, input.value);
    conversationId = id;
    input.value = store.draft(id);
    autosize();
    stickToBottom = true;
    render();
    if (!id) return;
    try {
      await store.loadThread(id);
      await refreshResearch();
    } catch (err) { toast(err.message); }
    if (conversationId === id) render();
  }

  function setHint(text) { hint.textContent = text || ''; }

  return { thread, form, open, render, setHint, get conversationId() { return conversationId; },
           focus: () => input.focus(), setEnabled: (on) => { input.disabled = !on; send.disabled = !on; } };
}
