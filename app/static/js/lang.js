document.addEventListener("DOMContentLoaded", () => {

  const switcher = document.querySelector(".lang-switch");
  if (!switcher) return;

  const trigger = switcher.querySelector(".lang-trigger");
  const menu = switcher.querySelector(".lang-menu");
  const items = switcher.querySelectorAll(".lang-item[data-lang]");

  const close = () => {
    switcher.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
  };

  const toggle = () => {
    const willOpen = !switcher.classList.contains("is-open");
    switcher.classList.toggle("is-open", willOpen);
    trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
  };

  // Ouvrir/fermer
  trigger.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggle();
  });

  // Fermer au clic dehors
  document.addEventListener("click", (e) => {
    if (!switcher.contains(e.target)) close();
  });

  // Fermer à Escape
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });

  // Enregistrer la langue au clic
  items.forEach((a) => {
    a.addEventListener("click", () => {
      localStorage.setItem("lang", a.dataset.lang);
      // On laisse la navigation suivre le href:
      // le serveur posera le cookie "lang" et rechargera la page dans la bonne langue.
    });
  });

});
