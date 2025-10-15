document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('menuToggle');
  const menu = document.getElementById('mainMenu');
  if (btn && menu) {
    btn.addEventListener('click', () => {
      menu.classList.toggle('open');
    });
  }
});
