document.addEventListener("DOMContentLoaded", () => {

    const btn = document.getElementById("theme-toggle");
    const root = document.documentElement;

    // --- Charger le thème depuis localStorage ---
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        root.classList.add("dark-mode");
        btn.textContent = "🌙️"; // icône lune si dark actif
    } else {
        btn.textContent = "☀️"; // icône soleil si light
    }

    // --- Bouton toggle ---
    btn.addEventListener("click", () => {
        const isDark = root.classList.toggle("dark-mode");

        if (isDark) {
            localStorage.setItem("theme", "dark");
            btn.textContent = "🌙️"; // afficher lune
        } else {
            localStorage.setItem("theme", "light");
            btn.textContent = "☀️"; // afficher soleil
        }
    });
});
