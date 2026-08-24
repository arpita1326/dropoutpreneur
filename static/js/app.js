const menu = document.querySelector('.menu');
const links = document.querySelector('.nav-links');
if (menu) menu.addEventListener('click', () => links.classList.toggle('open'));
document.querySelectorAll('form').forEach((form) => form.addEventListener('submit', () => {
  const button = form.querySelector('button[type="submit"]');
  if (button) { button.disabled = true; button.textContent = 'Working...'; }
}));
