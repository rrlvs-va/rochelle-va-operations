(function () {
  'use strict';

  const WELCOME_KEY = 'theRochelleEditWelcomeSeen';
  const VISIT_TRACK_KEY = 'theRochelleEditVisitTracked';
  const UMAMI_WEBSITE_ID = '4d20ec6e-67e3-44fc-acd3-5c53bfd78c80';
  const UMAMI_SCRIPT = 'https://cloud.umami.is/script.js';
  const query = new URLSearchParams(window.location.search);
  const forceWelcomePreview = query.get('welcome') === 'preview';

  function safeGet(storage, key) {
    try { return storage.getItem(key); } catch (_) { return null; }
  }

  function safeSet(storage, key, value) {
    try { storage.setItem(key, value); return true; } catch (_) { return false; }
  }

  const hadWelcome = safeGet(window.localStorage, WELCOME_KEY) === '1';
  const visitorType = hadWelcome ? 'returning' : 'first';

  if (!hadWelcome && !forceWelcomePreview) {
    safeSet(window.localStorage, WELCOME_KEY, '1');
  }

  function getEntryType() {
    const path = window.location.pathname.toLowerCase();
    if (path.endsWith('/article.html') || path.endsWith('article.html')) return 'article';
    return 'blog-home';
  }

  function withUmami(callback) {
    let completed = false;

    function invokeOnce() {
      if (completed || !window.umami || typeof window.umami.track !== 'function') return false;
      completed = true;
      callback();
      return true;
    }

    if (invokeOnce()) return;

    let script = document.querySelector('script[data-rochelle-umami="true"]') ||
      document.querySelector('script[data-website-id="' + UMAMI_WEBSITE_ID + '"]');

    if (!script) {
      script = document.createElement('script');
      script.defer = true;
      script.src = UMAMI_SCRIPT;
      script.dataset.websiteId = UMAMI_WEBSITE_ID;
      script.dataset.domains = 'rrlvsva.wasmer.app';
      script.dataset.rochelleUmami = 'true';
      document.head.appendChild(script);
    }

    function runWhenReady() {
      let attempts = 0;
      const timer = window.setInterval(function () {
        attempts += 1;
        if (invokeOnce() || attempts >= 30) {
          window.clearInterval(timer);
        }
      }, 200);
    }

    script.addEventListener('load', runWhenReady, { once: true });
    window.setTimeout(runWhenReady, 500);
  }

  function trackBlogVisit() {
    if (safeGet(window.sessionStorage, VISIT_TRACK_KEY) === '1') return;
    safeSet(window.sessionStorage, VISIT_TRACK_KEY, '1');

    withUmami(function () {
      window.umami.track('blog-visit', {
        visitor_type: visitorType,
        entry: getEntryType()
      });
    });
  }

  function trackReaderSignal() {
    if (getEntryType() !== 'article') return;

    let elapsedEnough = false;
    let scrolledEnough = false;
    let tracked = false;

    function maybeTrack() {
      if (tracked || !elapsedEnough || !scrolledEnough) return;
      tracked = true;
      withUmami(function () {
        window.umami.track('blog-reader', {
          article: document.title.replace(' | The Rochelle Edit', '')
        });
      });
      window.removeEventListener('scroll', checkScroll);
    }

    function checkScroll() {
      const doc = document.documentElement;
      const scrollable = Math.max(doc.scrollHeight - window.innerHeight, 1);
      const depth = window.scrollY / scrollable;
      if (depth >= 0.25) {
        scrolledEnough = true;
        maybeTrack();
      }
    }

    window.addEventListener('scroll', checkScroll, { passive: true });
    checkScroll();
    window.setTimeout(function () {
      elapsedEnough = true;
      maybeTrack();
    }, 20000);
  }

  function injectWelcomeStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .tre-welcome{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:24px;background:rgba(9,8,7,.68);backdrop-filter:blur(7px);opacity:0;pointer-events:none;transition:opacity .22s ease;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
      .tre-welcome.show{opacity:1;pointer-events:auto}
      .tre-welcome-panel{position:relative;width:min(620px,100%);max-height:min(84vh,720px);overflow:auto;background:radial-gradient(circle at 14% 14%,rgba(203,143,150,.10),transparent 28%),radial-gradient(circle at 88% 82%,rgba(209,171,99,.10),transparent 32%),#181512;color:#f7f1ea;border:1px solid #5a4738;box-shadow:0 28px 80px rgba(0,0,0,.48);padding:42px 42px 36px;text-align:center;transform:translateY(14px) scale(.985);transition:transform .22s ease}
      .tre-welcome.show .tre-welcome-panel{transform:translateY(0) scale(1)}
      .tre-welcome-panel:before{content:"";position:absolute;left:54px;right:54px;top:0;height:1px;background:linear-gradient(90deg,transparent,#d1ab63,#cb8f96,transparent)}
      .tre-welcome-close{position:absolute;top:13px;right:14px;width:38px;height:38px;border:0;background:transparent;color:#b9aca1;font-size:1.45rem;cursor:pointer;border-radius:50%}
      .tre-welcome-close:hover,.tre-welcome-close:focus-visible{color:#fff;background:#27211d;outline:none}
      .tre-welcome-eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:.7rem;font-weight:800;color:#cb8f96;margin:0 36px 10px}
      .tre-welcome-title{font:500 clamp(2.45rem,6vw,3.7rem)/1 Georgia,"Times New Roman",serif;margin:0 auto 22px;color:#f7f1ea;letter-spacing:-.035em}
      .tre-welcome-copy{margin:0 auto;color:#c9bbb0;font-size:1rem;line-height:1.7;max-width:500px}
      .tre-welcome-copy + .tre-welcome-copy{margin-top:8px}
      .tre-welcome-copy.hello{color:#f0e5dc;font-weight:750}
      .tre-welcome-actions{display:flex;align-items:center;justify-content:center;gap:16px;margin-top:26px;flex-wrap:wrap}
      .tre-welcome-primary{border:0;border-radius:999px;background:#d1ab63;color:#17110d;padding:11px 17px;font-weight:800;cursor:pointer}
      .tre-welcome-primary:hover,.tre-welcome-primary:focus-visible{filter:brightness(1.05);outline:2px solid rgba(209,171,99,.4);outline-offset:3px}
      .tre-welcome-link{color:#d9c6b4;font-size:.82rem;text-decoration:none;border-bottom:1px solid rgba(217,198,180,.35)}
      .tre-welcome-link:hover{color:#fff}
      @media(max-width:620px){.tre-welcome{padding:16px}.tre-welcome-panel{width:100%;max-height:84vh;padding:36px 22px 28px}.tre-welcome-panel:before{left:32px;right:32px}.tre-welcome-title{font-size:clamp(2.2rem,11vw,3rem);margin-bottom:18px}.tre-welcome-copy{font-size:.94rem}.tre-welcome-actions{margin-top:22px}}
      @media(max-height:560px){.tre-welcome{align-items:start;overflow:auto}.tre-welcome-panel{margin:auto 0;max-height:none}}
      @media(prefers-reduced-motion:reduce){.tre-welcome,.tre-welcome-panel{transition:none}}
    `;
    document.head.appendChild(style);
  }

  function showWelcome() {
    if (hadWelcome && !forceWelcomePreview) return;

    injectWelcomeStyles();
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement;
    const box = document.createElement('aside');
    box.className = 'tre-welcome';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', 'tre-welcome-title');
    box.innerHTML = `
      <div class="tre-welcome-panel">
        <button class="tre-welcome-close" type="button" aria-label="Close welcome">×</button>
        <div class="tre-welcome-eyebrow">The Rochelle Edit</div>
        <h2 class="tre-welcome-title" id="tre-welcome-title">Welcome to the Blog</h2>
        <p class="tre-welcome-copy hello">Thanks for stopping by!</p>
        <p class="tre-welcome-copy">This space is a growing collection of published thoughts, practical ideas, and resources by Rochelle V. Silvestre.</p>
        <div class="tre-welcome-actions">
          <button class="tre-welcome-primary" type="button">Start reading</button>
          <a class="tre-welcome-link" href="../../privacy.html">Privacy</a>
        </div>
      </div>
    `;

    document.body.appendChild(box);
    document.body.style.overflow = 'hidden';
    const closeButton = box.querySelector('.tre-welcome-close');
    const primaryButton = box.querySelector('.tre-welcome-primary');

    function closeWelcome() {
      box.classList.remove('show');
      document.body.style.overflow = previousOverflow;
      if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
      window.setTimeout(function () { box.remove(); }, 230);
    }

    closeButton.addEventListener('click', closeWelcome);
    primaryButton.addEventListener('click', closeWelcome);
    box.addEventListener('click', function (event) {
      if (event.target === box) closeWelcome();
    });
    document.addEventListener('keydown', function onKeydown(event) {
      if (event.key === 'Escape' && document.body.contains(box)) {
        closeWelcome();
        document.removeEventListener('keydown', onKeydown);
      }
    });

    window.setTimeout(function () {
      box.classList.add('show');
      closeButton.focus();
    }, 650);
  }

  function init() {
    trackBlogVisit();
    trackReaderSignal();
    showWelcome();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
