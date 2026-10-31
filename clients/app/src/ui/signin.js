// Sign-in screen. Two methods, both already used by AIOL: an emailed six-digit code (default) and a password.
// Nothing about the session is decided here; the server's answer is shown as it is written.
import { h } from './dom.js';
import { icon } from './icons.js';

export function signInView({ t, session, links, openLink, onSignedIn }) {
  let mode = 'code';
  let sent = false;
  const status = h('p', { class: 'subtle', role: 'status' });
  const error = h('p', { class: 'error-text', role: 'alert' });
  const email = h('input', { type: 'email', id: 'si-email', autocomplete: 'username', required: true, inputmode: 'email' });
  const code = h('input', { type: 'text', id: 'si-code', autocomplete: 'one-time-code', inputmode: 'numeric',
                            pattern: '[0-9]{6}', maxlength: '6' });
  const password = h('input', { type: 'password', id: 'si-password', autocomplete: 'current-password' });
  const codeRow = h('div', { hidden: true }, h('label', { for: 'si-code', text: t('signin.code') }), code);
  const pwRow = h('div', { hidden: true }, h('label', { for: 'si-password', text: t('signin.password') }), password);
  const primary = h('button', { class: 'btn btn--primary', type: 'submit' });
  const toggle = h('button', { class: 'linkish', type: 'button' });

  const render = () => {
    codeRow.hidden = !(mode === 'code' && sent);
    pwRow.hidden = mode !== 'password';
    primary.textContent = mode === 'code' && !sent ? t('signin.send_code') : t('signin.verify');
    toggle.textContent = mode === 'code' ? t('signin.use_password') : t('signin.use_code');
  };

  toggle.addEventListener('click', () => { mode = mode === 'code' ? 'password' : 'code'; error.textContent = ''; render(); });

  const form = h('form', { class: 'signin__card', novalidate: true, 'aria-labelledby': 'si-title' },
    h('div', { class: 'signin__brand' }, h('img', { src: './brand/aiol-logo.svg', alt: '', width: 28, height: 28 }),
      h('h1', { id: 'si-title', text: t('signin.title'), style: 'font-size: inherit; margin: 0' })),
    h('div', {}, h('label', { for: 'si-email', text: t('signin.email') }), email),
    codeRow, pwRow, primary, status, error, toggle,
    h('nav', { class: 'signin__links' },
      ...[['help', 'menu.help'], ['privacy', 'settings.legal'], ['terms', 'settings.terms']]
        .filter(([k]) => links[k])
        .map(([k, label]) => h('button', { class: 'linkish', type: 'button', onclick: () => openLink(links[k]) },
                                t(label), ' ', icon('action-external')))));

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    error.textContent = '';
    status.textContent = '';
    if (!email.value.trim()) { email.focus(); return; }
    primary.disabled = true;
    try {
      if (mode === 'code' && !sent) {
        await session.requestCode(email.value.trim());
        sent = true;
        status.textContent = t('signin.code_sent', { email: email.value.trim() });
        render();
        code.focus();
      } else {
        await session.signIn(mode === 'code'
          ? { email: email.value.trim(), code: code.value.trim() }
          : { email: email.value.trim(), password: password.value });
        password.value = '';
        onSignedIn();
      }
    } catch (err) {
      error.textContent = err.message;
    } finally {
      primary.disabled = false;
    }
  });

  render();
  return h('main', { class: 'signin' }, form);
}
