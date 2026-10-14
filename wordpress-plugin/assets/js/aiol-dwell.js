/**
 * Dwell-time beacon (Phase 13, ADR-078).
 *
 * Measures how long the page was actually VISIBLE, not how long the tab
 * existed. A tab left open behind a laptop lid for nine hours is not a
 * nine-hour read, and reporting it as one would poison every average it
 * touches.
 *
 * Sends at most twice: once on the first hide (a lower bound, in case the
 * visitor never comes back) and once when the page is discarded
 * (`complete: true`). The server only ever raises a stored value, so
 * arriving out of order is harmless.
 *
 * `navigator.sendBeacon` is used where available because a normal fetch
 * during unload is routinely cancelled — which is exactly when this
 * measurement is worth sending.
 */
(function () {
  'use strict';

  if (typeof window.AIOL_DWELL === 'undefined' || !window.AIOL_DWELL.eventKey) {
    return;
  }

  var visibleSince = document.visibilityState === 'visible' ? Date.now() : null;
  var accumulated = 0;
  var sentComplete = false;

  function accumulate() {
    if (visibleSince !== null) {
      accumulated += Date.now() - visibleSince;
      visibleSince = null;
    }
  }

  function send(complete) {
    accumulate();
    if (accumulated <= 0 || sentComplete) {
      return;
    }
    if (complete) {
      sentComplete = true;
    }

    var body = new FormData();
    body.append('action', 'aiol_dwell');
    body.append('nonce', window.AIOL_DWELL.nonce);
    body.append('event_key', window.AIOL_DWELL.eventKey);
    body.append('dwell_ms', String(accumulated));
    body.append('complete', complete ? '1' : '0');

    if (navigator.sendBeacon) {
      navigator.sendBeacon(window.AIOL_DWELL.ajaxUrl, body);
    } else {
      try {
        fetch(window.AIOL_DWELL.ajaxUrl, { method: 'POST', body: body, keepalive: true });
      } catch (e) {
        /* A lost measurement is a NULL on the server, which reads as
           "not reported". That is the correct outcome and needs no
           fallback that would invent a number. */
      }
    }
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      visibleSince = Date.now();
    } else {
      send(false);
    }
  });

  window.addEventListener('pagehide', function () { send(true); });
})();
