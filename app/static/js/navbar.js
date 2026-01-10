document.addEventListener("DOMContentLoaded", () => {
  const dropdowns = document.querySelectorAll(".nav-dropdown");

  dropdowns.forEach(dropdown => {
    let closeTimeout = null;

    dropdown.addEventListener("mouseenter", () => {
      if (closeTimeout) {
        clearTimeout(closeTimeout);
        closeTimeout = null;
      }
      dropdown.classList.add("is-open");
    });

    dropdown.addEventListener("mouseleave", () => {
      closeTimeout = setTimeout(() => {
        dropdown.classList.remove("is-open");
      }, 100); // délai en ms
    });
  });
});
