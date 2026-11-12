document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.getAttribute("data-confirm") || "Подтвердить действие?";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll(".flash").forEach((element) => {
    window.setTimeout(() => {
      element.style.transition = "opacity .35s ease";
      element.style.opacity = "0";
      window.setTimeout(() => element.remove(), 400);
    }, 6000);
  });
});
