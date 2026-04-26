document.addEventListener("click", function (event) {
  var switchLink = event.target.closest("[data-lang-switch]");

  if (!switchLink) {
    return;
  }

  var targetLanguage = switchLink.getAttribute("data-lang-target");

  if (targetLanguage !== "en" && targetLanguage !== "zh") {
    return;
  }

  try {
    localStorage.setItem("preferredLanguage", targetLanguage);
  } catch (error) {
    // Continue navigation even if localStorage is unavailable.
  }
});
