// A minimal SMTP receiver for the e2e only (no dependency, no application code involved): AI Core's real sender
// (smtplib, configured through SMTP_HOST / SMTP_PORT / SMTP_STARTTLS=false) delivers to it on 127.0.0.1, and the
// e2e reads the emailed sign-in code from the captured message. Messages are kept in memory for the run.
import { createServer } from 'node:net';

export function startCatcher(port) {
  const messages = [];
  const server = createServer((sock) => {
    let buf = '';
    let inData = false;
    let envelope = { from: '', to: [] };
    let body = [];
    const say = (s) => sock.write(`${s}\r\n`);
    say('220 aiol-e2e-catcher');
    sock.on('data', (chunk) => {
      buf += chunk.toString('latin1');
      for (let i = buf.indexOf('\r\n'); i !== -1; i = buf.indexOf('\r\n')) {
        const line = buf.slice(0, i);
        buf = buf.slice(i + 2);
        if (inData) {
          if (line === '.') {
            inData = false;
            messages.push({ ...envelope, raw: body.join('\n') });
            body = [];
            say('250 queued');
          } else body.push(line.startsWith('..') ? line.slice(1) : line);
          continue;
        }
        const cmd = line.slice(0, 4).toUpperCase();
        if (cmd === 'EHLO' || cmd === 'HELO') say('250 aiol-e2e-catcher');
        else if (cmd === 'MAIL') { envelope = { from: line.slice(10), to: [] }; say('250 ok'); }
        else if (cmd === 'RCPT') { envelope.to.push(line.slice(8)); say('250 ok'); }
        else if (cmd === 'DATA') { inData = true; say('354 end with <CRLF>.<CRLF>'); }
        else if (cmd === 'QUIT') { say('221 bye'); sock.end(); }
        else if (cmd === 'RSET' || cmd === 'NOOP') say('250 ok');
        else say('502 not implemented');
      }
    });
    sock.on('error', () => {});
  });
  return new Promise((ok, fail) => {
    server.once('error', fail);
    server.listen(port, '127.0.0.1', () => ok({ messages, close: () => server.close() }));
  });
}
