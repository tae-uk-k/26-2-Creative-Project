(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  if ('IntersectionObserver' in window && !reduced.matches) {
    document.body.classList.add('enhanced');
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); }
    }), { threshold: .01, rootMargin: '100px 0px' });
    document.querySelectorAll('.reveal').forEach(element => observer.observe(element));
    reduced.addEventListener('change', event => { if (event.matches) { document.body.classList.remove('enhanced'); observer.disconnect(); } });
  }
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  function selectTab(index, focus = false) {
    tabs.forEach((tab, i) => {
      tab.setAttribute('aria-selected', String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = i !== index;
    });
    if (focus) tabs[index].focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(index));
    tab.addEventListener('keydown', event => {
      let next;
      if (['ArrowDown', 'ArrowRight'].includes(event.key)) next = (index + 1) % tabs.length;
      if (['ArrowUp', 'ArrowLeft'].includes(event.key)) next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); selectTab(next, true); }
    });
  });
  const dialog = document.querySelector('.start-dialog');
  if (!dialog) return;
  let opener;
  const form = dialog.querySelector('form'), result = dialog.querySelector('.demo-result');
  document.querySelectorAll('[data-start]').forEach(button => button.addEventListener('click', () => {
    opener = button; form.hidden = false; result.hidden = true; dialog.showModal();
  }));
  function close() { dialog.close(); opener?.focus(); }
  dialog.querySelector('.dialog-close').addEventListener('click', close);
  dialog.querySelector('[data-demo-close]').addEventListener('click', close);
  dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) close(); } });
  form.addEventListener('submit', event => {
    event.preventDefault();
    dialog.querySelector('[data-demo-store]').textContent = form.elements.store.value.trim() || '입력한 가게';
    form.hidden = true; result.hidden = false; result.querySelector('button').focus();
  });
})();
