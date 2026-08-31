/* ==========================================================================
   VIPADSUZ / AutoXabar — frontend
   ========================================================================== */
(function () {
  'use strict';

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* ---------------------------------------------------------- Toast */
  const ICONS = {
    success: '<path d="M20 6 9 17l-5-5"/>',
    error: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
    danger: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
    warning: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>'
  };

  function toast(message, kind = 'info', ms = 4600) {
    let box = $('.toasts');
    if (!box) {
      box = document.createElement('div');
      box.className = 'toasts';
      document.body.appendChild(box);
    }
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    el.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" stroke-linejoin="round">' + (ICONS[kind] || ICONS.info) + '</svg>' +
      '<div class="msg"></div>' +
      '<button class="x" aria-label="Yopish">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>';
    $('.msg', el).textContent = message;

    const close = () => {
      el.classList.add('out');
      setTimeout(() => el.remove(), 300);
    };
    $('.x', el).addEventListener('click', close);
    box.appendChild(el);
    if (ms) setTimeout(close, ms);
    return el;
  }

  window.toast = toast;

  /* ---------------------------------------------------------- Modal */
  function openModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.add('open');
    document.body.style.overflow = 'hidden';
    const focusable = m.querySelector('input:not([type=hidden]), textarea, select, button');
    if (focusable) setTimeout(() => focusable.focus(), 120);
  }

  function closeModal(el) {
    const m = typeof el === 'string' ? document.getElementById(el) : el;
    if (!m) return;
    m.classList.remove('open');
    if (!$('.modal-backdrop.open')) document.body.style.overflow = '';
  }

  window.openModal = openModal;
  window.closeModal = closeModal;

  document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-modal]');
    if (opener) {
      e.preventDefault();
      // Ma'lumotlarni modalga uzatish: data-set-<field>
      const m = document.getElementById(opener.dataset.modal);
      if (m) {
        Object.keys(opener.dataset).forEach((key) => {
          if (!key.startsWith('set')) return;
          const name = key.slice(3).toLowerCase();
          const target = m.querySelector('[data-fill="' + name + '"]');
          if (!target) return;
          if ('value' in target && target.tagName !== 'DIV') target.value = opener.dataset[key];
          else target.textContent = opener.dataset[key];
        });
      }
      openModal(opener.dataset.modal);
      return;
    }

    if (e.target.closest('[data-close]')) {
      e.preventDefault();
      closeModal(e.target.closest('.modal-backdrop'));
      return;
    }

    if (e.target.classList.contains('modal-backdrop')) closeModal(e.target);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const open = $('.modal-backdrop.open');
      if (open) closeModal(open);
      $$('.dropdown.open').forEach((d) => d.classList.remove('open'));
    }
  });

  /* ---------------------------------------------------------- Dropdown */
  document.addEventListener('click', (e) => {
    const trigger = e.target.closest('[data-dropdown]');
    $$('.dropdown.open').forEach((d) => {
      if (!trigger || d !== trigger.closest('.dropdown')) d.classList.remove('open');
    });
    if (trigger) {
      e.preventDefault();
      trigger.closest('.dropdown').classList.toggle('open');
    }
  });

  /* ---------------------------------------------------------- Sarlavha / menyu */
  const header = $('.site-header');
  if (header) {
    const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  const burger = $('.burger');
  if (burger) {
    burger.addEventListener('click', () => {
      burger.classList.toggle('open');
      $('.nav').classList.toggle('open');
    });
    $$('.nav a').forEach((a) =>
      a.addEventListener('click', () => {
        burger.classList.remove('open');
        $('.nav').classList.remove('open');
      })
    );
  }

  /* ---------------------------------------------------------- Sidebar (mobil) */
  const sidebar = $('.sidebar');
  const sideToggle = $('.sidebar-toggle');
  if (sidebar && sideToggle) {
    let overlay = $('.overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'overlay';
      document.body.appendChild(overlay);
    }
    const close = () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('show');
    };
    sideToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      overlay.classList.toggle('show');
    });
    overlay.addEventListener('click', close);
    $$('.nav-item', sidebar).forEach((a) => a.addEventListener('click', close));
  }

  /* ---------------------------------------------------------- FAQ */
  $$('.faq-q').forEach((btn) => {
    btn.addEventListener('click', () => {
      const item = btn.closest('.faq-item');
      const body = $('.faq-a', item);
      const isOpen = item.classList.contains('open');
      $$('.faq-item.open').forEach((other) => {
        if (other !== item) {
          other.classList.remove('open');
          $('.faq-a', other).style.maxHeight = null;
        }
      });
      item.classList.toggle('open', !isOpen);
      body.style.maxHeight = isOpen ? null : body.scrollHeight + 'px';
    });
  });

  /* ---------------------------------------------------------- Tablar */
  $$('[data-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      const group = tab.closest('.tabs');
      const name = tab.dataset.tab;
      $$('[data-tab]', group).forEach((t) => t.classList.toggle('active', t === tab));
      const scope = group.parentElement;
      $$('.tab-panel', scope).forEach((p) =>
        p.classList.toggle('active', p.dataset.panel === name)
      );
      if (history.replaceState) {
        history.replaceState(null, '', '#' + name);
      }
    });
  });

  if (location.hash) {
    const target = $('[data-tab="' + location.hash.slice(1) + '"]');
    if (target) target.click();
  }

  /* ---------------------------------------------------------- Nusxalash */
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    e.preventDefault();
    const text = btn.dataset.copy;
    const done = () => toast('Nusxalandi', 'success', 1800);
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
    } else fallbackCopy(text, done);
  });

  function fallbackCopy(text, done) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (err) { toast('Nusxalab bo‘lmadi', 'error'); }
    ta.remove();
  }

  /* ---------------------------------------------------------- Tasdiqlash */
  document.addEventListener('submit', (e) => {
    const form = e.target;
    const msg = form.dataset.confirm;
    if (msg && !window.confirm(msg)) {
      e.preventDefault();
      return;
    }
    const btn = form.querySelector('button[type=submit], .btn-submit');
    if (btn && !form.dataset.noLoading) {
      setTimeout(() => btn.classList.add('is-loading'), 0);
      setTimeout(() => btn.classList.remove('is-loading'), 12000);
    }
  });

  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[data-confirm]');
    if (link && !window.confirm(link.dataset.confirm)) e.preventDefault();
  });

  /* ---------------------------------------------------------- Avto-yuborish */
  $$('[data-autosubmit]').forEach((el) => {
    el.addEventListener('change', () => el.closest('form').submit());
  });

  /* ---------------------------------------------------------- Parolni ko'rsatish */
  $$('[data-toggle-pass]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.togglePass);
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.innerHTML = show
        ? '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9.9 4.2A10.9 10.9 0 0 1 12 4c7 0 10 8 10 8a18.5 18.5 0 0 1-2.2 3.2M6.6 6.6A18.5 18.5 0 0 0 2 12s3 8 10 8a10.9 10.9 0 0 0 5.4-1.4"/><path d="m2 2 20 20"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>'
        : '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M2 12s3-8 10-8 10 8 10 8-3 8-10 8-10-8-10-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    });
  });

  /* ---------------------------------------------------------- Telefon maskasi */
  $$('[data-phone]').forEach((input) => {
    const format = (raw) => {
      let d = raw.replace(/\D/g, '');
      if (d.startsWith('998')) d = d.slice(3);
      d = d.slice(0, 9);
      let out = '+998';
      if (d.length) out += ' ' + d.slice(0, 2);
      if (d.length > 2) out += ' ' + d.slice(2, 5);
      if (d.length > 5) out += ' ' + d.slice(5, 7);
      if (d.length > 7) out += ' ' + d.slice(7, 9);
      return out;
    };
    const apply = () => { input.value = format(input.value); };
    input.addEventListener('focus', () => { if (!input.value.trim()) input.value = '+998 '; });
    input.addEventListener('input', apply);
    input.addEventListener('blur', () => { if (input.value.trim() === '+998') input.value = ''; });
    if (input.value) apply();
  });

  /* ---------------------------------------------------------- Karta maskasi */
  $$('[data-card]').forEach((input) => {
    input.addEventListener('input', () => {
      const d = input.value.replace(/\D/g, '').slice(0, 16);
      input.value = (d.match(/.{1,4}/g) || []).join(' ');
    });
  });

  $$('[data-expire]').forEach((input) => {
    input.addEventListener('input', () => {
      const d = input.value.replace(/\D/g, '').slice(0, 4);
      input.value = d.length > 2 ? d.slice(0, 2) + '/' + d.slice(2) : d;
    });
  });

  /* ---------------------------------------------------------- OTP kiritish */
  /* Har bir katakning o'z name="code" atributi bor, shuning uchun forma
     JavaScriptsiz ham to'g'ri yuboriladi. Bu yerda faqat qulaylik:
     avtomatik o'tish, backspace va joylashtirish (paste). */
  $$('.otp').forEach((box) => {
    const inputs = $$('input', box);

    const maybeSubmit = () => {
      if (box.dataset.autosubmit === 'off') return;
      if (!inputs.every((i) => i.value)) return;
      const form = box.closest('form');
      if (form) (form.requestSubmit ? form.requestSubmit() : form.submit());
    };

    inputs.forEach((input, idx) => {
      input.addEventListener('input', () => {
        input.value = input.value.replace(/\D/g, '').slice(0, 1);
        if (input.value && idx < inputs.length - 1) inputs[idx + 1].focus();
        maybeSubmit();
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !input.value && idx > 0) {
          inputs[idx - 1].focus();
          inputs[idx - 1].value = '';
          e.preventDefault();
        }
        if (e.key === 'ArrowLeft' && idx > 0) inputs[idx - 1].focus();
        if (e.key === 'ArrowRight' && idx < inputs.length - 1) inputs[idx + 1].focus();
      });

      input.addEventListener('focus', () => input.select());

      input.addEventListener('paste', (e) => {
        e.preventDefault();
        const digits = ((e.clipboardData || window.clipboardData).getData('text') || '')
          .replace(/\D/g, '');
        if (!digits) return;
        inputs.forEach((el, i) => { el.value = digits[i] || ''; });
        (inputs[Math.min(digits.length, inputs.length - 1)] || inputs[0]).focus();
        maybeSubmit();
      });
    });

    if (inputs[0]) inputs[0].focus();
  });

  /* ---------------------------------------------------------- Sanoq animatsiyasi */
  function animateCount(el) {
    const target = parseFloat(el.dataset.count);
    if (isNaN(target)) return;
    const suffix = el.dataset.suffix || '';
    const dur = 1100;
    const start = performance.now();
    const fmt = (n) => Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' ');
    const step = (now) => {
      const t = Math.min((now - start) / dur, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(target * eased) + suffix;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /* ---------------------------------------------------------- Skroll animatsiyasi */
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('in');
          $$('[data-count]', entry.target).forEach(animateCount);
          if (entry.target.hasAttribute('data-count')) animateCount(entry.target);
          io.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    $$('.reveal, [data-count]').forEach((el) => io.observe(el));

    // Xavfsizlik to'ri: kuzatuvchi ishlamay qolsa ham kontent ko'rinsin
    setTimeout(() => {
      $$('.reveal:not(.in)').forEach((el) => {
        if (el.getBoundingClientRect().top < window.innerHeight * 1.4) {
          el.classList.add('in');
          $$('[data-count]', el).forEach(animateCount);
        }
      });
    }, 1600);
  } else {
    $$('.reveal').forEach((el) => el.classList.add('in'));
    $$('[data-count]').forEach(animateCount);
  }

  /* ---------------------------------------------------------- Grafik */
  function drawChart(host) {
    let data;
    try { data = JSON.parse(host.dataset.chart); } catch (e) { return; }
    if (!data || !data.length) return;

    const type = host.dataset.type || 'bar';
    const valueKey = host.dataset.key || 'value';
    const labelKey = host.dataset.label || 'label';
    const W = 760, H = 230, PAD_L = 46, PAD_R = 12, PAD_T = 14, PAD_B = 28;
    const iw = W - PAD_L - PAD_R;
    const ih = H - PAD_T - PAD_B;
    const values = data.map((d) => Number(d[valueKey]) || 0);
    const max = Math.max(...values, 1);
    const nice = niceMax(max);

    const short = (n) => {
      if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
      if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
      if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'K';
      return String(Math.round(n));
    };

    let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img">';
    svg += '<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#F4D477"/><stop offset="100%" stop-color="#B07F09"/></linearGradient>' +
      '<linearGradient id="cgf" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="rgba(232,190,58,.42)"/>' +
      '<stop offset="100%" stop-color="rgba(232,190,58,0)"/></linearGradient></defs>';

    // To'r va o'q
    svg += '<g class="chart-grid">';
    for (let i = 0; i <= 4; i++) {
      const y = PAD_T + (ih / 4) * i;
      svg += '<line x1="' + PAD_L + '" y1="' + y + '" x2="' + (W - PAD_R) + '" y2="' + y + '"/>';
      svg += '<text class="chart-axis" x="' + (PAD_L - 8) + '" y="' + (y + 3.5) +
        '" text-anchor="end">' + short(nice - (nice / 4) * i) + '</text>';
    }
    svg += '</g>';

    const stepX = iw / data.length;

    if (type === 'line') {
      const pts = data.map((d, i) => {
        const x = PAD_L + stepX * i + stepX / 2;
        const y = PAD_T + ih - ((Number(d[valueKey]) || 0) / nice) * ih;
        return [x, y];
      });
      const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
      svg += '<path d="' + path + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + (PAD_T + ih) +
        ' L' + pts[0][0].toFixed(1) + ' ' + (PAD_T + ih) + ' Z" fill="url(#cgf)"/>';
      svg += '<path d="' + path + '" fill="none" stroke="url(#cg)" stroke-width="2.5" ' +
        'stroke-linecap="round" stroke-linejoin="round"/>';
      pts.forEach((p, i) => {
        svg += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) +
          '" r="3" fill="#E8BE3A"><title>' + esc(data[i][labelKey]) + ': ' +
          fmtNum(values[i]) + '</title></circle>';
      });
    } else {
      const bw = Math.max(Math.min(stepX * 0.6, 42), 3);
      data.forEach((d, i) => {
        const v = Number(d[valueKey]) || 0;
        const h = Math.max((v / nice) * ih, v > 0 ? 2 : 0);
        const x = PAD_L + stepX * i + (stepX - bw) / 2;
        const y = PAD_T + ih - h;
        svg += '<rect class="chart-bar" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) +
          '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) +
          '" rx="' + Math.min(bw / 2, 5).toFixed(1) + '" fill="url(#cg)">' +
          '<title>' + esc(d[labelKey]) + ': ' + fmtNum(v) + '</title></rect>';
      });
    }

    // X o'qi belgilari
    const every = Math.ceil(data.length / 12);
    data.forEach((d, i) => {
      if (i % every) return;
      const x = PAD_L + stepX * i + stepX / 2;
      svg += '<text class="chart-axis" x="' + x.toFixed(1) + '" y="' + (H - 8) +
        '" text-anchor="middle">' + esc(String(d[labelKey])) + '</text>';
    });

    svg += '</svg>';
    host.innerHTML = svg;
  }

  function niceMax(max) {
    const mag = Math.pow(10, Math.floor(Math.log10(max)));
    const n = max / mag;
    const mult = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
    return mult * mag;
  }

  function fmtNum(n) {
    return Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' ');
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  $$('[data-chart]').forEach(drawChart);
  window.drawChart = drawChart;

  /* ---------------------------------------------------------- Jonli yangilash */
  const live = $('[data-live]');
  if (live) {
    const url = live.dataset.live;
    const every = parseInt(live.dataset.every || '20000', 10);
    const refresh = () => {
      if (document.hidden) return;
      fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!data || !data.ok) return;
          Object.keys(data.values || {}).forEach((key) => {
            $$('[data-live-key="' + key + '"]').forEach((el) => {
              const next = data.values[key];
              if (el.textContent !== String(next)) {
                el.textContent = next;
                el.style.transition = 'color .3s';
                el.style.color = '#F4D477';
                setTimeout(() => { el.style.color = ''; }, 700);
              }
            });
          });
        })
        .catch(() => {});
    };
    setInterval(refresh, Math.max(every, 5000));
  }

  /* ---------------------------------------------------------- Qidiruv filtri */
  $$('[data-filter]').forEach((input) => {
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      const targets = $$(input.dataset.filter);
      let shown = 0;
      targets.forEach((row) => {
        const match = !q || row.textContent.toLowerCase().includes(q);
        row.style.display = match ? '' : 'none';
        if (match) shown++;
      });
      const empty = $(input.dataset.filterEmpty || '.filter-empty');
      if (empty) empty.classList.toggle('hidden', shown > 0);
    });
  });

  /* ---------------------------------------------------------- Barchasini tanlash */
  $$('[data-check-all]').forEach((master) => {
    master.addEventListener('change', () => {
      $$(master.dataset.checkAll).forEach((cb) => { cb.checked = master.checked; });
    });
  });

  /* ---------------------------------------------------------- Flash xabarlar */
  $$('[data-flash]').forEach((el) => {
    toast(el.dataset.flash, el.dataset.kind || 'info');
    el.remove();
  });

  /* ---------------------------------------------------------- Vaqt hisoblagich */
  $$('[data-countdown]').forEach((el) => {
    let left = parseInt(el.dataset.countdown, 10);
    const btn = el.closest('button');
    const tick = () => {
      if (left <= 0) {
        el.textContent = '';
        if (btn) { btn.disabled = false; btn.textContent = btn.dataset.readyText || 'Qayta yuborish'; }
        return;
      }
      const m = Math.floor(left / 60);
      const s = left % 60;
      el.textContent = m ? m + ':' + String(s).padStart(2, '0') : s + ' s';
      left--;
      setTimeout(tick, 1000);
    };
    if (btn) btn.disabled = true;
    tick();
  });

  /* ---------------------------------------------------------- Matn hisoblagichi */
  $$('[data-counter]').forEach((input) => {
    const out = $(input.dataset.counter);
    if (!out) return;
    const max = parseInt(input.getAttribute('maxlength') || '4096', 10);
    const upd = () => {
      out.textContent = input.value.length + ' / ' + max;
      out.style.color = input.value.length > max * 0.92 ? 'var(--warn)' : '';
    };
    input.addEventListener('input', upd);
    upd();
  });
})();
