document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("menuToggle");
  const mainMenu = document.getElementById("mainMenu");
  if (btn && mainMenu) {
    btn.addEventListener("click", () => {
      mainMenu.classList.toggle("open");
    });
  }
});
