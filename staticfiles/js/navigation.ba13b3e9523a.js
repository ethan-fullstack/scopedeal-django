(() => {
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('navigation-backdrop');
  const toggle = document.getElementById('navigation-toggle');
  const closeNavigation = () => {
    if (!sidebar) return;
    sidebar.classList.add('hidden');
    sidebar.classList.remove('flex');
    backdrop.classList.add('hidden');
    toggle.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  };
  toggle?.addEventListener('click', () => {
    const opening = toggle.getAttribute('aria-expanded') !== 'true';
    if (!opening) { closeNavigation(); return; }
    sidebar.classList.remove('hidden');
    sidebar.classList.add('flex');
    backdrop.classList.remove('hidden');
    toggle.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    sidebar.querySelector('button')?.focus();
  });
  document.querySelectorAll('[data-close-navigation]').forEach(button => button.addEventListener('click', () => { closeNavigation(); toggle?.focus(); }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeNavigation();
      document.querySelectorAll('details[open]').forEach(element => element.removeAttribute('open'));
      toggle?.focus();
    }
    if (event.key === 'Tab' && toggle?.getAttribute('aria-expanded') === 'true') {
      const controls = Array.from(sidebar.querySelectorAll('a, button')).filter(element => element.offsetParent !== null);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { last.focus(); event.preventDefault(); }
      else if (!event.shiftKey && document.activeElement === last) { first.focus(); event.preventDefault(); }
    }
  });
  window.matchMedia('(min-width: 1024px)').addEventListener('change', closeNavigation);
  const links = Array.from(document.querySelectorAll('[data-section-link]'));
  const updateSection = () => {
    const current = window.location.hash || (window.location.pathname.endsWith('/budget/') ? '#budget' : '#overview');
    links.forEach(link => {
      if (new URL(link.href).pathname === window.location.pathname && new URL(link.href).hash === current) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  };
  window.addEventListener('hashchange', updateSection);
  updateSection();
  document.querySelectorAll('[data-file-input]').forEach(input => {
    input.addEventListener('change', () => {
      const output = document.getElementById(input.dataset.fileOutput);
      if (output) output.textContent = input.files[0]?.name || 'Ningún archivo seleccionado';
    });
  });
})();
