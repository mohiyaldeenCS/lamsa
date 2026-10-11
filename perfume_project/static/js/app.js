const menuButton = document.querySelector('.menu-toggle');
const nav = document.querySelector('.main-nav');
if (menuButton && nav) {
  menuButton.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    menuButton.setAttribute('aria-expanded', String(open));
  });
  nav.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    nav.classList.remove('open');
    menuButton.setAttribute('aria-expanded', 'false');
  }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && nav.classList.contains('open')) {
      nav.classList.remove('open');
      menuButton.setAttribute('aria-expanded', 'false');
      menuButton.focus();
    }
  });
}
document.querySelectorAll('.toast button').forEach(button => button.addEventListener('click', () => button.closest('.toast').remove()));
document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
  if (!window.confirm(form.dataset.confirm)) event.preventDefault();
}));

const quickDialog = document.querySelector('#quick-view');
if (quickDialog && typeof quickDialog.showModal === 'function') {
  let lastTrigger;
  document.querySelectorAll('[data-quick-view]').forEach(button => {
    button.addEventListener('click', () => {
      const template = document.getElementById(button.dataset.quickView);
      if (!template) return;
      lastTrigger = button;
      quickDialog.querySelector('.quick-content').replaceChildren(template.content.cloneNode(true));
      quickDialog.showModal();
      document.body.classList.add('dialog-open');
      quickDialog.querySelector('.dialog-close').focus();
    });
  });
  quickDialog.querySelector('.dialog-close').addEventListener('click', () => quickDialog.close());
  quickDialog.addEventListener('click', event => {
    if (event.target !== quickDialog) return;
    const box = quickDialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) quickDialog.close();
  });
  quickDialog.addEventListener('close', () => {
    document.body.classList.remove('dialog-open');
    quickDialog.querySelector('.quick-content').replaceChildren();
    lastTrigger?.focus();
  });
} else {
  document.querySelectorAll('[data-quick-view]').forEach(button => button.hidden = true);
}

document.querySelectorAll('[data-auto-submit]').forEach(select => {
  select.addEventListener('change', () => select.form.requestSubmit());
});
